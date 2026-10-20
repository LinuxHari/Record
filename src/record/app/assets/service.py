import math

from typing import TypedDict
from pydantic import Field

from record.aws.s3_service import AwsS3
from record.exceptions.http_excpetions import BadRequestException
from record.app.assets.repository import AssetRepository, AssetUploadRepository
from record.app.assets.models import Asset, AssetUpload, AssetStatus


class AssetMetadata(TypedDict):
    name: str
    size: int
    type: str


class AssetService:
    MULTIPART_CHUNK_SIZE_IN_MB = 64

    def __init__(
        self,
        *,
        asset_repository: AssetRepository,
        asset_upload_repository: AssetUploadRepository,
        s3_service: AwsS3,
    ):
        self.s3_service: AwsS3 = s3_service
        self.asset_repository: AssetRepository = asset_repository
        self.asset_upload_repository: AssetUploadRepository = asset_upload_repository

    async def initiate_asset_upload(
        self, asset_metadata: AssetMetadata, user_id: str
    ) -> list[dict]:
        total_chunks = math.ceil(
            asset_metadata["size"] / (self.MULTIPART_CHUNK_SIZE_IN_MB * 1000 * 1000)
        )
        upload_id = await self.s3_service.create_multipart_upload(
            file_name=asset_metadata["name"], content_type=asset_metadata["type"]
        )
        urls = await self.s3_service.generate_presigned_part_urls(
            file_name=asset_metadata["name"],
            upload_id=upload_id,
            total_parts=total_chunks,
        )

        await self.asset_upload_repository.create(
            AssetUpload(
                upload_id=upload_id,
                name=asset_metadata["name"],
                size=asset_metadata["size"],
                type=asset_metadata["type"],
                user_id=user_id,
            )
        )

        return urls

    async def list_assets(self, *, user_id: str) -> list[dict]:
        user_assets = await self.asset_repository.find_many_by_user(user_id=user_id)
        return user_assets

    async def asset_upload_complete(self, *, user_id, asset_id):
        asset = await self.asset_repository.update_by_id(
            user_id=user_id,
            asset_id=asset_id,
            update_data={"status": AssetStatus.SUCCESS},
        )

        if not asset:
            raise BadRequestException("No asset found")

        await self.asset_upload_repository.delete_by_id()

    # def update_asset(self, asset_id, updated_data):
    #     """
    #     Updates an existing asset in the system.

    #     :param asset_id: The ID of the asset to be updated.
    #     :param updated_data: The new data for the asset.
    #     :return: A response indicating the success or failure of the update.
    #     """
    #     # Implement the logic for updating an asset
    #     pass
