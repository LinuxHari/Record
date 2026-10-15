import uuid
import hashlib

# from datetime import timedelta, datetime, timezone
from record.dependencies import get_settings

class RefreshTokenService:
    def __init__(self):
        self.expiry_days = get_settings().refresh_expiry_days

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def generate_token(self) -> str:
        token = str(uuid.uuid4())
        # Futute implementation after redis
        # hashed_token = self._hash(token)
        # expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        return token

    def validate_token(self, token: str):
        hashed_token = self._hash(token)
        