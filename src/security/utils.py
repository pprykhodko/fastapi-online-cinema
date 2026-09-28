import hashlib
import secrets


def generate_secure_token() -> str:
    """
    Generate a cryptographically random URL-safe token.

    Returns:
        str: URL-safe random token.
    """
    return secrets.token_hex(32)


def hash_reset_token(token: str) -> str:
    """
    Hash a reset token with SHA-256 for lookup without storing its plaintext.

    Args:
        token (str): Plaintext token supplied by the caller; never log this value.

    Returns:
        str: Hexadecimal SHA-256 digest of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()
