"""
Tool parser and executor for Agent42.
Parses <tool> tags from model output and executes corresponding actions.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

TOOL_PATTERN = re.compile(
    r'<tool\s+name="([^"]+)"([^/>]*)/?>(?:</tool>)?',
    re.IGNORECASE | re.DOTALL
)

ATTR_PATTERN = re.compile(r'(\w+)="([^"]*)"')


@dataclass
class ToolCall:
    name: str
    params: dict[str, str]


class ToolExecutor:
    def __init__(self):
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._vm_controller = None
        self._avatar_controller = None
        self._memory_manager = None

    def set_vm_controller(self, controller):
        self._vm_controller = controller

    def set_avatar_controller(self, controller):
        self._avatar_controller = controller

    def set_memory_manager(self, manager):
        self._memory_manager = manager

    def register_handler(self, name: str, handler: Callable[..., Any]):
        self._handlers[name] = handler

    def parse_tools(self, text: str) -> list[ToolCall]:
        tools = []
        for match in TOOL_PATTERN.finditer(text):
            name = match.group(1)
            attrs_str = match.group(2)
            params = dict(ATTR_PATTERN.findall(attrs_str))
            tools.append(ToolCall(name=name, params=params))
        return tools

    def strip_tools(self, text: str) -> str:
        return TOOL_PATTERN.sub("", text).strip()

    async def execute(self, tool: ToolCall) -> Optional[Any]:
        logger.info(f"Executing tool: {tool.name} with params: {tool.params}")

        if tool.name in self._handlers:
            handler = self._handlers[tool.name]
            return await self._call_handler(handler, tool.params)

        if tool.name.startswith("mouse_") or tool.name.startswith("key_") or tool.name == "type_text" or tool.name == "screenshot":
            return await self._execute_vm_tool(tool)

        if tool.name.startswith("avatar_"):
            return await self._execute_avatar_tool(tool)

        if tool.name.startswith("memory_"):
            return await self._execute_memory_tool(tool)

        logger.warning(f"Unknown tool: {tool.name}")
        return None

    async def _call_handler(self, handler: Callable, params: dict) -> Any:
        import asyncio
        if asyncio.iscoroutinefunction(handler):
            return await handler(**params)
        return handler(**params)

    async def _execute_vm_tool(self, tool: ToolCall) -> Optional[Any]:
        if not self._vm_controller:
            logger.error("VM controller not set")
            return None

        vm = self._vm_controller

        if tool.name == "mouse_move":
            x, y = int(tool.params["x"]), int(tool.params["y"])
            await vm.mouse_move(x, y)

        elif tool.name == "mouse_click":
            button = tool.params.get("button", "left")
            await vm.mouse_click(button)

        elif tool.name == "mouse_double_click":
            button = tool.params.get("button", "left")
            await vm.mouse_double_click(button)

        elif tool.name == "mouse_drag":
            start_x = int(tool.params["start_x"])
            start_y = int(tool.params["start_y"])
            end_x = int(tool.params["end_x"])
            end_y = int(tool.params["end_y"])
            await vm.mouse_drag(start_x, start_y, end_x, end_y)

        elif tool.name == "key_press":
            key = tool.params["key"]
            await vm.key_press(key)

        elif tool.name == "key_combo":
            keys = tool.params["keys"]
            await vm.key_combo(keys)

        elif tool.name == "type_text":
            text = tool.params["text"]
            await vm.type_text(text)

        elif tool.name == "screenshot":
            return await vm.screenshot()

        return None

    async def _execute_avatar_tool(self, tool: ToolCall) -> Optional[Any]:
        if not self._avatar_controller:
            logger.error("Avatar controller not set")
            return None

        avatar = self._avatar_controller

        if tool.name == "avatar_expression":
            expression = tool.params["expression"]
            await avatar.set_expression(expression)

        elif tool.name == "avatar_motion":
            motion = tool.params["motion"]
            await avatar.play_motion(motion)

        elif tool.name == "avatar_look":
            x = float(tool.params["x"])
            y = float(tool.params["y"])
            await avatar.look_at(x, y)

        return None

    async def _execute_memory_tool(self, tool: ToolCall) -> Optional[Any]:
        if not self._memory_manager:
            logger.error("Memory manager not set")
            return None

        memory = self._memory_manager

        if tool.name == "memory_save":
            content = tool.params["content"]
            await memory.save(content)

        elif tool.name == "memory_search":
            query = tool.params["query"]
            return await memory.search(query)

        return None

    async def execute_all(self, text: str) -> list[tuple[ToolCall, Any]]:
        tools = self.parse_tools(text)
        results = []
        for tool in tools:
            result = await self.execute(tool)
            results.append((tool, result))
        return results
