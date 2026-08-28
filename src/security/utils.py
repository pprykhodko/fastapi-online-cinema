import secrets


def generate_secure_token() -> str:
    return secrets.token_hex(32)
