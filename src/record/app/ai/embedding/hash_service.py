import hashlib
import enum


class HashAlgorithm(enum.Enum):
    SHA256 = "sha256"


class HashService:
    def hash(
        self, content: str, algorithm: HashAlgorithm = HashAlgorithm.SHA256
    ) -> str:
        digest = hashlib.new(name=algorithm.value, data=content.encode("utf-8"))
        return digest.hexdigest()
    