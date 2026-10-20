import uuid

from record.db.sql.repository import BaseRepository
from record.app.assets.models import Asset, AssetUpload

class AssetRepository(BaseRepository[Asset]):
    def __init__(self, model, context_fn):
        super().__init__(model, context_fn)

    async def find_by_id(self, *, id: uuid.UUID) -> Asset | None:
        return await self._find_one(where=(self._model.id == id,))

    async def find_many_by_user(self, *, user_id: uuid.UUID) -> list[Asset]:
        return await self._find_many(where=(self._model.user_id == user_id))

    async def update_by_id(self, *, user_id: uuid.UUID, asset_id: uuid.UUID, update_data: dict) -> Asset | None:
        return await self._update(data=update_data, where=((self._model.user_id == user_id) & (self._model.asset_id == asset_id)))


class AssetUploadRepository(BaseRepository[AssetUpload]):
    def __init__(self, model, context_fn):
        super().__init__(model, context_fn)

    async def find_by_id(self, *, id: uuid.UUID) -> AssetUpload | None:
        return await self._find_one(where=(self._model.upload_id == id,))

    async def find_many_by_user(self, *, user_id: uuid.UUID) -> list[AssetUpload]:
        return await self._find_many(where=(self._model.user_id == user_id))

    async def create(self, *, data: AssetUpload):
        return await self._create(data)

    async def update_by_id(self, *, user_id: uuid.UUID, upload_id: uuid.UUID, update_data: dict) -> AssetUpload | None:
        return await self._update(data=update_data, where=((self._model.user_id == user_id) & (self._model.asset_id == upload_id)))

    async def delete_by_id(self, *, upload_id: uuid.UUID) -> AssetUpload:
        return await self._delete(where=(self._model.upload_id == upload_id))
