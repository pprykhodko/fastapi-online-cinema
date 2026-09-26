from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.database import get_db
from src.database.models import UserModel
from src.repositories.accounts import AccountRepository


docs_auth = HTTPBasic(realm="Online Cinema documentation")


async def get_docs_user(
        credentials: HTTPBasicCredentials = Depends(docs_auth),
        db: AsyncSession = Depends(get_db)
) -> UserModel:
    repository = AccountRepository(db)

    try:
        user = await repository.get_user_by_email(credentials.username.strip().lower())

    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable"
        )

    if user is None or not await run_in_threadpool(
            user.verify_password,
            credentials.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={
                "WWW-Authenticate": 'Basic realm="Online Cinema documentation"'
            }
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not active"
        )

    return user
