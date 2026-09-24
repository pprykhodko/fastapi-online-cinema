from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.database import get_db
from src.notifications.queue import EmailQueue, get_email_queue
from src.repositories.accounts import AccountRepository
from src.repositories.cart import CartRepository
from src.repositories.certifications import CertificationRepository
from src.repositories.comments import CommentRepository
from src.repositories.directors import DirectorRepository
from src.repositories.favorites import FavoriteRepository
from src.repositories.genres import GenreRepository
from src.repositories.movies import MovieRepository
from src.repositories.orders import OrderRepository
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
from src.services.profiles import ProfileService
from src.services.ratings import RatingService
from src.services.reactions import ReactionService
from src.services.stars import StarService
from src.storages.s3 import S3Storage, get_s3_storage


def get_account_service(
        db: AsyncSession = Depends(get_db),
        email_queue: EmailQueue = Depends(get_email_queue)
) -> AccountService:
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
    return ProfileService(ProfileRepository(db), storage, settings)


def get_genre_service(db: AsyncSession = Depends(get_db)) -> GenreService:
    return GenreService(GenreRepository(db))


def get_star_service(db: AsyncSession = Depends(get_db)) -> StarService:
    return StarService(StarRepository(db))


def get_director_service(db: AsyncSession = Depends(get_db)) -> DirectorService:
    return DirectorService(DirectorRepository(db))


def get_certification_service(db: AsyncSession = Depends(get_db)) -> CertificationService:
    return CertificationService(CertificationRepository(db))


def get_movie_service(db: AsyncSession = Depends(get_db)) -> MovieService:
    return MovieService(MovieRepository(db))


def get_cart_service(db: AsyncSession = Depends(get_db)) -> CartService:
    return CartService(CartRepository(db), MovieRepository(db), OrderRepository(db))


def get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
    return OrderService(OrderRepository(db), CartRepository(db), MovieRepository(db))


def get_favorite_service(db: AsyncSession = Depends(get_db)) -> FavoriteService:
    return FavoriteService(FavoriteRepository(db), MovieRepository(db))


def get_reaction_service(db: AsyncSession = Depends(get_db)) -> ReactionService:
    return ReactionService(ReactionRepository(db), MovieRepository(db))


def get_rating_service(db: AsyncSession = Depends(get_db)) -> RatingService:
    return RatingService(RatingRepository(db), MovieRepository(db))


def get_comment_service(
        db: AsyncSession = Depends(get_db),
        email_queue: EmailQueue = Depends(get_email_queue)
) -> CommentService:
    return CommentService(CommentRepository(db), email_queue, MovieRepository(db), AccountRepository(db))
