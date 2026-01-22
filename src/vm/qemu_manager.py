"""
QEMU VM lifecycle manager - starts, stops, and monitors QEMU instances.
"""

import asyncio
import logging
import os
import shutil
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VMConfig:
    iso_path: str
    disk_path: Optional[str] = None
    disk_size: str = "20G"
    memory: str = "4096"
    cpus: int = 2
    display_width: int = 1920
    display_height: int = 1080
    vnc_port: int = 5900
    qmp_port: int = 4444
    enable_kvm: bool = True
    extra_args: list[str] = field(default_factory=list)


class QEMUManager:
    def __init__(self, config: VMConfig, work_dir: str = "./data/vm"):
        self.config = config
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self._process: Optional[asyncio.subprocess.Process] = None
        self._qemu_binary = self._find_qemu_binary()

    def _find_qemu_binary(self) -> str:
        for binary in ["qemu-system-x86_64", "kvm", "qemu-kvm"]:
            path = shutil.which(binary)
            if path:
                return path
        raise RuntimeError("QEMU not found. Please install qemu-system-x86_64")

    def _build_command(self) -> list[str]:
        cfg = self.config
        cmd = [self._qemu_binary]

        if cfg.enable_kvm and os.path.exists("/dev/kvm"):
            cmd.append("-enable-kvm")

        cmd.extend(["-m", cfg.memory])
        cmd.extend(["-smp", str(cfg.cpus)])

        if cfg.disk_path:
            disk = Path(cfg.disk_path)
            if not disk.exists():
                self._create_disk(disk, cfg.disk_size)
            cmd.extend(["-hda", str(disk)])

        if cfg.iso_path and Path(cfg.iso_path).exists():
            cmd.extend(["-cdrom", cfg.iso_path])
            if not cfg.disk_path:
                cmd.append("-boot")
                cmd.append("d")

        vnc_display = cfg.vnc_port - 5900
        cmd.extend(["-vnc", f":{vnc_display}"])

        cmd.extend([
            "-qmp", f"tcp:localhost:{cfg.qmp_port},server,nowait"
        ])

        cmd.extend([
            "-device", f"virtio-vga,xres={cfg.display_width},yres={cfg.display_height}",
            "-device", "virtio-keyboard-pci",
            "-device", "virtio-mouse-pci",
            "-device", "virtio-net-pci,netdev=net0",
            "-netdev", "user,id=net0",
            "-usb",
            "-device", "usb-tablet"
        ])

        cmd.extend([
            "-audiodev", "pa,id=audio0",
            "-device", "intel-hda",
            "-device", "hda-duplex,audiodev=audio0"
        ])

        cmd.extend(cfg.extra_args)

        return cmd

    def _create_disk(self, path: Path, size: str):
        qemu_img = shutil.which("qemu-img")
        if not qemu_img:
            raise RuntimeError("qemu-img not found")

        import subprocess
        subprocess.run([
            qemu_img, "create", "-f", "qcow2",
            str(path), size
        ], check=True)
        logger.info(f"Created disk image: {path} ({size})")

    async def start(self) -> bool:
        if self._process and self._process.returncode is None:
            logger.warning("VM is already running")
            return True

        cmd = self._build_command()
        logger.info(f"Starting QEMU: {' '.join(cmd)}")

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await asyncio.sleep(2)

            if self._process.returncode is not None:
                stderr = await self._process.stderr.read()
                logger.error(f"QEMU failed to start: {stderr.decode()}")
                return False

            logger.info(f"QEMU started with PID {self._process.pid}")
            return True

        except Exception as e:
            logger.error(f"Failed to start QEMU: {e}")
            return False

    async def stop(self, force: bool = False):
        if not self._process:
            return

        if force:
            self._process.kill()
        else:
            self._process.send_signal(signal.SIGTERM)

        try:
            await asyncio.wait_for(self._process.wait(), timeout=10)
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()

        logger.info("QEMU stopped")
        self._process = None

    async def wait(self):
        if self._process:
            await self._process.wait()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def pid(self) -> Optional[int]:
        return self._process.pid if self._process else None

    @property
    def vnc_address(self) -> str:
        return f"localhost:{self.config.vnc_port}"

    @property
    def qmp_address(self) -> tuple[str, int]:
        return ("localhost", self.config.qmp_port)
