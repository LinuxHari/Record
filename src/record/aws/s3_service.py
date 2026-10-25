from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, NamedTuple

from aiobotocore.session import AioSession, get_session


@dataclass(frozen=True)
class S3Config:
    bucket_name: str
    secret_access_key: str
    access_key_id: str
    region_name: str
    folder: str

class MultipartConf(NamedTuple):
    upload_id: str
    key: str


class AwsS3:
    def __init__(self, *, config: S3Config) -> None:
        self.config = config
        self._session: AioSession = get_session()

    def _key(self, file_name: str) -> str:
        return f"{self.config.folder}/{file_name}"

    @asynccontextmanager
    async def get_client(self):
        try:
            async with self._session.create_client(
                "s3",
                region_name=self.config.region_name,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
            ) as client:
                yield client
        except Exception as e:
            print("Error getting s3 client:", str(e))
            raise

    async def get_s3_object(self, *, file_name: str):
        async with self.get_client() as client:
            resp = await client.get_object(
                Bucket=self.config.bucket_name, Key=self._key(file_name)
            )

            body = await resp["Body"].read()
            return body, resp.get("ContentType")

    async def stream_s3_object(
        self, *, file_name: str, chunk_size: int = 1024 * 64
    ) -> AsyncIterator[bytes]:
        async with self.get_client() as client:
            resp = await client.get_object(
                Bucket=self.config.bucket_name, Key=self._key(file_name)
            )
            async with resp["Body"] as stream:
                while chunk := await stream.read(chunk_size):
                    yield chunk

    async def delete_S3_object(self, *, file_name: str):
        async with self.get_client() as client:
            return await client.delete_object(
                Bucket=self.config.bucket_name, Key=self._key(file_name)
            )

    async def generate_presigned_get_url(
        self, *, file_name: str, expires_in: int = 3600
    ) -> str:
        async with self.get_client() as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.config.bucket_name, "Key": self._key(file_name)},
                ExpiresIn=expires_in,
            )

    async def generate_presigned_put_url(
        self, *, file_name: str, content_type: str | None = None, expires_in: int = 3600
    ) -> str:
        params = {"Bucket": self.config.bucket_name, "Key": self._key(file_name)}
        if content_type:
            params["ContentType"] = content_type
        async with self.get_client() as client:
            return await client.generate_presigned_url(
                "put_object", Params=params, ExpiresIn=expires_in
            )

    async def create_multipart_upload(
        self, *, file_name: str, content_type: str | None = None
    ) -> MultipartConf:
        key = self._key(file_name)
        kwargs = {"Bucket": self.config.bucket_name, "Key": key}
        if content_type:
            kwargs["ContentType"] = content_type
        async with self.get_client() as client:
            resp = await client.create_multipart_upload(**kwargs)
            return MultipartConf(upload_id=resp["UploadId"], key=key)

    async def generate_presigned_part_url(
        self,
        *,
        file_name: str,
        upload_id: str,
        part_number: int,
        expires_in: int = 3600,
    ) -> str:
        if not 1 <= part_number <= 10000:
            raise ValueError("part_number must be between 1 and 10000")
        async with self.get_client() as client:
            return await client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.config.bucket_name,
                    "Key": self._key(file_name),
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=expires_in,
            )

    async def generate_presigned_part_urls(
        self,
        *,
        file_name: str,
        upload_id: str,
        total_parts: int,
        expires_in: int = 3600,
    ) -> list[dict]:
        urls = []
        async with self.get_client() as client:
            for part_number in range(1, total_parts + 1):
                url = await client.generate_presigned_url(
                    "upload_part",
                    Params={
                        "Bucket": self.config.bucket_name,
                        "Key": self._key(file_name),
                        "UploadId": upload_id,
                        "PartNumber": part_number,
                    },
                    ExpiresIn=expires_in,
                )
                urls.append({"part_number": part_number, "url": url})
        return urls

    async def complete_multipart_upload(
        self, *, file_name: str, upload_id: str, parts: list[dict] #Parts will contain part numbers and ETags
    ):
        parts = sorted(parts, key=lambda p: p["PartNumber"])
        async with self.get_client() as client:
            return await client.complete_multipart_upload(
                Bucket=self.config.bucket_name,
                Key=self._key(file_name),
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

    async def abort_multipart_upload(self, *, file_name: str, upload_id: str):
        async with self.get_client() as client:
            return await client.abort_multipart_upload(
                Bucket=self.config.bucket_name,
                Key=self._key(file_name),
                UploadId=upload_id,
            )

    async def list_parts(self, *, file_name: str, upload_id: str) -> list[dict]:
        """Useful for resuming an interrupted upload."""
        async with self.get_client() as client:
            resp = await client.list_parts(
                Bucket=self.config.bucket_name,
                Key=self._key(file_name),
                UploadId=upload_id,
            )
            return resp.get("Parts", [])
