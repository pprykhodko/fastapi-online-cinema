import hashlib
import secrets


def generate_secure_token() -> str:
    return secrets.token_hex(32)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
