from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    db_url: str = Field(min_length=32)
    app_url: HttpUrl
    redis_cache_url: str = Field(min_length=24)
    celery_queue_url: str = Field(min_length=32)

    aws_secret_access_key: str = Field(min_length=4)
    aws_access_key_id: str = Field(min_length=4)
    aws_region_name: str = Field(min_length=8)
    aws_s3_bucket_name: str = Field(min_length=4)
    
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: HttpUrl
    jwt_audience: HttpUrl
    jwt_access_expiry_minutes: int = Field(ge=5, description="Jwt access token time in minutes")

    refresh_expiry_days: int = Field(ge=1, description="Opaque stateful refresh token time in days")
    refresh_max_session_days: int = Field(default=30, ge=1, description="Maximum session lifetime in days")

    docling_server_url: HttpUrl
    embedding_model: str = Field(description="Embedding model id", min_length=3)
    chunk_max_tokens: int = Field(default=512, ge=256, le=512)
    chunk_overlap_tokens: int = Field(default=32, ge=32, le=128)

    model_config = SettingsConfigDict(
        env_file=".env.local",
        extra="forbid",   
        frozen=True,
        str_strip_whitespace=True
    )
