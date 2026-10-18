import uuid

from record.db.sql.repository import BaseRepository
from record.app.assets.models import Asset

class AssetRepository(BaseRepository[Asset]):
    def __init__(self, model, context_fn):
        super().__init__(model, context_fn)

    async def find_by_id(self, *, id: uuid.UUID) -> Asset | None:
        return await self._find_one(where=(self._model.id == id,))

    async def find_many_by_user(self, *, user_id: uuid.UUID) -> list[Asset]:
        return await self._find_many(where=(self._model.user_id == user_id))