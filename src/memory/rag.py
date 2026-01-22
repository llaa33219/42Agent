"""
RAG-based long-term memory system using LanceDB for unlimited conversation history.
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime
from typing import Optional

import lancedb
import pyarrow as pa
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class RAGMemory:
    TABLE_NAME = "agent42_memory"
    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(
        self,
        persist_dir: str = "./data/memory",
        embedding_model: Optional[str] = None
    ):
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        self.db = lancedb.connect(persist_dir)

        model_name = embedding_model or self.DEFAULT_MODEL
        self.embedder = SentenceTransformer(model_name)
        self._embedding_dim = self.embedder.get_sentence_embedding_dimension()

        self._init_table()
        logger.info(f"RAG Memory initialized with {model_name}")

    def _init_table(self):
        """Initialize the memory table if it doesn't exist."""
        if self.TABLE_NAME in self.db.table_names():
            self.table = self.db.open_table(self.TABLE_NAME)
        else:
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("content", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self._embedding_dim)),
                pa.field("timestamp", pa.string()),
                pa.field("type", pa.string()),
                pa.field("role", pa.string()),
                pa.field("session_id", pa.string()),
            ])
            self.table = self.db.create_table(self.TABLE_NAME, schema=schema)

    def _generate_id(self, content: str) -> str:
        timestamp = datetime.now().isoformat()
        return hashlib.sha256(f"{content}{timestamp}".encode()).hexdigest()[:16]

    def _embed(self, text: str) -> list[float]:
        return self.embedder.encode(text).tolist()

    async def save(
        self,
        content: str,
        metadata: Optional[dict] = None
    ) -> str:
        doc_id = self._generate_id(content)
        embedding = await asyncio.to_thread(self._embed, content)

        meta = metadata or {}
        timestamp = datetime.now().isoformat()

        data = [{
            "id": doc_id,
            "content": content,
            "vector": embedding,
            "timestamp": timestamp,
            "type": meta.get("type", "general"),
            "role": meta.get("role", ""),
            "session_id": meta.get("session_id", ""),
        }]

        await asyncio.to_thread(self.table.add, data)

        logger.debug(f"Saved memory: {doc_id}")
        return doc_id

    async def search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[dict] = None
    ) -> list[dict]:
        embedding = await asyncio.to_thread(self._embed, query)

        search_query = self.table.search(embedding).limit(n_results)

        if filter_metadata:
            conditions = []
            for key, value in filter_metadata.items():
                conditions.append(f"{key} = '{value}'")
            if conditions:
                search_query = search_query.where(" AND ".join(conditions))

        results = await asyncio.to_thread(search_query.to_list)

        memories = []
        for row in results:
            memories.append({
                "content": row["content"],
                "metadata": {
                    "timestamp": row["timestamp"],
                    "type": row["type"],
                    "role": row["role"],
                    "session_id": row["session_id"],
                },
                "distance": row.get("_distance", 0)
            })

        return memories

    async def save_conversation(
        self,
        role: str,
        content: str,
        session_id: Optional[str] = None
    ) -> str:
        metadata = {
            "type": "conversation",
            "role": role,
            "session_id": session_id or "default"
        }
        return await self.save(content, metadata)

    async def get_relevant_context(
        self,
        query: str,
        max_tokens: int = 2000
    ) -> str:
        memories = await self.search(query, n_results=10)

        context_parts = []
        total_chars = 0
        char_limit = max_tokens * 4

        for mem in memories:
            content = mem["content"]
            if total_chars + len(content) > char_limit:
                break
            context_parts.append(content)
            total_chars += len(content)

        return "\n---\n".join(context_parts)

    async def delete(self, doc_id: str):
        await asyncio.to_thread(
            self.table.delete,
            f"id = '{doc_id}'"
        )
        logger.debug(f"Deleted memory: {doc_id}")

    async def clear(self):
        self.db.drop_table(self.TABLE_NAME)
        self._init_table()
        logger.info("Memory cleared")

    @property
    def count(self) -> int:
        return self.table.count_rows()
