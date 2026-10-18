from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    db_url: str = Field(min_length=32)
    app_url: HttpUrl
    redis_cache_url: str = Field(min_length=24)
    celery_queue_url: str = Field(min_length=32)
    
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: HttpUrl
    jwt_audience: HttpUrl
    jwt_access_expiry_minutes: int = Field(ge=5, description="Jwt access token time in minutes")

    refresh_expiry_days: int = Field(ge=1, description="Opaque stateful refresh token time in days")
    refresh_max_session_days: int = Field(default=30, ge=1, description="Maximum session lifetime in days")

    model_config = SettingsConfigDict(
        env_file=".env.local",
        extra="forbid",   
        frozen=True,
        str_strip_whitespace=True
    )
