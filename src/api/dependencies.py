from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.database import get_db
from src.notifications.queue import EmailQueue, get_email_queue
from src.payments.stripe import StripeGateway, get_stripe_gateway
from src.repositories.accounts import AccountRepository
from src.repositories.cart import CartRepository
from src.repositories.certifications import CertificationRepository
from src.repositories.comments import CommentRepository
from src.repositories.directors import DirectorRepository
from src.repositories.favorites import FavoriteRepository
from src.repositories.genres import GenreRepository
from src.repositories.movies import MovieRepository
from src.repositories.orders import OrderRepository
from src.repositories.payments import PaymentRepository
from src.repositories.profiles import ProfileRepository
from src.repositories.ratings import RatingRepository
from src.repositories.reactions import ReactionRepository
from src.repositories.stars import StarRepository
from src.repositories.tokens import TokenRepository
from src.services.accounts import AccountService
from src.services.cart import CartService
from src.services.certifications import CertificationService
from src.services.comments import CommentService
from src.services.directors import DirectorService
from src.services.favorites import FavoriteService
from src.services.genres import GenreService
from src.services.movies import MovieService
from src.services.orders import OrderService
from src.services.payments import PaymentService
from src.services.profiles import ProfileService
from src.services.ratings import RatingService
from src.services.reactions import ReactionService
from src.services.stars import StarService
from src.storages.s3 import S3Storage, get_s3_storage


def get_account_service(
        db: AsyncSession = Depends(get_db),
        email_queue: EmailQueue = Depends(get_email_queue)
) -> AccountService:
    """
    Build AccountService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.
        email_queue (EmailQueue): Publisher used to send email tasks to Celery.

    Returns:
        AccountService: Configured component ready for use.
    """
    return AccountService(
        repository=AccountRepository(db),
        email_queue=email_queue,
        token_repository=TokenRepository(db),
        profile_repository=ProfileRepository(db),
        cart_repository=CartRepository(db)
    )


def get_profile_service(
        db: AsyncSession = Depends(get_db),
        storage: S3Storage = Depends(get_s3_storage),
        settings: Settings = Depends(get_settings)
) -> ProfileService:
    """
    Build ProfileService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.
        storage (S3Storage): S3-compatible adapter used to manage avatar files.
        settings (Settings): Application configuration used by this component.

    Returns:
        ProfileService: Configured component ready for use.
    """
    return ProfileService(ProfileRepository(db), storage, settings)


def get_genre_service(db: AsyncSession = Depends(get_db)) -> GenreService:
    """
    Build GenreService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        GenreService: Configured component ready for use.
    """
    return GenreService(GenreRepository(db))


def get_star_service(db: AsyncSession = Depends(get_db)) -> StarService:
    """
    Build StarService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        StarService: Configured component ready for use.
    """
    return StarService(StarRepository(db))


def get_director_service(db: AsyncSession = Depends(get_db)) -> DirectorService:
    """
    Build DirectorService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        DirectorService: Configured component ready for use.
    """
    return DirectorService(DirectorRepository(db))


def get_certification_service(
        db: AsyncSession = Depends(get_db)
) -> CertificationService:
    """
    Build CertificationService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        CertificationService: Configured component ready for use.
    """
    return CertificationService(CertificationRepository(db))


def get_movie_service(db: AsyncSession = Depends(get_db)) -> MovieService:
    """
    Build MovieService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        MovieService: Configured component ready for use.
    """
    return MovieService(MovieRepository(db))


def get_cart_service(db: AsyncSession = Depends(get_db)) -> CartService:
    """
    Build CartService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        CartService: Configured component ready for use.
    """
    return CartService(CartRepository(db), MovieRepository(db), OrderRepository(db))


def get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
    """
    Build OrderService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        OrderService: Configured component ready for use.
    """
    return OrderService(OrderRepository(db), CartRepository(db), MovieRepository(db))


def get_payment_service(
        db: AsyncSession = Depends(get_db),
        orders: OrderService = Depends(get_order_service),
        gateway: StripeGateway = Depends(get_stripe_gateway),
        email_queue: EmailQueue = Depends(get_email_queue)
) -> PaymentService:
    """
    Build PaymentService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.
        orders (OrderService): Order service using the same database session.
        gateway (StripeGateway): Stripe adapter used for checkout, webhook and refund
            operations.
        email_queue (EmailQueue): Publisher used to send email tasks to Celery.

    Returns:
        PaymentService: Configured component ready for use.
    """
    return PaymentService(PaymentRepository(db), orders, gateway, email_queue)


def get_favorite_service(db: AsyncSession = Depends(get_db)) -> FavoriteService:
    """
    Build FavoriteService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        FavoriteService: Configured component ready for use.
    """
    return FavoriteService(FavoriteRepository(db), MovieRepository(db))


def get_reaction_service(db: AsyncSession = Depends(get_db)) -> ReactionService:
    """
    Build ReactionService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        ReactionService: Configured component ready for use.
    """
    return ReactionService(ReactionRepository(db), MovieRepository(db))


def get_rating_service(db: AsyncSession = Depends(get_db)) -> RatingService:
    """
    Build RatingService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.

    Returns:
        RatingService: Configured component ready for use.
    """
    return RatingService(RatingRepository(db), MovieRepository(db))


def get_comment_service(
        db: AsyncSession = Depends(get_db),
        email_queue: EmailQueue = Depends(get_email_queue)
) -> CommentService:
    """
    Build CommentService with repositories sharing the request database session.

    Args:
        db (AsyncSession): Shared asynchronous database session.
        email_queue (EmailQueue): Publisher used to send email tasks to Celery.

    Returns:
        CommentService: Configured component ready for use.
    """
    return CommentService(
        CommentRepository(db),
        email_queue,
        MovieRepository(db),
        AccountRepository(db)
    )
