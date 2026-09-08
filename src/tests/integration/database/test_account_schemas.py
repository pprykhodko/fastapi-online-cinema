from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.database import (
    ActivationTokenModel,
    GenderEnum,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserModel,
    UserProfileModel,
)
from src.schemas.accounts import (
    UserProfileResponseSchema,
    UserProfileUpdateRequestSchema,
    UserResponseSchema,
)


def test_persisted_user_response_does_not_expose_tokens_or_password_hash(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
) -> None:
    user_id = catalog_users[0].id
    db_session.add_all([
        ActivationTokenModel(user_id=user_id, token="private-activation"),
        PasswordResetTokenModel(user_id=user_id, token="private-reset"),
        RefreshTokenModel.create(user_id, 7, "private-refresh"),
    ])
    db_session.commit()
    db_session.expunge_all()
    user = db_session.scalars(
        select(UserModel).options(selectinload(UserModel.group))
        .where(UserModel.id == user_id)
    ).one()
    # Serialize without a session or lazy-loading token relationships.
    db_session.expunge_all()

    response = UserResponseSchema.model_validate(user)
    data = response.model_dump(mode="json")
    assert data["id"] == user_id
    assert data["is_active"] is False
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert data["group"]["name"] == "user"
    assert set(data) == {
        "id", "email", "is_active", "created_at", "updated_at", "group",
    }
    serialized = response.model_dump_json()
    for secret in (
        "unused-in-database-tests", "private-activation", "private-reset",
        "private-refresh",
    ):
        assert secret not in serialized


def test_profile_patch_updates_only_supplied_fields_and_can_clear_values(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
) -> None:
    profile = UserProfileModel(
        user_id=catalog_users[0].id,
        first_name="Alex", last_name="Smith", avatar="avatars/original.png",
        gender=GenderEnum.WOMAN, date_of_birth=date(2000, 1, 2),
    )
    db_session.add(profile)
    db_session.commit()
    profile_id = profile.id
    patch = UserProfileUpdateRequestSchema.model_validate({
        "first_name": "Sam", "avatar": None,
    })
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db_session.commit()
    db_session.expunge_all()

    persisted = db_session.get(UserProfileModel, profile_id)
    response = UserProfileResponseSchema.model_validate(persisted)
    assert response.first_name == "Sam"
    assert response.last_name == "Smith"
    assert response.avatar is None
    assert response.gender is GenderEnum.WOMAN
    assert response.date_of_birth == date(2000, 1, 2)
