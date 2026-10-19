import math

from typing import TypedDict

from record.aws.s3_service import AwsS3
from record.app.assets.repository import AssetRepository

class AssetMetadata(TypedDict):
    name: str
    size: int
    type: str

class AssetService:
    MULTIPART_CHUNK_SIZE_IN_MB = 64

    def __init__(self, *, asset_repository: AssetRepository, s3_service: AwsS3):
        self.s3_service: AwsS3 = s3_service
        self.asset_repository: AssetRepository = asset_repository

    async def initiate_asset_upload(self, asset_metadata: AssetMetadata) -> list[dict]:
        total_chunks = math.ceil(asset_metadata["size"] / (self.MULTIPART_CHUNK_SIZE_IN_MB * 1000 * 1000))
        upload_id = await self.s3_service.create_multipart_upload(file_name=asset_metadata["name"], content_type=asset_metadata["type"])
        urls = await self.s3_service.generate_presigned_part_urls(file_name=asset_metadata["name"], upload_id=upload_id, total_parts=total_chunks)

        return urls
    
    async def list_assets(self, *, user_id: str):
        user_assets = await self.asset_repository.find_many_by_user(user_id=user_id)

    def update_asset(self, asset_id, updated_data):
        """
        Updates an existing asset in the system.

        :param asset_id: The ID of the asset to be updated.
        :param updated_data: The new data for the asset.
        :return: A response indicating the success or failure of the update.
        """
        # Implement the logic for updating an asset
        pass