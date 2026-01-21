"""
Agent module - Core AI agent with omnimodal capabilities
"""

from .core import Agent42
from .omni_client import OmniRealtimeClient
from .tools import ToolExecutor
from .system_prompt import SYSTEM_PROMPT

__all__ = ["Agent42", "OmniRealtimeClient", "ToolExecutor", "SYSTEM_PROMPT"]
