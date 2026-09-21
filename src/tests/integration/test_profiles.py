from datetime import date
from io import BytesIO
from unittest.mock import Mock

from PIL import Image
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from src.database.models import (
    UserGroupEnum, UserGroupModel, UserModel, UserProfileModel,
)
from src.main import app
from src.repositories.profiles import ProfileRepository
from src.storages.s3 import S3Storage, StorageError
from src.core.config import Settings, get_settings


PREFIX = "/api/v1/profiles"


@pytest_asyncio.fixture
async def profile_api(login_api, monkeypatch):
    monkeypatch.setattr(S3Storage, "get_file_url", lambda self, key: key)
    monkeypatch.setattr(S3Storage, "upload_file", Mock())
    monkeypatch.setattr(S3Storage, "delete_file", Mock())
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
    patch = paths[f"{PREFIX}/{{user_id}}/"]["patch"]
    content = patch["requestBody"]["content"]
    assert {"application/json", "multipart/form-data"} <= set(content)


@pytest.fixture
def png_bytes():
    output = BytesIO()
    Image.new("RGB", (10, 10), "red").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_form_updates_all_declared_profile_fields(profile_api):
    client, _, user_id, _, headers = profile_api
    fields = {
        "first_name": "Sam", "last_name": "Jones", "gender": "man",
        "date_of_birth": "2000-01-02", "info": "New biography",
    }
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers, data=fields,
    )
    assert response.status_code == 200
    for key, value in fields.items():
        assert response.json()[key] == value

    unchanged = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers,
        data={"first_name": "", "gender": "", "date_of_birth": ""},
    )
    assert unchanged.status_code == 200
    assert unchanged.json() == response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("multipart", [True, False])
@pytest.mark.parametrize("birthday", ["1999-01-02", ""])
async def test_empty_form_fields_preserve_profile(
    profile_api, multipart, birthday,
):
    client, sessions, user_id, _, headers = profile_api
    async with sessions() as db:
        profile = await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        ))
        profile.date_of_birth = date(2000, 1, 2)
        await db.commit()
    before = await client.get(f"{PREFIX}/{user_id}/", headers=headers)
    fields = {
        "first_name": "", "last_name": "", "gender": "",
        "date_of_birth": birthday, "info": "", "avatar": "",
    }
    if multipart:
        response = await client.patch(
            f"{PREFIX}/{user_id}/", headers=headers,
            files={key: (None, value) for key, value in fields.items()},
        )
    else:
        response = await client.patch(
            f"{PREFIX}/{user_id}/", headers=headers, data=fields,
        )
    expected = before.json()
    if birthday:
        expected["date_of_birth"] = birthday
    assert response.status_code == 200
    assert response.json() == expected
    after = await client.get(f"{PREFIX}/{user_id}/", headers=headers)
    assert after.json() == expected
    S3Storage.upload_file.assert_not_called()
    S3Storage.delete_file.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("avatar", [None, ""])
async def test_text_update_preserves_avatar(profile_api, avatar):
    client, sessions, user_id, _, headers = profile_api
    fields = {
        "first_name": "Sam", "last_name": "Jones", "gender": "man",
        "date_of_birth": "2000-01-02", "info": "New biography",
    }
    files = {key: (None, value) for key, value in fields.items()}
    if avatar is not None:
        files["avatar"] = (None, avatar)
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers, files=files,
    )
    assert response.status_code == 200
    for key, value in fields.items():
        assert response.json()[key] == value
    assert response.json()["avatar"] == "avatars/existing.png"
    async with sessions() as db:
        profile = await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        ))
        assert profile.avatar == "avatars/existing.png"
        assert profile.first_name == "Sam"
    S3Storage.upload_file.assert_not_called()
    S3Storage.delete_file.assert_not_called()


@pytest.mark.asyncio
async def test_nonempty_avatar_text_is_rejected(profile_api):
    client, _, user_id, _, headers = profile_api
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers,
        files={"avatar": (None, "not-a-file")},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "avatar"]
    S3Storage.upload_file.assert_not_called()
    S3Storage.delete_file.assert_not_called()


@pytest.mark.asyncio
async def test_upload_avatar_and_text_together(profile_api, png_bytes):
    client, sessions, user_id, _, headers = profile_api
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers,
        data={"first_name": "Sam", "info": "", "gender": "woman"},
        files={"avatar": ("../../unsafe.png", png_bytes, "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "Sam"
    assert data["last_name"] == "Smith"
    assert data["gender"] == "woman"
    assert data["info"] == "Movie fan"
    key = data["avatar"]
    assert key.startswith(f"avatars/{user_id}/") and key.endswith(".png")
    assert "unsafe" not in key
    uploaded, saved_key, mime = S3Storage.upload_file.call_args.args
    assert saved_key == key
    assert mime == "image/png"
    with Image.open(BytesIO(uploaded)) as image:
        assert image.size == (10, 10)
    async with sessions() as db:
        profile = await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        ))
        assert profile.avatar == key
    S3Storage.delete_file.assert_not_called()
    # Replacing an avatar generated by this API removes the previous file.
    second = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers,
        files={"avatar": ("new.png", png_bytes, "image/png")},
    )
    assert second.status_code == 200
    assert second.json()["avatar"] != key
    S3Storage.delete_file.assert_called_once_with(key)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["upload", "commit", "url"])
async def test_avatar_failure_preserves_old_profile(
    profile_api, png_bytes, monkeypatch, failure,
):
    client, sessions, user_id, _, headers = profile_api
    if failure == "commit":
        async def fail_commit(self):
            await self.db.flush()
            raise OperationalError("private", {}, Exception())
        monkeypatch.setattr(ProfileRepository, "commit", fail_commit)
    else:
        method = "upload_file" if failure == "upload" else "get_file_url"
        monkeypatch.setattr(
            S3Storage, method, Mock(side_effect=StorageError("private")),
        )
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers, data={"first_name": "Sam"},
        files={"avatar": ("a.png", png_bytes, "image/png")},
    )
    assert response.status_code == 503
    assert "private" not in response.text
    deleted_key = S3Storage.delete_file.call_args.args[0]
    assert deleted_key.startswith(f"avatars/{user_id}/")
    async with sessions() as db:
        profile = await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        ))
        assert profile.avatar == "avatars/existing.png"
        assert profile.first_name == "Alex"


@pytest.mark.asyncio
async def test_avatar_cleanup_failure_does_not_fail_saved_update(
    profile_api, png_bytes, monkeypatch, caplog,
):
    client, sessions, user_id, _, headers = profile_api
    async with sessions() as db:
        profile = await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        ))
        profile.avatar = f"avatars/{user_id}/old.png"
        await db.commit()
    monkeypatch.setattr(
        S3Storage, "delete_file", Mock(side_effect=StorageError("private")),
    )
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers,
        files={"avatar": ("a.png", png_bytes, "image/png")},
    )
    assert response.status_code == 200
    assert "could not be removed" in caplog.text
    assert "private" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("content,mime", [
    (b"", "image/png"), (b"not an image", "image/png"),
    (b"<svg></svg>", "image/svg+xml"),
])
async def test_invalid_avatar_is_not_uploaded(profile_api, content, mime):
    client, _, user_id, _, headers = profile_api
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers,
        files={"avatar": ("a.png", content, mime)},
    )
    assert response.status_code == 422
    S3Storage.upload_file.assert_not_called()


@pytest.mark.asyncio
async def test_oversized_avatar(profile_api, png_bytes, monkeypatch):
    client, _, user_id, _, headers = profile_api
    monkeypatch.setitem(
        app.dependency_overrides, get_settings,
        lambda: Settings(_env_file=None, AVATAR_MAX_BYTES=10),
    )
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers,
        files={"avatar": ("a.png", png_bytes, "image/png")},
    )
    assert response.status_code == 413
    S3Storage.upload_file.assert_not_called()


@pytest.mark.asyncio
async def test_upload_to_another_profile_is_forbidden(profile_api, png_bytes):
    client, _, _, other_id, headers = profile_api
    response = await client.patch(
        f"{PREFIX}/{other_id}/", headers=headers,
        files={"avatar": ("a.png", png_bytes, "image/png")},
    )
    assert response.status_code == 403
    S3Storage.upload_file.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [
    {"first_name": "a" * 101}, {"gender": "invalid"},
    {"date_of_birth": "invalid"}, {"user_id": "999"},
])
async def test_invalid_form_does_not_upload(profile_api, png_bytes, fields):
    client, _, user_id, _, headers = profile_api
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers, data=fields,
        files={"avatar": ("a.png", png_bytes, "image/png")},
    )
    assert response.status_code == 422
    S3Storage.upload_file.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mime,content,expected", [
    ("application/json", "{broken", 422),
    ("text/plain", "hello", 415),
])
async def test_bad_request_body(profile_api, mime, content, expected):
    client, _, user_id, _, headers = profile_api
    response = await client.patch(
        f"{PREFIX}/{user_id}/", content=content,
        headers={**headers, "Content-Type": mime},
    )
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_processed_avatar_size_limit(
    profile_api, png_bytes, monkeypatch,
):
    client, _, user_id, _, headers = profile_api
    monkeypatch.setitem(
        app.dependency_overrides, get_settings,
        lambda: Settings(_env_file=None, AVATAR_MAX_BYTES=1000),
    )
    monkeypatch.setattr(
        "src.services.profiles.validate_avatar",
        lambda data, mime: (b"x" * 1001, "png"),
    )
    response = await client.patch(
        f"{PREFIX}/{user_id}/", headers=headers,
        files={"avatar": ("a.png", png_bytes, "image/png")},
    )
    assert response.status_code == 413
    S3Storage.upload_file.assert_not_called()


@pytest.mark.asyncio
async def test_get_returns_signed_url_without_storing_it(
    profile_api, monkeypatch,
):
    client, sessions, user_id, _, headers = profile_api
    url = "https://storage.test/avatar?signature=" + "x" * 300
    monkeypatch.setattr(S3Storage, "get_file_url", Mock(return_value=url))
    response = await client.get(f"{PREFIX}/{user_id}/", headers=headers)
    assert response.status_code == 200
    assert response.json()["avatar"] == url
    async with sessions() as db:
        profile = await db.scalar(select(UserProfileModel).where(
            UserProfileModel.user_id == user_id,
        ))
        assert profile.avatar == "avatars/existing.png"
