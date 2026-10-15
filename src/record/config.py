from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    db_url: str = Field(min_length=32)
    app_url: HttpUrl
    queue_url: str = Field(min_length=32)
    
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: HttpUrl
    jwt_audience: HttpUrl
    jwt_access_expiry_minutes: int

    refresh_expiry_days: int

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="forbid",   
        frozen=True,
        str_strip_whitespace=True
    )
