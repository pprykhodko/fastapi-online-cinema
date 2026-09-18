from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.notifications.emails import EmailSender, get_email_sender
from src.repositories.accounts import AccountRepository
from src.services.accounts import AccountService
from src.repositories.profiles import ProfileRepository
from src.services.profiles import ProfileService
from src.storages.s3 import S3Storage, get_s3_storage
from src.core.config import Settings, get_settings


def get_account_service(
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender),
) -> AccountService:
    repository = AccountRepository(db)

    return AccountService(repository, email_sender)


def get_profile_service(
    db: AsyncSession = Depends(get_db),
    storage: S3Storage = Depends(get_s3_storage),
    settings: Settings = Depends(get_settings),
) -> ProfileService:
    return ProfileService(ProfileRepository(db), storage, settings)
