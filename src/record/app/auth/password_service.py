from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

class PasswordService:
    def __init__(self):
        self.hasher = PasswordHash((Argon2Hasher(), ))

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def compare(self, *, password: str, hash: str) -> bool:
        return self.hasher.verify(password, hash)