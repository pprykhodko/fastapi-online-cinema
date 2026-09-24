from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import (
    CertificationModel, CommentLikeModel, MovieCommentModel, MovieModel,
    UserModel,
)
from src.main import app
from src.notifications.queue import EmailQueue, EmailQueueError, get_email_queue
from src.repositories.comments import CommentRepository


PATH = "/api/v1/movies/1/comments/"
LIKE = "/api/v1/comments/1/like/"


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["reply", "like"])
async def test_queue_failure_preserves_saved_comment_activity(comments_api, monkeypatch, event):
    client, sessions, headers, _, user_id = comments_api
    monkeypatch.setitem(app.dependency_overrides, get_email_queue, lambda: EmailQueue())

    async def check_saved_activity(kind, email, data):
        async with sessions() as db:
            model = MovieCommentModel if event == "reply" else CommentLikeModel
            assert await db.scalar(select(model).where(model.user_id == user_id)) is not None
        raise EmailQueueError("Broker unavailable")

    enqueue = AsyncMock(side_effect=check_saved_activity)
    monkeypatch.setattr(EmailQueue, "_enqueue", enqueue)
    if event == "reply":
        response = await client.post(PATH, headers=headers, json={"content": "Reply", "parent_id": 1})
    else:
        response = await client.put(LIKE, headers=headers)
    assert response.status_code == 201
    enqueue.assert_awaited_once()


@pytest_asyncio.fixture
async def comments_api(login_api, monkeypatch):
    client, sessions, manager, user_id = login_api
    sender = AsyncMock(spec=EmailQueue)
    monkeypatch.setitem(
        app.dependency_overrides, get_email_queue, lambda: sender,
    )
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        other = UserModel(
            email="author@example.com", group_id=user.group_id,
            _hashed_password="unused", is_active=True,
        )
        certification = CertificationModel(name="PG")
        db.add(other)
        for movie_id in (1, 2):
            db.add(MovieModel(
                id=movie_id, name=f"Movie {movie_id}", year=2020, time=90,
                imdb=8, votes=5, description="Story", price=Decimal("5"),
                certification=certification,
            ))
        await db.flush()
        db.add(MovieCommentModel(
            id=1, user_id=other.id, movie_id=1, content="Original",
        ))
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}",
    }
    return client, sessions, headers, sender, user_id


@pytest.mark.asyncio
async def test_comments_replies_and_pagination(comments_api):
    client, _, headers, sender, user_id = comments_api
    result = await client.post(PATH, headers=headers, json={"content": " Hi "})
    assert result.status_code == 201
    assert result.json()["content"] == "Hi"
    assert result.json()["user_id"] == user_id
    assert result.json()["parent_id"] is None
    sender.send_comment_notification.assert_not_awaited()
    reply = await client.post(PATH, headers=headers, json={
        "content": "Reply", "parent_id": 1,
    })
    assert reply.status_code == 201
    assert reply.json()["parent_id"] == 1
    sender.send_comment_notification.assert_awaited_once_with(
        "author@example.com", "Movie 1", 1, "reply",
    )
    own_reply = await client.post(PATH, headers=headers, json={
        "content": "Own reply", "parent_id": reply.json()["id"],
    })
    assert own_reply.status_code == 201
    assert sender.send_comment_notification.await_count == 1
    listing = (await client.get(PATH)).json()
    assert listing["total"] == 4
    assert [item["id"] for item in listing["items"]] == [1, 2, 3, 4]
    page = (await client.get(PATH, params={"page": 2, "per_page": 2})).json()
    assert page["total"] == 4
    assert [item["id"] for item in page["items"]] == [3, 4]
    assert (await client.get(PATH, params={"page": 9})).json()["items"] == []
    empty = await client.get("/api/v1/movies/2/comments/")
    assert empty.json()["total"] == 0


@pytest.mark.asyncio
async def test_like_lifecycle_and_isolation(comments_api):
    client, sessions, headers, sender, user_id = comments_api
    async with sessions() as db:
        comment = await db.get(MovieCommentModel, 1)
        db.add(CommentLikeModel(user_id=comment.user_id, comment_id=1))
        await db.commit()
    assert (await client.delete(LIKE, headers=headers)).status_code == 404
    created = await client.put(LIKE, headers=headers)
    assert created.status_code == 201
    assert created.json()["user_id"] == user_id
    repeated = await client.put(LIKE, headers=headers)
    assert repeated.status_code == 200
    assert repeated.json() == created.json()
    sender.send_comment_notification.assert_awaited_once_with(
        "author@example.com", "Movie 1", 1, "like",
    )
    async with sessions() as db:
        movie = await db.get(MovieModel, 1)
        movie.is_deleted = True
        await db.commit()
    removed = await client.delete(LIKE, headers=headers)
    assert removed.status_code == 204 and removed.content == b""
    assert (await client.delete(LIKE, headers=headers)).status_code == 404
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(
            CommentLikeModel,
        )) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("inactive_author", [True, False])
async def test_skip_self_or_inactive_author_email(
    comments_api, inactive_author,
):
    client, sessions, headers, sender, user_id = comments_api
    async with sessions() as db:
        comment = await db.get(MovieCommentModel, 1)
        if inactive_author:
            author = await db.get(UserModel, comment.user_id)
            author.is_active = False
        else:
            comment.user_id = user_id
        await db.commit()
    assert (await client.put(LIKE, headers=headers)).status_code == 201
    assert (await client.post(PATH, headers=headers, json={
        "content": "Reply", "parent_id": 1,
    })).status_code == 201
    sender.send_comment_notification.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("parent_id", [999, 1])
async def test_invalid_parent(comments_api, parent_id):
    client, _, headers, sender, _ = comments_api
    result = await client.post(
        "/api/v1/movies/2/comments/", headers=headers,
        json={"content": "Reply", "parent_id": parent_id},
    )
    assert result.status_code == 404
    sender.send_comment_notification.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {}, {"content": " "}, {"content": 123},
    {"content": "Hi", "parent_id": 0},
    {"content": "Hi", "parent_id": True},
    {"content": "Hi", "parent_id": 2**40},
    {"content": "Hi", "user_id": 42},
])
async def test_invalid_comment(comments_api, body):
    client, _, headers, _, _ = comments_api
    result = await client.post(PATH, headers=headers, json=body)
    assert result.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    {"page": 0}, {"page": 2**100}, {"per_page": 101}, {"unexpected": 1},
])
async def test_invalid_pagination(comments_api, query):
    client, _, _, _, _ = comments_api
    assert (await client.get(PATH, params=query)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("POST", PATH), ("PUT", LIKE),
                                         ("DELETE", LIKE)])
@pytest.mark.parametrize("auth", ["missing", "invalid", "inactive"])
async def test_authentication(comments_api, method, path, auth):
    client, sessions, headers, _, user_id = comments_api
    if auth == "inactive":
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            user.is_active = False
            await db.commit()
    else:
        headers = {} if auth == "missing" else {"Authorization": "Bearer bad"}
    result = await client.request(method, path, headers=headers,
                                  json={"content": "Hi"})
    assert result.status_code == (403 if auth == "inactive" else 401)


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", [True, False])
async def test_unavailable_movie(comments_api, deleted):
    client, sessions, headers, sender, _ = comments_api
    if deleted:
        async with sessions() as db:
            movie = await db.get(MovieModel, 1)
            movie.is_deleted = True
            await db.commit()
    path = PATH if deleted else "/api/v1/movies/999/comments/"
    assert (await client.get(path)).status_code == 404
    assert (await client.post(path, headers=headers,
                              json={"content": "Hi"})).status_code == 404
    like_path = LIKE if deleted else "/api/v1/comments/999/like/"
    assert (await client.put(like_path, headers=headers)).status_code == 404
    sender.send_comment_notification.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,operation", [
    ("GET", PATH, "list_comments"),
    ("POST", PATH, "commit"),
    ("PUT", LIKE, "commit"),
    ("DELETE", LIKE, "delete_like"),
])
async def test_database_failure_rolls_back(
    comments_api, monkeypatch, method, path, operation,
):
    client, sessions, headers, sender, _ = comments_api
    monkeypatch.setattr(CommentRepository, operation,
                        AsyncMock(side_effect=SQLAlchemyError("private")))
    result = await client.request(method, path, headers=headers,
                                  json={"content": "Hi", "parent_id": 1})
    assert result.status_code == 503
    assert "private" not in result.text
    sender.send_comment_notification.assert_not_awaited()
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(
            MovieCommentModel,
        )) == 1
        assert await db.scalar(select(func.count()).select_from(
            CommentLikeModel,
        )) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("POST", PATH), ("PUT", LIKE)])
async def test_integrity_conflict(comments_api, monkeypatch, method, path):
    client, _, headers, sender, _ = comments_api
    monkeypatch.setattr(CommentRepository, "save", AsyncMock(
        side_effect=IntegrityError("private", {}, Exception()),
    ))
    result = await client.request(method, path, headers=headers,
                                  json={"content": "Hi", "parent_id": 1})
    assert result.status_code == 409
    sender.send_comment_notification.assert_not_awaited()
