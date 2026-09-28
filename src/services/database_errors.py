from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


@asynccontextmanager
async def database_errors(
        repository,
        detail: str,
        conflict_detail: str | None = None
) -> AsyncIterator[None]:
    """
    Roll back failed database operations and translate database errors to HTTP errors.

    Does not commit automatically. All repositories must share one session.

    Args:
        repository: Repository used for database operations and the shared transaction.
        detail (str): Public error message for database failures.
        conflict_detail (str | None): Optional conflict message; enables HTTP 409 for
            integrity errors.

    Yields:
        None: Control while the application or guarded operation runs.

    Raises:
        HTTPException: A database failure becomes HTTP 409 or 503 after rollback.
    """
    try:
        yield

    except IntegrityError:
        await repository.rollback()
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
                if conflict_detail else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
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
