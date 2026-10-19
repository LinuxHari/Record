from record.dependencies import get_settings
from record.aws.s3_service import AwsS3, S3Config


def get_asset_s3():
    settings = get_settings()
    return AwsS3(
        config=S3Config(
            bucket_name=settings.aws_s3_bucket_name,
            secret_access_key=settings.aws_secret_access_key,
            access_key_id=settings.aws_access_key_id,
            region_name=settings.aws_region_name,
            folder="assets",
        )
    )
