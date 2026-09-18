from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from src.database.models import UserProfileModel
from src.repositories.profiles import ProfileRepository
from src.schemas.accounts import (
    UserProfileResponseSchema, UserProfileUpdateRequestSchema,
)


class ProfileService:
    def __init__(self, repository: ProfileRepository):
        self.repository = repository

    async def get_profile(self, user_id: int) -> UserProfileModel:
        try:
            profile = await self.repository.get_profile(user_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Profiles are temporarily unavailable.",
            ) from error

        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found.",
            )

        return profile

    async def update_profile(
        self, user_id: int, data: UserProfileUpdateRequestSchema,
    ) -> UserProfileResponseSchema:
        profile = await self.get_profile(user_id)

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)

        try:
            await self.repository.commit()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The profile could not be saved. Please try again.",
            ) from error

        return UserProfileResponseSchema.model_validate(profile)
