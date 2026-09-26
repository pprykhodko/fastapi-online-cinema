from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, insert, select

from src.database.models import (
    Base, UserGroupEnum, UserGroupModel, UserModel, UserProfileModel
)


migration = import_module(
    "src.database.alembic.versions.7a92c1d4e608_backfill_user_profiles"
)


@pytest.mark.parametrize("with_users", [True, False])
def test_profile_backfill_preserves_existing_data(with_users):
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            if with_users:
                connection.execute(insert(UserGroupModel), {
                    "id": 1, "name": UserGroupEnum.USER
                })
                connection.execute(insert(UserModel), [
                    {
                        "id": user_id, "email": f"user{user_id}@example.com",
                        "hashed_password": "unused-test-hash", "group_id": 1,
                        "is_active": user_id != 2
                    }
                    for user_id in (1, 2, 3)
                ])
                connection.execute(insert(UserProfileModel), {
                    "user_id": 1, "first_name": "Alice", "info": "Keep me"
                })

            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                profiles = connection.execute(
                    select(UserProfileModel.__table__)
                    .order_by(UserProfileModel.user_id)
                ).mappings().all()
                assert len(profiles) == (3 if with_users else 0)
                if with_users:
                    assert profiles[0]["first_name"] == "Alice"
                    assert profiles[0]["info"] == "Keep me"
                    for profile in profiles[1:]:
                        for field in (
                                "first_name", "last_name", "avatar", "gender",
                                "date_of_birth", "info"
                        ):
                            assert profile[field] is None

                migration.upgrade()
                migration.downgrade()
                remaining = connection.execute(
                    select(UserProfileModel.__table__)
                    .order_by(UserProfileModel.user_id)
                ).mappings().all()
                assert remaining == profiles
    finally:
        engine.dispose()
