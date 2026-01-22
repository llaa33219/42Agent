"""
VNC screen capture for streaming VM display at 30fps.
Pure Python RFB (VNC) protocol implementation - no twisted dependency.
"""

import asyncio
import io
import logging
import struct
from typing import Callable, Optional

from PIL import Image

logger = logging.getLogger(__name__)


class VNCCapture:
    """Async VNC client using pure Python RFB protocol."""
    
    # RFB Protocol constants
    RFB_VERSION = b"RFB 003.008\n"
    
    # Message types
    MSG_FRAMEBUFFER_UPDATE_REQUEST = 3
    MSG_FRAMEBUFFER_UPDATE = 0
    
    # Encoding types
    ENCODING_RAW = 0
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5900,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30
    ):
        self.host = host
        self.port = port
        self.target_width = width
        self.target_height = height
        self.fps = fps

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._running = False
        self._capture_task: Optional[asyncio.Task] = None
        self._frame_callback: Optional[Callable[[bytes], None]] = None
        
        # Framebuffer
        self._fb_width = 0
        self._fb_height = 0
        self._fb_bpp = 0
        self._fb_depth = 0
        self._fb_bigendian = False
        self._fb_truecolor = True
        self._pixel_format = None
        self._framebuffer: Optional[Image.Image] = None
        self._last_frame: Optional[bytes] = None

    async def connect(self, max_retries: int = 10, retry_delay: float = 1.0) -> bool:
        """Connect to VNC server using RFB protocol."""
        for attempt in range(max_retries):
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=5.0
                )
                
                # Protocol version handshake
                server_version = await self._reader.read(12)
                logger.debug(f"Server version: {server_version}")
                self._writer.write(self.RFB_VERSION)
                await self._writer.drain()
                
                # Security handshake
                num_security_types = await self._reader.read(1)
                if num_security_types == b'\x00':
                    # Connection failed, read reason
                    reason_len = struct.unpack('>I', await self._reader.read(4))[0]
                    reason = await self._reader.read(reason_len)
                    logger.error(f"VNC connection refused: {reason.decode()}")
                    return False
                
                security_types = await self._reader.read(num_security_types[0])
                logger.debug(f"Security types: {list(security_types)}")
                
                # Select None authentication (type 1) if available
                if 1 in security_types:
                    self._writer.write(b'\x01')  # None auth
                    await self._writer.drain()
                else:
                    logger.error("No supported security type (need None auth)")
                    return False
                
                # Security result
                security_result = struct.unpack('>I', await self._reader.read(4))[0]
                if security_result != 0:
                    logger.error(f"Security handshake failed: {security_result}")
                    return False
                
                # ClientInit - shared flag
                self._writer.write(b'\x01')  # Shared
                await self._writer.drain()
                
                # ServerInit
                server_init = await self._reader.read(24)
                self._fb_width, self._fb_height = struct.unpack('>HH', server_init[:4])
                
                # Pixel format (16 bytes)
                pf = server_init[4:20]
                self._fb_bpp = pf[0]
                self._fb_depth = pf[1]
                self._fb_bigendian = pf[2] != 0
                self._fb_truecolor = pf[3] != 0
                
                # Red, green, blue max and shift
                r_max, g_max, b_max = struct.unpack('>HHH', pf[4:10])
                r_shift, g_shift, b_shift = pf[10], pf[11], pf[12]
                
                self._pixel_format = {
                    'bpp': self._fb_bpp,
                    'depth': self._fb_depth,
                    'bigendian': self._fb_bigendian,
                    'truecolor': self._fb_truecolor,
                    'r_max': r_max, 'g_max': g_max, 'b_max': b_max,
                    'r_shift': r_shift, 'g_shift': g_shift, 'b_shift': b_shift
                }
                
                # Desktop name
                name_len = struct.unpack('>I', server_init[20:24])[0]
                desktop_name = await self._reader.read(name_len)
                
                logger.info(f"VNC connected to {self.host}:{self.port} - "
                           f"{self._fb_width}x{self._fb_height} {self._fb_bpp}bpp "
                           f"'{desktop_name.decode(errors='ignore')}'")
                
                # Initialize framebuffer
                self._framebuffer = Image.new('RGB', (self._fb_width, self._fb_height), (0, 0, 0))
                
                # Set pixel format to 32-bit BGRA for easier handling
                await self._set_pixel_format()
                
                # Set encodings (RAW only for simplicity)
                await self._set_encodings()
                
                return True
                
            except asyncio.TimeoutError:
                logger.debug(f"VNC connection attempt {attempt + 1} timed out")
            except Exception as e:
                logger.debug(f"VNC connection attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
        
        logger.error(f"VNC connection failed after {max_retries} attempts")
        return False

    async def _set_pixel_format(self):
        """Set pixel format to 32-bit BGRA."""
        # SetPixelFormat message
        msg = struct.pack(
            '>BBBB BBBB HHH BBB xxx',
            0,        # message type
            0, 0, 0,  # padding
            32,       # bpp
            24,       # depth
            0,        # big-endian (false)
            1,        # true-color (true)
            255, 255, 255,  # r/g/b max
            16, 8, 0  # r/g/b shift (BGRA format)
        )
        self._writer.write(msg)
        await self._writer.drain()
        
        self._fb_bpp = 32
        self._pixel_format = {
            'bpp': 32, 'depth': 24, 'bigendian': False, 'truecolor': True,
            'r_max': 255, 'g_max': 255, 'b_max': 255,
            'r_shift': 16, 'g_shift': 8, 'b_shift': 0
        }

    async def _set_encodings(self):
        """Set supported encodings (RAW only)."""
        encodings = [self.ENCODING_RAW]
        msg = struct.pack('>BBH', 2, 0, len(encodings))
        for enc in encodings:
            msg += struct.pack('>i', enc)
        self._writer.write(msg)
        await self._writer.drain()

    async def _request_framebuffer_update(self, incremental: bool = True):
        """Request framebuffer update from server."""
        msg = struct.pack(
            '>BBHHHH',
            self.MSG_FRAMEBUFFER_UPDATE_REQUEST,
            1 if incremental else 0,
            0, 0,  # x, y
            self._fb_width, self._fb_height
        )
        self._writer.write(msg)
        await self._writer.drain()

    async def _read_framebuffer_update(self) -> bool:
        """Read and process framebuffer update message."""
        try:
            # Read message type
            msg_type = await asyncio.wait_for(self._reader.read(1), timeout=0.5)
            if not msg_type:
                return False
            
            msg_type = msg_type[0]
            
            if msg_type == self.MSG_FRAMEBUFFER_UPDATE:
                # Framebuffer update
                header = await self._reader.read(3)
                num_rects = struct.unpack('>xH', header)[0]
                
                for _ in range(num_rects):
                    rect_header = await self._reader.read(12)
                    x, y, w, h, encoding = struct.unpack('>HHHHi', rect_header)
                    
                    if encoding == self.ENCODING_RAW:
                        # Read raw pixel data
                        bytes_per_pixel = self._fb_bpp // 8
                        data_len = w * h * bytes_per_pixel
                        pixel_data = b''
                        while len(pixel_data) < data_len:
                            chunk = await self._reader.read(min(data_len - len(pixel_data), 65536))
                            if not chunk:
                                break
                            pixel_data += chunk
                        
                        # Update framebuffer
                        if len(pixel_data) == data_len and self._framebuffer:
                            rect_img = Image.frombytes('RGBX', (w, h), pixel_data, 'raw', 'BGRX')
                            self._framebuffer.paste(rect_img.convert('RGB'), (x, y))
                    
                    elif encoding == -223:  # DesktopSize pseudo-encoding
                        # Desktop resize
                        self._fb_width = w
                        self._fb_height = h
                        self._framebuffer = Image.new('RGB', (w, h), (0, 0, 0))
                        logger.info(f"VNC desktop resized to {w}x{h}")
                    
                    else:
                        logger.warning(f"Unsupported encoding: {encoding}")
                
                return True
            else:
                # Skip other message types
                logger.debug(f"Ignoring message type: {msg_type}")
                return False
                
        except asyncio.TimeoutError:
            return False
        except Exception as e:
            logger.error(f"Error reading framebuffer update: {e}")
            return False

    async def disconnect(self):
        """Disconnect from VNC server."""
        self._running = False
        
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
        
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        
        self._reader = None
        self._writer = None
        self._framebuffer = None
        logger.info("VNC disconnected")

    async def capture_frame(self) -> Optional[bytes]:
        """Capture current framebuffer as JPEG."""
        if not self._writer or not self._framebuffer:
            return self._last_frame
        
        try:
            # Request update and process response
            await self._request_framebuffer_update(incremental=True)
            await self._read_framebuffer_update()
            
            # Convert framebuffer to JPEG
            fb = self._framebuffer
            if fb.size != (self.target_width, self.target_height):
                fb = fb.resize(
                    (self.target_width, self.target_height),
                    Image.Resampling.LANCZOS
                )
            
            buffer = io.BytesIO()
            fb.save(buffer, format="JPEG", quality=80)
            self._last_frame = buffer.getvalue()
            return self._last_frame
            
        except Exception as e:
            logger.error(f"Frame capture error: {e}")
            return self._last_frame

    async def capture_frame_raw(self) -> Optional[bytes]:
        """Capture current framebuffer as raw RGB bytes."""
        if not self._framebuffer:
            return None
        
        try:
            await self._request_framebuffer_update(incremental=True)
            await self._read_framebuffer_update()
            return self._framebuffer.tobytes()
        except Exception as e:
            logger.error(f"Raw frame capture error: {e}")
            return None

    def set_frame_callback(self, callback: Callable[[bytes], None]):
        self._frame_callback = callback

    async def start_streaming(self):
        """Start streaming frames to callback."""
        self._running = True
        self._capture_task = asyncio.create_task(self._stream_loop())

    async def _stream_loop(self):
        """Async loop that captures frames and calls callback."""
        frame_interval = 1.0 / self.fps
        
        # Request initial full framebuffer
        if self._writer:
            await self._request_framebuffer_update(incremental=False)
        
        while self._running:
            try:
                start_time = asyncio.get_event_loop().time()
                
                frame = await self.capture_frame()
                if frame and self._frame_callback:
                    self._frame_callback(frame)
                
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed < frame_interval:
                    await asyncio.sleep(frame_interval - elapsed)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stream error: {e}")
                await asyncio.sleep(0.1)

    async def stop_streaming(self):
        self._running = False
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass

    async def read(self) -> Optional[bytes]:
        return await self.capture_frame()

    @property
    def is_connected(self) -> bool:
        return self._writer is not None

    @property
    def is_streaming(self) -> bool:
        return self._running
