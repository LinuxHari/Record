from typing import Callable
from record.db.sql.repository import BaseRepository
from record.app.ai.embedding.models import Embeddings


class EmbeddingRepository(BaseRepository[Embeddings]):
    def __init__(self, context_fn: Callable):
        super().__init__(Embeddings, context_fn)

    async def create(self, *, data: Embeddings) -> Embeddings:
        return await self._create(data)
        