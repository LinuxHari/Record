from aiobotocore.session import get_session, AioSession
from contextlib import asynccontextmanager

class AwsS3:
    def __init__(self, bucket_name: str, key: str) -> None:
        self.bucket_name: str = bucket_name
        self.key: str = key
        self._session:AioSession = get_session()

    @asynccontextmanager
    async def get_session(self):

        try:
            async with self._session.create_client("s3") as client:
                yield client
        except Exception as e:
            print("Error getting s3 client", str(e))
            raise

    # def upload_to_S3(self):
    #     pass

    def get_s3_object(self):
        pass

    def stream_s3_object(self):
        pass