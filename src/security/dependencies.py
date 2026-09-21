from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.database.models import UserGroupEnum, UserModel
from src.repositories.accounts import AccountRepository
from src.security.tokens import (
    InvalidTokenError, JWTAuthManager, get_jwt_auth_manager,
)


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
    jwt_manager: JWTAuthManager = Depends(get_jwt_auth_manager),
) -> UserModel:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_error

    try:
        payload = jwt_manager.decode_access_token(credentials.credentials)

    except InvalidTokenError as error:
        raise credentials_error from error

    user_id = int(payload["sub"])

    if user_id > 2**63 - 1:
        raise credentials_error

    repository = AccountRepository(db)

    try:
        user = await repository.get_user_by_id(user_id)

    except SQLAlchemyError as error:
        await repository.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable.",
        ) from error

    if user is None:
        raise credentials_error

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not active.",
        )

    return user


async def get_current_admin(
    current_user: UserModel = Depends(get_current_user),
) -> UserModel:
    if current_user.group.name != UserGroupEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required.",
        )

    return current_user


async def get_current_moderator(
    current_user: UserModel = Depends(get_current_user),
) -> UserModel:
    if current_user.group.name not in (
        UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN,
    ):
        raise HTTPException(
            403, "Moderator or administrator access is required.",
        )

    return current_user


async def get_profile_owner(
    user_id: int = Path(gt=0, le=2**63 - 1),
    current_user: UserModel = Depends(get_current_user),
) -> UserModel:
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own profile.",
        )

    return current_user
