from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.notifications.emails import EmailSender, get_email_sender
from src.repositories.accounts import AccountRepository
from src.services.accounts import AccountService


def get_account_service(
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender),
) -> AccountService:
    repository = AccountRepository(db)
    return AccountService(repository, email_sender)
