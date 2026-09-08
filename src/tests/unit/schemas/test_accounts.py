from datetime import date, datetime, timezone
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.database import (
    GenderEnum,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
    UserProfileModel,
)
from src.schemas.accounts import (
    AccessTokenResponseSchema,
    AccountActivationRequestSchema,
    AccountMessageResponseSchema,
    ActivationResendRequestSchema,
    LogoutRequestSchema,
    PasswordChangeRequestSchema,
    PasswordResetConfirmRequestSchema,
    PasswordResetRequestSchema,
    TokenPairResponseSchema,
    TokenRefreshRequestSchema,
    UserGroupResponseSchema,
    UserGroupUpdateRequestSchema,
    UserLoginRequestSchema,
    UserProfileCreateRequestSchema,
    UserProfileResponseSchema,
    UserProfileUpdateRequestSchema,
    UserRegistrationRequestSchema,
    UserResponseSchema,
)


EMAIL_REQUESTS: list[tuple[type[BaseModel], dict[str, str]]] = [
    (UserRegistrationRequestSchema, {"password": "StrongPassword1!"}),
    (UserLoginRequestSchema, {"password": "existing"}),
    (ActivationResendRequestSchema, {}),
    (PasswordResetRequestSchema, {}),
]
NEW_PASSWORD_REQUESTS: list[
    tuple[type[BaseModel], str, dict[str, str]]
] = [
    (UserRegistrationRequestSchema, "password", {"email": "user@example.com"}),
    (PasswordChangeRequestSchema, "new_password", {"old_password": "old"}),
    (PasswordResetConfirmRequestSchema, "new_password", {"token": "token"}),
]
TOKEN_REQUESTS: list[tuple[type[BaseModel], str, dict[str, str]]] = [
    (AccountActivationRequestSchema, "token", {}),
    (TokenRefreshRequestSchema, "refresh_token", {}),
    (LogoutRequestSchema, "refresh_token", {}),
    (PasswordResetConfirmRequestSchema, "token", {
        "new_password": "StrongPassword1!",
    }),
]


@pytest.mark.parametrize(("schema", "other_fields"), EMAIL_REQUESTS)
def test_email_requests_normalize_addresses(
    schema: type[BaseModel], other_fields: dict[str, str],
) -> None:
    request = schema.model_validate({
        "email": "User@Example.COM", **other_fields,
    })
    assert request.model_dump()["email"] == "user@example.com"


@pytest.mark.parametrize(("schema", "other_fields"), EMAIL_REQUESTS)
@pytest.mark.parametrize("email", ["not-email", "", None, 12, "a" * 256])
def test_email_requests_reject_invalid_addresses(
    schema: type[BaseModel], other_fields: dict[str, str], email: Any,
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({"email": email, **other_fields})


@pytest.mark.parametrize(("schema", "field", "other_fields"),
                         NEW_PASSWORD_REQUESTS)
@pytest.mark.parametrize("password", [
    "Short1!", "lowercase1!", "UPPERCASE1!", "NoDigits!", "NoSpecial1",
    "Aa1!" + "a" * 69, "Aa1!" + "\u044f" * 35,
    "Aa1!" + "\U0001f600" * 18, "StrongPassword1!\x00", None, 123,
])
def test_new_password_requests_reuse_strength_and_byte_validation(
    schema: type[BaseModel], field: str, other_fields: dict[str, str],
    password: Any,
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({field: password, **other_fields})


@pytest.mark.parametrize(("schema", "field", "other_fields"),
                         NEW_PASSWORD_REQUESTS)
@pytest.mark.parametrize("password", [
    "StrongPassword1!", "Aa1!" + "a" * 68,
    "Aa1!" + "\u044f" * 34, "  StrongPassword1!  ",
])
def test_new_password_requests_preserve_valid_secrets(
    schema: type[BaseModel], field: str, other_fields: dict[str, str],
    password: str,
) -> None:
    request = schema.model_validate({field: password, **other_fields})
    assert getattr(request, field) == password
    assert isinstance(getattr(request, field), str)
    assert password not in repr(request)
    assert password not in request.model_dump_json()
    assert field not in request.model_dump()


def test_existing_passwords_do_not_require_new_password_complexity() -> None:
    login = UserLoginRequestSchema.model_validate({
        "email": "user@example.com", "password": "old",
    })
    change = PasswordChangeRequestSchema.model_validate({
        "old_password": "old", "new_password": "StrongPassword1!",
    })
    assert login.password == "old"
    assert change.old_password == "old"
    assert "password" not in login.model_dump()
    assert "old_password" not in change.model_dump()
    assert "new_password" not in change.model_dump()


@pytest.mark.parametrize("password", [
    "", "a" * 73, "\u044f" * 37, "old\x00", None,
])
def test_existing_password_requests_reject_unsupported_bcrypt_inputs(
    password: Any,
) -> None:
    with pytest.raises(ValidationError):
        UserLoginRequestSchema.model_validate({
            "email": "user@example.com", "password": password,
        })
    with pytest.raises(ValidationError):
        PasswordChangeRequestSchema.model_validate({
            "old_password": password, "new_password": "StrongPassword1!",
        })


@pytest.mark.parametrize("field", [
    "group", "group_id", "is_active", "id", "hashed_password", "user_id",
])
def test_registration_rejects_client_supplied_privileged_fields(
    field: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        UserRegistrationRequestSchema.model_validate({
            "email": "user@example.com", "password": "StrongPassword1!",
            field: 1,
        })
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize(("schema", "field", "other_fields"), TOKEN_REQUESTS)
@pytest.mark.parametrize("token", ["", " ", "abc def", "abc\n", "a" * 256,
                                   None, 123])
def test_token_requests_reject_empty_whitespace_and_oversized_tokens(
    schema: type[BaseModel], field: str, other_fields: dict[str, str],
    token: Any,
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({field: token, **other_fields})


@pytest.mark.parametrize(("schema", "field", "other_fields"), TOKEN_REQUESTS)
def test_token_requests_preserve_tokens_and_hide_them_in_repr(
    schema: type[BaseModel], field: str, other_fields: dict[str, str],
) -> None:
    token = "t" * 255
    request = schema.model_validate({field: token, **other_fields})
    assert getattr(request, field) == token
    assert token not in repr(request)


@pytest.mark.parametrize("schema", [
    UserProfileCreateRequestSchema, UserProfileUpdateRequestSchema,
])
def test_profile_requests_accept_optional_fields(
    schema: type[BaseModel],
) -> None:
    profile = schema.model_validate({
        "first_name": "Alex", "last_name": "Smith",
        "avatar": "avatars/user-1.png", "gender": "man",
        "date_of_birth": "2000-01-02", "info": "Movie enthusiast.",
    })
    assert getattr(profile, "gender") is GenderEnum.MAN
    assert getattr(profile, "date_of_birth") == date(2000, 1, 2)
    assert schema.model_validate({}).model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("schema", [
    UserProfileCreateRequestSchema, UserProfileUpdateRequestSchema,
])
@pytest.mark.parametrize(("field", "value"), [
    ("first_name", "a" * 101), ("last_name", "a" * 101),
    ("avatar", "a" * 256), ("gender", "invalid"),
    ("date_of_birth", "2000-02-30"), ("user_id", 1), ("is_active", True),
])
def test_profile_requests_enforce_fields_and_database_limits(
    schema: type[BaseModel], field: str, value: Any,
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({field: value})


def test_profile_patch_distinguishes_omitted_fields_from_null() -> None:
    omitted = UserProfileUpdateRequestSchema.model_validate({})
    cleared = UserProfileUpdateRequestSchema.model_validate({"avatar": None})
    changed = UserProfileUpdateRequestSchema.model_validate({
        "first_name": "Alex", "info": None,
    })
    assert omitted.model_dump(exclude_unset=True) == {}
    assert cleared.model_dump(exclude_unset=True) == {"avatar": None}
    assert changed.model_dump(exclude_unset=True) == {
        "first_name": "Alex", "info": None,
    }


def test_profile_field_lengths_match_database_boundaries() -> None:
    profile = UserProfileCreateRequestSchema.model_validate({
        "first_name": "a" * 100, "last_name": "b" * 100,
        "avatar": "a" * 255, "info": "a" * 1000,
    })
    assert len(profile.first_name or "") == 100
    assert len(profile.avatar or "") == 255


@pytest.mark.parametrize("group", list(UserGroupEnum))
def test_admin_group_update_accepts_only_known_group_names(
    group: UserGroupEnum,
) -> None:
    request = UserGroupUpdateRequestSchema.model_validate({
        "group": group.value,
    })
    assert request.group is group


@pytest.mark.parametrize("group", ["owner", "ADMIN", 1, None])
def test_admin_group_update_rejects_unknown_groups(group: Any) -> None:
    with pytest.raises(ValidationError):
        UserGroupUpdateRequestSchema.model_validate({"group": group})


def test_user_response_reads_orm_without_exposing_hashes_or_tokens() -> None:
    now = datetime.now(timezone.utc)
    group = UserGroupModel(id=1, name=UserGroupEnum.USER)
    user = UserModel(
        id=2, email="user@example.com", group=group,
        _hashed_password="must-never-be-returned", is_active=False,
        created_at=now, updated_at=now,
    )
    response = UserResponseSchema.model_validate(user)
    data = response.model_dump(mode="json")
    assert set(data) == {
        "id", "email", "is_active", "created_at", "updated_at", "group",
    }
    assert data["group"] == {"id": 1, "name": "user"}
    assert "must-never-be-returned" not in response.model_dump_json()


def test_profile_response_reads_orm_and_serializes_dates_and_enums() -> None:
    profile = UserProfileModel(
        id=3, user_id=2, gender=GenderEnum.WOMAN,
        date_of_birth=date(2000, 1, 2),
    )
    response = UserProfileResponseSchema.model_validate(profile)
    assert response.model_dump(mode="json") == {
        "id": 3, "user_id": 2, "first_name": None, "last_name": None,
        "avatar": None, "gender": "woman", "date_of_birth": "2000-01-02",
        "info": None,
    }


@pytest.mark.parametrize("invalid_id", [0, -1])
def test_group_response_rejects_non_positive_ids(invalid_id: int) -> None:
    with pytest.raises(ValidationError):
        UserGroupResponseSchema.model_validate({
            "id": invalid_id, "name": "user",
        })


def test_token_responses_return_plain_tokens_and_bearer_type() -> None:
    pair = TokenPairResponseSchema.model_validate({
        "access_token": "header.payload.signature", "refresh_token": "refresh",
    })
    assert pair.model_dump() == {
        "access_token": "header.payload.signature",
        "refresh_token": "refresh", "token_type": "bearer",
    }
    access = AccessTokenResponseSchema.model_validate({
        "access_token": "access",
    })
    assert access.model_dump() == {
        "access_token": "access", "token_type": "bearer",
    }
    with pytest.raises(ValidationError):
        AccessTokenResponseSchema.model_validate({
            "access_token": "access", "token_type": "Basic",
        })


def test_acknowledgement_schema_requires_a_message() -> None:
    response = AccountMessageResponseSchema(message="Request accepted.")
    assert response.model_dump() == {"message": "Request accepted."}
    with pytest.raises(ValidationError):
        AccountMessageResponseSchema(message="")


def test_json_schema_documents_passwords_and_input_restrictions() -> None:
    registration = UserRegistrationRequestSchema.model_json_schema()
    assert registration["additionalProperties"] is False
    assert registration["properties"]["email"]["format"] == "email"
    password = registration["properties"]["password"]
    assert password["writeOnly"] is True
    assert password["format"] == "password"
    assert password["minLength"] == 8
    assert "72 bytes" in password["description"]
    activation = AccountActivationRequestSchema.model_json_schema()
    assert activation["properties"]["token"]["maxLength"] == 255
    assert activation["properties"]["token"]["writeOnly"] is True
