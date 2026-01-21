"""
RAG-based long-term memory system using ChromaDB for unlimited conversation history.
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class RAGMemory:
    COLLECTION_NAME = "agent42_memory"
    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(
        self,
        persist_dir: str = "./data/memory",
        embedding_model: Optional[str] = None
    ):
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

        model_name = embedding_model or self.DEFAULT_MODEL
        self.embedder = SentenceTransformer(model_name)
        logger.info(f"RAG Memory initialized with {model_name}")

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
        meta["timestamp"] = datetime.now().isoformat()
        meta["type"] = meta.get("type", "general")

        await asyncio.to_thread(
            self.collection.add,
            ids=[doc_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[meta]
        )

        logger.debug(f"Saved memory: {doc_id}")
        return doc_id

    async def search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[dict] = None
    ) -> list[dict]:
        embedding = await asyncio.to_thread(self._embed, query)

        where = filter_metadata if filter_metadata else None

        results = await asyncio.to_thread(
            self.collection.query,
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        memories = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                memories.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0
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
            self.collection.delete,
            ids=[doc_id]
        )
        logger.debug(f"Deleted memory: {doc_id}")

    async def clear(self):
        self.client.delete_collection(self.COLLECTION_NAME)
        self.collection = self.client.create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info("Memory cleared")

    @property
    def count(self) -> int:
        return self.collection.count()
