import pytest
from sqlalchemy import Enum, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from src.database import (
    Base,
    GenderEnum,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
    UserProfileModel
)


@pytest.mark.parametrize(
    ("table_name", "column", "length"),
    [
        ("user_groups", "name", 50),
        ("user_profiles", "gender", 10)
    ]
)
def test_account_enums_use_assignment_varchar_sizes(
        table_name: str,
        column: str,
        length: int
) -> None:
    table = Base.metadata.tables[table_name]
    column_type = table.c[column].type
    assert isinstance(column_type, Enum)
    assert column_type.native_enum is False
    assert column_type.length == length
    assert column_type.create_constraint is True
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert f"{column} VARCHAR({length})" in ddl


@pytest.mark.parametrize("group_name", list(UserGroupEnum))
def test_groups_preserve_python_enum_after_database_round_trip(
        db_session: Session,
        group_name: UserGroupEnum
) -> None:
    group = UserGroupModel(name=group_name)
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    assert group.name is group_name


@pytest.mark.parametrize("gender", [*GenderEnum, None])
def test_profile_gender_preserves_optional_enum(
        db_session: Session,
        catalog_users: tuple[UserModel, UserModel],
        gender: GenderEnum | None
) -> None:
    profile = UserProfileModel(user_id=catalog_users[0].id, gender=gender)
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    assert profile.gender is gender


@pytest.mark.parametrize("target", ["group", "gender"])
def test_database_rejects_unknown_account_enum_values(
        db_session: Session,
        catalog_users: tuple[UserModel, UserModel],
        target: str
) -> None:
    profile = UserProfileModel(user_id=catalog_users[0].id)
    db_session.add(profile)
    db_session.commit()
    statements = {
        "group": "UPDATE user_groups SET name = 'UNKNOWN'",
        "gender": "UPDATE user_profiles SET gender = 'UNKNOWN'"
    }
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text(statements[target]))
