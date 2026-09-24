from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


@asynccontextmanager
async def database_errors(repository, detail: str, conflict_detail: str | None = None) -> AsyncIterator[None]:
    """
    Handle the whole DB operation, including queries, flush and commit.

    Does not commit automatically: the service chooses when to save.
    All repositories in the operation must use the same session.
    """
    try:
        yield

    except IntegrityError:
        await repository.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if conflict_detail else status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=conflict_detail or detail
        )

    except SQLAlchemyError:
        await repository.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail
        )

    except Exception:
        await repository.rollback()
        raise
