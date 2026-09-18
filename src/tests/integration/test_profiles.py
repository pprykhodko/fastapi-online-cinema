import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from src.database.models import (
    UserGroupEnum, UserGroupModel, UserModel, UserProfileModel,
)
from src.main import app
from src.repositories.profiles import ProfileRepository


PREFIX = "/api/v1/profiles"


@pytest_asyncio.fixture
async def profile_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        other = UserModel(
            email="other@example.com", group_id=user.group_id,
            _hashed_password="unused-test-hash", is_active=True,
        )
        db.add(other)
        await db.flush()
        other_id = other.id
        db.add_all([
            UserProfileModel(
                user_id=user_id, first_name="Alex", last_name="Smith",
                avatar="avatars/existing.png", info="Movie fan",
            ),
            UserProfileModel(user_id=other_id),
        ])
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}",
    }
    return client, sessions, user_id, other_id, headers


@pytest.mark.asyncio
async def test_get_own_and_other_profile(profile_api):
    client, _, user_id, other_id, headers = profile_api
    for target_id in (user_id, other_id):
        response = await client.get(f"{PREFIX}/{target_id}/", headers=headers)
        assert response.status_code == 200
        assert response.json()["user_id"] == target_id
        assert set(response.json()) == {
            "id", "user_id", "first_name", "last_name", "avatar",
            "gender", "date_of_birth", "info",
        }


@pytest.mark.asyncio
async def test_patch_profile_changes_only_supplied_fields(profile_api):
    client, sessions, user_id, _, headers = profile_api
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers, json={
            "first_name": "Sam", "gender": "woman",
            "date_of_birth": "2000-01-02", "info": None,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "Sam"
    assert data["last_name"] == "Smith"
    assert data["avatar"] == "avatars/existing.png"
    assert data["gender"] == "woman"
    assert data["date_of_birth"] == "2000-01-02"
    assert data["info"] is None
    async with sessions() as db:
        profile = await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        ))
        assert profile.first_name == "Sam"
        assert profile.info is None
    empty = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers, json={},
    )
    assert empty.json() == data


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(UserGroupEnum))
async def test_even_admin_cannot_edit_another_profile(profile_api, role):
    client, sessions, user_id, other_id, headers = profile_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        group = await db.get(UserGroupModel, user.group_id)
        group.name = role
        await db.commit()
    response = await client.patch(
        f"{PREFIX}/{other_id}/", headers=headers,
        json={"first_name": "Changed"},
    )
    assert response.status_code == 403
    async with sessions() as db:
        profile = await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == other_id,
        ))
        assert profile.first_name is None


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize("credentials", [None, "Bearer invalid"])
async def test_profiles_require_access_token(profile_api, method, credentials):
    client, _, user_id, _, _ = profile_api
    headers = {} if credentials is None else {"Authorization": credentials}
    response = await client.request(
        method, f"{PREFIX}/{user_id}/", headers=headers,
        **({"json": {}} if method == "PATCH" else {}),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_inactive_caller_cannot_access_profiles(profile_api, method):
    client, sessions, user_id, _, headers = profile_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        user.is_active = False
        await db.commit()
    response = await client.request(
        method, f"{PREFIX}/{user_id}/", headers=headers,
        **({"json": {}} if method == "PATCH" else {}),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_inactive_or_missing_target_is_not_found(profile_api):
    client, sessions, _, other_id, headers = profile_api
    async with sessions() as db:
        user = await db.get(UserModel, other_id)
        user.is_active = False
        await db.commit()
    for target_id in (other_id, 9999):
        response = await client.get(f"{PREFIX}/{target_id}/", headers=headers)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_missing_profile_is_not_created_by_patch(profile_api):
    client, sessions, user_id, _, headers = profile_api
    async with sessions() as db:
        await db.execute(delete(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        ))
        await db.commit()
    for method in ("GET", "PATCH"):
        response = await client.request(
            method, f"{PREFIX}/{user_id}/", headers=headers,
            **({"json": {"first_name": "Sam"}} if method == "PATCH" else {}),
        )
        assert response.status_code == 404
    async with sessions() as db:
        assert await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        )) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    {"first_name": "a" * 101}, {"last_name": "b" * 101},
    {"gender": "invalid"}, {"date_of_birth": "2000-02-30"},
    {"user_id": 123}, {"is_active": True}, {"avatar": "untrusted.png"},
])
async def test_invalid_patch_leaves_profile_unchanged(profile_api, data):
    client, _, user_id, _, headers = profile_api
    before = await client.get(f"{PREFIX}/{user_id}/", headers=headers)
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers, json=data,
    )
    assert response.status_code == 422
    after = await client.get(f"{PREFIX}/{user_id}/", headers=headers)
    assert before.json() == after.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [0, -1, 2**63, "abc"])
async def test_invalid_user_id(profile_api, user_id):
    client, _, _, _, headers = profile_api
    response = await client.get(f"{PREFIX}/{user_id}/", headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_failed_commit_rolls_back_profile(profile_api, monkeypatch):
    client, sessions, user_id, _, headers = profile_api

    async def fail_commit(self):
        await self.db.flush()
        raise OperationalError("private database error", {}, Exception())

    monkeypatch.setattr(ProfileRepository, "commit", fail_commit)
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers, json={"first_name": "Sam"},
    )
    assert response.status_code == 503
    assert "private" not in response.text
    async with sessions() as db:
        profile = await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        ))
        assert profile.first_name == "Alex"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_profile_query_failure(profile_api, monkeypatch, method):
    client, _, user_id, _, headers = profile_api

    async def fail_query(self, user_id):
        raise OperationalError("private database error", {}, Exception())

    monkeypatch.setattr(ProfileRepository, "get_profile", fail_query)
    response = await client.request(
        method, f"{PREFIX}/{user_id}/", headers=headers,
        **({"json": {}} if method == "PATCH" else {}),
    )
    assert response.status_code == 503
    assert "private" not in response.text


def test_profile_openapi_contract():
    paths = app.openapi()["paths"]
    assert set(paths[f"{PREFIX}/{{user_id}}/"]) == {"get", "patch"}
    assert PREFIX + "/" not in paths
    for method in ("get", "patch"):
        operation = paths[f"{PREFIX}/{{user_id}}/"][method]
        assert operation["security"]
        assert operation["description"]
        assert {"200", "401", "403", "404", "422", "503"} <= set(
            operation["responses"],
        )
