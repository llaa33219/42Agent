"""
Conversation history manager with automatic RAG integration for overflow.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from collections import deque

from .rag import RAGMemory

logger = logging.getLogger(__name__)


@dataclass
class Message:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    audio_duration: Optional[float] = None


class ConversationManager:
    DEFAULT_MAX_MESSAGES = 50
    DEFAULT_ARCHIVE_THRESHOLD = 40

    def __init__(
        self,
        memory: RAGMemory,
        max_messages: int = DEFAULT_MAX_MESSAGES,
        archive_threshold: int = DEFAULT_ARCHIVE_THRESHOLD,
        session_id: Optional[str] = None
    ):
        self.memory = memory
        self.max_messages = max_messages
        self.archive_threshold = archive_threshold
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        self._messages: deque[Message] = deque(maxlen=max_messages)
        self._archive_lock = asyncio.Lock()

    async def add_message(
        self,
        role: str,
        content: str,
        audio_duration: Optional[float] = None
    ):
        message = Message(
            role=role,
            content=content,
            audio_duration=audio_duration
        )
        self._messages.append(message)

        if len(self._messages) >= self.archive_threshold:
            asyncio.create_task(self._archive_old_messages())

    async def _archive_old_messages(self):
        async with self._archive_lock:
            if len(self._messages) < self.archive_threshold:
                return

            messages_to_archive = []
            archive_count = len(self._messages) - (self.archive_threshold // 2)

            for _ in range(archive_count):
                if self._messages:
                    messages_to_archive.append(self._messages.popleft())

            for msg in messages_to_archive:
                await self.memory.save_conversation(
                    role=msg.role,
                    content=msg.content,
                    session_id=self.session_id
                )

            logger.info(f"Archived {len(messages_to_archive)} messages to RAG")

    def get_recent_messages(self, count: Optional[int] = None) -> list[Message]:
        if count is None:
            return list(self._messages)
        return list(self._messages)[-count:]

    def format_for_context(self, count: Optional[int] = None) -> str:
        messages = self.get_recent_messages(count)
        formatted = []
        for msg in messages:
            role_prefix = "User" if msg.role == "user" else "Agent42"
            formatted.append(f"{role_prefix}: {msg.content}")
        return "\n".join(formatted)

    async def get_full_context(
        self,
        query: str,
        recent_count: int = 10,
        rag_results: int = 5
    ) -> str:
        recent = self.format_for_context(recent_count)

        relevant = await self.memory.search(
            query,
            n_results=rag_results,
            filter_metadata={"type": "conversation"}
        )

        if not relevant:
            return recent

        archived = "\n---\n".join([m["content"] for m in relevant])

        return f"[Relevant Past Context]\n{archived}\n\n[Recent Conversation]\n{recent}"

    async def summarize_and_archive_all(self):
        async with self._archive_lock:
            for msg in self._messages:
                await self.memory.save_conversation(
                    role=msg.role,
                    content=msg.content,
                    session_id=self.session_id
                )
            self._messages.clear()
            logger.info("Archived all messages")

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def is_near_capacity(self) -> bool:
        return len(self._messages) >= self.archive_threshold
