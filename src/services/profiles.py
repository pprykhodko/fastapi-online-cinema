import logging
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError

from src.services.database_errors import database_errors
from src.core.config import Settings
from src.database.models import UserProfileModel
from src.database.validators.avatars import validate_avatar
from src.repositories.profiles import ProfileRepository
from src.schemas.accounts import (
    UserProfileResponseSchema,
    UserProfileUpdateRequestSchema
)
from src.storages.s3 import S3Storage, StorageError


logger = logging.getLogger(__name__)


class ProfileService:
    def __init__(
            self,
            repository: ProfileRepository,
            storage: S3Storage,
            settings: Settings
    ):
        self.repository = repository
        self.storage = storage
        self.settings = settings

    async def serialize_profile(
            self,
            profile: UserProfileModel
    ) -> UserProfileResponseSchema:
        response = UserProfileResponseSchema.model_validate(profile)

        if profile.avatar:
            try:
                response.avatar = await run_in_threadpool(
                    self.storage.get_file_url,
                    profile.avatar
                )

            except StorageError:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Avatar storage is unavailable"
                )

        return response

    async def delete_avatar(self, key: str) -> None:
        try:
            await run_in_threadpool(self.storage.delete_file, key)

        except StorageError:
            logger.warning("An unused avatar could not be removed from S3")

    async def prepare_avatar(self, avatar: UploadFile) -> tuple[bytes, str]:
        if avatar.content_type not in ("image/jpeg", "image/png"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only JPEG and PNG images are allowed"
            )

        data = await avatar.read(self.settings.AVATAR_MAX_BYTES + 1)

        if len(data) > self.settings.AVATAR_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Avatar file is too large"
            )

        try:
            data, extension = await run_in_threadpool(
                validate_avatar,
                data,
                avatar.content_type
            )

        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error)
            )

        if len(data) > self.settings.AVATAR_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Processed avatar is too large"
            )

        return data, extension

    async def get_profile(self, user_id: int) -> UserProfileModel:
        async with database_errors(
                self.repository,
                detail="Profiles are temporarily unavailable"
        ):
            profile = await self.repository.get_profile(user_id)

        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )

        return profile

    async def update_profile(
            self,
            user_id: int,
            data: UserProfileUpdateRequestSchema,
            avatar: UploadFile | None = None
    ) -> UserProfileResponseSchema:
        profile = await self.get_profile(user_id)
        old_key = profile.avatar
        new_key = None

        if avatar is not None:
            file_data, extension = await self.prepare_avatar(avatar)
            new_key = f"avatars/{user_id}/{uuid4().hex}.{extension}"

            try:
                await run_in_threadpool(
                    self.storage.upload_file, file_data, new_key,
                    "image/jpeg" if extension == "jpg" else "image/png",
                )

            except StorageError:
                await self.delete_avatar(new_key)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Avatar upload failed"
                )

            profile.avatar = new_key

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)

        try:
            response = await self.serialize_profile(profile)
            await self.repository.commit()

        except (SQLAlchemyError, HTTPException) as error:
            await self.repository.rollback()

            if new_key:
                await self.delete_avatar(new_key)

            if isinstance(error, HTTPException):
                raise

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The profile could not be saved. Please try again."
            )

        if new_key and old_key and old_key.startswith(f"avatars/{user_id}/"):
            await self.delete_avatar(old_key)

        return response
