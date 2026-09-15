from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.database.models import (
    ActivationTokenModel,
    CartModel,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
)
from src.schemas.accounts import (
    AccountActivationRequestSchema,
    AccountMessageResponseSchema,
    UserRegistrationRequestSchema,
    UserResponseSchema,
)
from src.schemas.common import ErrorResponseSchema


router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user",
    description=(
        "Register an inactive USER account with an email and a strong "
        "password. Creates an empty cart and an activation token valid "
        "for 24 hours. Email delivery is not implemented yet."
    ),
    responses={
        409: {
            "model": ErrorResponseSchema,
            "description": "A user with this email already exists.",
        },
        500: {
            "model": ErrorResponseSchema,
            "description": "The account could not be saved.",
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "The database or registration is unavailable.",
        },
    },
)
async def register_user(
    user_data: UserRegistrationRequestSchema,
    db: AsyncSession = Depends(get_db),
) -> UserResponseSchema:
    user_stmt = select(UserModel).where(UserModel.email == user_data.email)

    try:
        result = await db.execute(user_stmt)
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

        stmt = select(UserGroupModel).where(
            UserGroupModel.name == UserGroupEnum.USER,
        )
        group_result = await db.execute(stmt)
        user_group = group_result.scalars().first()
        if not user_group:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Registration is temporarily unavailable.",
            )

        new_user = await run_in_threadpool(
            UserModel.create,
            email=str(user_data.email),
            raw_password=user_data.password,
            group_id=user_group.id,
        )
        new_user.is_active = False
        new_user.group = user_group
        db.add(new_user)
        await db.flush()

        cart = CartModel(user_id=new_user.id)
        activation_token = ActivationTokenModel(user_id=new_user.id)
        db.add_all([cart, activation_token])
        await db.commit()

    except IntegrityError as error:
        await db.rollback()
        result = await db.execute(user_stmt)
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            ) from error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The account could not be saved.",
        ) from error
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable.",
        ) from error

    return UserResponseSchema.model_validate(new_user)


@router.post(
    "/activate",
    response_model=AccountMessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Activate a user account",
    description=(
        "Accepts an activation token in the JSON body. The token must "
        "exist and must not have expired (24 hours after registration). "
        "Activates the account and deletes the token in one transaction. "
        "No authentication is required. A used token cannot be reused."
    ),
    responses={
        400: {
            "model": ErrorResponseSchema,
            "description": "The activation token is invalid or expired.",
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "The account is already active.",
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Account activation is temporarily unavailable.",
        },
    },
)
async def activate_user(
    activation_data: AccountActivationRequestSchema,
    db: AsyncSession = Depends(get_db),
) -> AccountMessageResponseSchema:
    try:
        stmt = (
            select(ActivationTokenModel)
            .where(ActivationTokenModel.token == activation_data.token)
            .with_for_update()
        )
        result = await db.execute(stmt)
        activation_token = result.scalars().first()
        if not activation_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The activation token is invalid or expired.",
            )

        expires_at = activation_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The activation token is invalid or expired.",
            )

        user = await db.get(UserModel, activation_token.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The activation token is invalid or expired.",
            )
        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The account is already active.",
            )

        user.is_active = True
        await db.delete(activation_token)
        await db.commit()

    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account activation is temporarily unavailable.",
        ) from error

    return AccountMessageResponseSchema(
        message="Account activated successfully.",
    )
