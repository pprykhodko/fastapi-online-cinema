import base64
import json
from datetime import datetime, timezone

import pytest
from jose import jwt  # type: ignore[import-untyped]
from pydantic import SecretStr, ValidationError

from src.core.config import Settings
from src.schemas.accounts import (
    TokenPairResponseSchema, TokenRefreshRequestSchema,
)
from src.security import tokens


TEST_KEY = "unit-test-secret-not-for-production-123456789"
REFRESH_KEY = "unit-test-refresh-secret-not-for-production-987654321"
NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def jwt_settings(monkeypatch):
    settings = Settings(
        _env_file=None,
        JWT_ACCESS_SECRET_KEY=SecretStr(TEST_KEY),
        JWT_REFRESH_SECRET_KEY=SecretStr(REFRESH_KEY),
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=15,
        REFRESH_TOKEN_EXPIRE_DAYS=7,
    )
    monkeypatch.setattr(tokens, "get_settings", lambda: settings)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr(tokens, "datetime", FrozenDatetime)
    monkeypatch.setattr(jwt, "datetime", FrozenDatetime)
    return settings


@pytest.fixture
def manager(jwt_settings):
    return tokens.get_jwt_auth_manager()


@pytest.fixture
def valid_payload(manager):
    return jwt.get_unverified_claims(manager.create_access_token(42))


@pytest.mark.parametrize("token_type, lifetime", [
    ("access", 15 * 60), ("refresh", 7 * 24 * 60 * 60),
])
def test_create_and_decode_tokens(manager, token_type, lifetime):
    create = (
        manager.create_access_token if token_type == "access"
        else manager.create_refresh_token
    )
    token = create(42)
    decode = getattr(manager, f"decode_{token_type}_token")
    payload = decode(token)
    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    assert payload["sub"] == "42"
    assert payload["type"] == token_type
    assert payload["iat"] == int(NOW.timestamp())
    assert payload["exp"] == int(NOW.timestamp()) + lifetime
    assert len(payload["jti"]) == 32
    assert len(token) <= 255
    assert set(payload) == {"sub", "type", "iat", "exp", "jti"}


def test_configured_lifetimes_are_used(jwt_settings):
    jwt_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 5
    jwt_settings.REFRESH_TOKEN_EXPIRE_DAYS = 2
    manager = tokens.JWTAuthManager(jwt_settings)
    access = manager.decode_access_token(manager.create_access_token(1))
    refresh = manager.decode_refresh_token(manager.create_refresh_token(1))
    assert access["exp"] - access["iat"] == 300
    assert refresh["exp"] - refresh["iat"] == 2 * 86400


@pytest.mark.parametrize("create", [
    "create_access_token", "create_refresh_token",
])
def test_tokens_are_unique_even_in_same_second(manager, create):
    create_token = getattr(manager, create)
    assert len({create_token(1) for _ in range(20)}) == 20


def test_tokens_fit_existing_schemas_and_database_length(manager):
    user_id = 2**63 - 1
    access = manager.create_access_token(user_id)
    refresh = manager.create_refresh_token(user_id)
    assert len(refresh) <= 255
    TokenRefreshRequestSchema(refresh_token=refresh)
    TokenPairResponseSchema(access_token=access, refresh_token=refresh)
    assert manager.decode_refresh_token(refresh)["sub"] == str(user_id)


@pytest.mark.parametrize("user_id", [0, -1, True, False, "1", None, 1.5])
@pytest.mark.parametrize("create", [
    "create_access_token", "create_refresh_token",
])
def test_invalid_user_id_is_rejected(manager, user_id, create):
    with pytest.raises(ValueError, match="positive integer"):
        getattr(manager, create)(user_id)


def test_oversized_token_is_not_created(manager):
    with pytest.raises(ValueError, match="supported length"):
        manager.create_refresh_token(10**100)


@pytest.mark.parametrize("create, expected", [
    ("create_access_token", "decode_refresh_token"),
    ("create_refresh_token", "decode_access_token"),
])
def test_access_and_refresh_cannot_be_interchanged(
    manager, create, expected,
):
    with pytest.raises(tokens.InvalidTokenError):
        token = getattr(manager, create)(1)
        getattr(manager, expected)(token)


@pytest.mark.parametrize("claim", ["sub", "type", "iat", "exp", "jti"])
def test_required_claims_must_exist(manager, valid_payload, claim):
    del valid_payload[claim]
    token = jwt.encode(valid_payload, TEST_KEY, algorithm="HS256")
    with pytest.raises(tokens.InvalidTokenError):
        manager.decode_access_token(token)


@pytest.mark.parametrize("claim, value", [
    ("sub", ""), ("sub", "0"), ("sub", "-1"), ("sub", "abc"),
    ("sub", "1.5"), ("sub", " 1"), ("sub", "١"), ("sub", 1),
    ("sub", None), ("sub", True),
    ("type", "other"), ("type", None),
    ("jti", ""), ("jti", None), ("jti", 1),
    ("iat", None), ("iat", True), ("iat", "123"), ("iat", []),
    ("iat", 123.5), ("iat", float("inf")),
    ("exp", None), ("exp", True), ("exp", []), ("exp", "bad"),
    ("exp", float("inf")), ("exp", float("nan")),
    ("exp", int(NOW.timestamp()) + 0.5),
    ("exp", str(int(NOW.timestamp()) + 60)),
])
def test_invalid_claim_values_are_rejected(
    manager, valid_payload, claim, value,
):
    valid_payload[claim] = value
    token = jwt.encode(valid_payload, TEST_KEY, algorithm="HS256")
    with pytest.raises(tokens.InvalidTokenError):
        manager.decode_access_token(token)


@pytest.mark.parametrize("offset", [-1, 0])
def test_expired_token_including_exact_boundary(
    manager, valid_payload, offset,
):
    valid_payload["iat"] = int(NOW.timestamp()) - 60
    valid_payload["exp"] = int(NOW.timestamp()) + offset
    token = jwt.encode(valid_payload, TEST_KEY, algorithm="HS256")
    with pytest.raises(tokens.TokenExpiredError):
        manager.decode_access_token(token)


def test_future_issued_at_is_rejected(manager, valid_payload):
    valid_payload["iat"] = int(NOW.timestamp()) + 60
    token = jwt.encode(valid_payload, TEST_KEY, algorithm="HS256")
    with pytest.raises(tokens.InvalidTokenError):
        manager.decode_access_token(token)


def test_invalid_lifetime_is_rejected(manager, valid_payload):
    valid_payload["iat"] = int(NOW.timestamp()) - 10
    valid_payload["exp"] = valid_payload["iat"] - 10
    token = jwt.encode(valid_payload, TEST_KEY, algorithm="HS256")
    with pytest.raises(tokens.InvalidTokenError):
        manager.decode_access_token(token)


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", "x" * 256, None, 42])
def test_malformed_tokens_raise_uniform_error(manager, token):
    with pytest.raises(tokens.InvalidTokenError):
        manager.decode_access_token(token)


@pytest.mark.parametrize("algorithm", ["HS384", "HS512"])
def test_disallowed_algorithm_is_rejected(manager, valid_payload, algorithm):
    token = jwt.encode(valid_payload, TEST_KEY, algorithm=algorithm)
    with pytest.raises(tokens.InvalidTokenError):
        manager.decode_access_token(token)


def test_wrong_signing_key_is_rejected(manager, valid_payload):
    token = jwt.encode(
        valid_payload, "different-secret" * 3, algorithm="HS256",
    )
    with pytest.raises(tokens.InvalidTokenError):
        manager.decode_access_token(token)


def test_payload_tampering_is_rejected(manager):
    token = manager.create_access_token(1)
    header, payload, signature = token.split(".")
    data = jwt.get_unverified_claims(token)
    data["sub"] = "2"
    payload = base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    with pytest.raises(tokens.InvalidTokenError):
        manager.decode_access_token(f"{header}.{payload}.{signature}")


def test_unsigned_token_is_rejected(manager):
    token = manager.create_access_token(1)
    _, payload, _ = token.split(".")
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    with pytest.raises(tokens.InvalidTokenError):
        manager.decode_access_token(f"{header}.{payload}.")


@pytest.mark.parametrize("missing", ["access", "refresh", "both"])
def test_missing_keys_fail_without_defaults(jwt_settings, missing):
    if missing in ("access", "both"):
        jwt_settings.JWT_ACCESS_SECRET_KEY = None
    if missing in ("refresh", "both"):
        jwt_settings.JWT_REFRESH_SECRET_KEY = None
    with pytest.raises(ValueError, match="Set JWT_ACCESS_SECRET_KEY"):
        tokens.get_jwt_auth_manager()


@pytest.mark.parametrize("field", [
    "JWT_ACCESS_SECRET_KEY", "JWT_REFRESH_SECRET_KEY",
])
@pytest.mark.parametrize("value", ["", "short", "x" * 31, " " * 32])
def test_settings_reject_short_or_blank_key(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: SecretStr(value)})


def test_settings_reject_identical_keys():
    with pytest.raises(ValidationError, match="must be different"):
        Settings(
            _env_file=None,
            JWT_ACCESS_SECRET_KEY=SecretStr(TEST_KEY),
            JWT_REFRESH_SECRET_KEY=SecretStr(TEST_KEY),
        )


@pytest.mark.parametrize("field, value", [
    ("JWT_ALGORITHM", "none"), ("JWT_ALGORITHM", "HS512"),
    ("ACCESS_TOKEN_EXPIRE_MINUTES", 0),
    ("ACCESS_TOKEN_EXPIRE_MINUTES", -1),
    ("ACCESS_TOKEN_EXPIRE_MINUTES", 1441),
    ("REFRESH_TOKEN_EXPIRE_DAYS", 0),
    ("REFRESH_TOKEN_EXPIRE_DAYS", -1),
    ("REFRESH_TOKEN_EXPIRE_DAYS", 366),
])
def test_settings_reject_invalid_jwt_options(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_settings_hide_key(jwt_settings):
    assert TEST_KEY not in repr(jwt_settings)
    assert TEST_KEY not in jwt_settings.model_dump_json()
    assert REFRESH_KEY not in repr(jwt_settings)
    assert REFRESH_KEY not in jwt_settings.model_dump_json()


def test_settings_allow_jwt_to_remain_unconfigured():
    settings = Settings(
        _env_file=None,
        JWT_ACCESS_SECRET_KEY=None,
        JWT_REFRESH_SECRET_KEY=None,
    )
    assert settings.JWT_ACCESS_SECRET_KEY is None
    assert settings.JWT_REFRESH_SECRET_KEY is None


@pytest.mark.parametrize("token_type, key", [
    ("access", TEST_KEY), ("refresh", REFRESH_KEY),
])
def test_each_token_uses_its_own_key(manager, token_type, key):
    token = getattr(manager, f"create_{token_type}_token")(1)
    payload = jwt.decode(token, key, algorithms=["HS256"])
    assert payload["type"] == token_type


@pytest.mark.parametrize("expected_type, signing_key, wrong_type", [
    ("access", TEST_KEY, "refresh"), ("refresh", REFRESH_KEY, "access"),
])
def test_correct_signature_does_not_bypass_type_check(
    manager, valid_payload, expected_type, signing_key, wrong_type,
):
    valid_payload["type"] = wrong_type
    token = jwt.encode(valid_payload, signing_key, algorithm="HS256")
    with pytest.raises(tokens.InvalidTokenError):
        getattr(manager, f"decode_{expected_type}_token")(token)


@pytest.mark.parametrize("token_type, key", [
    ("access", TEST_KEY), ("refresh", REFRESH_KEY),
])
@pytest.mark.parametrize("offset", [-1, 0])
def test_both_token_types_raise_expired_error(
    manager, valid_payload, token_type, key, offset,
):
    valid_payload["type"] = token_type
    valid_payload["iat"] = int(NOW.timestamp()) - 60
    valid_payload["exp"] = int(NOW.timestamp()) + offset
    token = jwt.encode(valid_payload, key, algorithm="HS256")
    with pytest.raises(tokens.TokenExpiredError, match="Token has expired"):
        getattr(manager, f"decode_{token_type}_token")(token)
