import uuid
from collections.abc import Callable
from typing import TypedDict

from record.db.sql.repository import BaseRepository
from record.app.assets.models import Asset, AssetUpload, AssetStatus


class AssetUpdate(TypedDict, total=False):
    name: str
    status: AssetStatus


class AssetUploadUpdate(TypedDict, total=False):
    status: AssetStatus

class AssetRepository(BaseRepository[Asset]):
    def __init__(self, context_fn: Callable):
        super().__init__(Asset, context_fn)

    async def find_by_id(self, *, user_id: uuid.UUID, asset_id: uuid.UUID) -> Asset | None:
        return await self._find_one(
            where=(self._model.user_id == user_id, self._model.id == asset_id)
        )

    async def find_many_by_user(self, *, user_id: uuid.UUID) -> list[Asset]:
        return await self._find_many(where=(self._model.user_id == user_id,))

    async def create(self, *, data: Asset) -> Asset:
        return await self._create(data)

    async def update_by_id(
        self, *, user_id: uuid.UUID, asset_id: uuid.UUID, update_data: AssetUpdate
    ) -> Asset | None:
        return await self._update(
            data=update_data,
            where=(self._model.user_id == user_id, self._model.id == asset_id),
        )


class AssetUploadRepository(BaseRepository[AssetUpload]):
    def __init__(self, context_fn: Callable):
        super().__init__(AssetUpload, context_fn)

    async def find_by_id(
        self, *, user_id: uuid.UUID, upload_id: uuid.UUID
    ) -> AssetUpload | None:
        return await self._find_one(
            where=(self._model.user_id == user_id, self._model.upload_id == upload_id)
        )

    async def find_many_by_user(self, *, user_id: uuid.UUID) -> list[AssetUpload]:
        return await self._find_many(where=(self._model.user_id == user_id,))

    async def create(self, *, data: AssetUpload) -> AssetUpload:
        return await self._create(data)

    async def update_by_id(
        self, *, user_id: uuid.UUID, upload_id: uuid.UUID, update_data: AssetUploadUpdate
    ) -> AssetUpload | None:
        return await self._update(
            data=update_data,
            where=(self._model.user_id == user_id, self._model.upload_id == upload_id),
        )

    async def delete_by_id(self, *, user_id: uuid.UUID, upload_id: uuid.UUID) -> bool:
        return await self._delete(
            where=(self._model.user_id == user_id, self._model.upload_id == upload_id)
        )