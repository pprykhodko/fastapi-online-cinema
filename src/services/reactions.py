from fastapi import HTTPException, status

from src.services.database_errors import database_errors
from src.database.models import MovieReactionModel
from src.repositories.reactions import ReactionRepository
from src.repositories.movies import MovieRepository
from src.services.movie_checks import get_movie_or_404
from src.schemas.interactions import (
    MovieReactionRequestSchema,
    MovieReactionResponseSchema
)


class ReactionService:
    def __init__(
            self,
            repository: ReactionRepository,
            movie_repository: MovieRepository
    ):
        """
        Initialize ReactionService with its required dependencies.

        Args:
            repository (ReactionRepository): Repository used for database operations and
                the shared transaction.
            movie_repository (MovieRepository): Repository for movie data using the
                shared session.
        """
        self.repository = repository
        self.movie_repository = movie_repository

    async def get_reaction(
            self,
            user_id: int,
            movie_id: int
    ) -> MovieReactionResponseSchema:
        """
        Return the user like or dislike for the selected movie.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            MovieReactionResponseSchema: User like or dislike and record timestamps.

        Raises:
            HTTPException: The requested record is missing or cannot be loaded.
        """
        async with database_errors(
                self.repository,
                detail="Reactions are temporarily unavailable"
        ):
            await get_movie_or_404(self.movie_repository, movie_id)

            reaction = await self.repository.get_reaction(user_id, movie_id)

        if reaction is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You have not reacted to this movie"
            )

        return MovieReactionResponseSchema.model_validate(reaction)

    async def set_reaction(
            self,
            user_id: int,
            movie_id: int,
            data: MovieReactionRequestSchema
    ) -> tuple[MovieReactionResponseSchema, bool]:
        """
        Create or replace the user movie reaction with a like or dislike.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.
            data (MovieReactionRequestSchema): Requested like or dislike reaction.

        Returns:
            tuple[MovieReactionResponseSchema, bool]: Response data and True if a new
                record was created.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        async with database_errors(
                self.repository,
                detail="The reaction could not be saved",
                conflict_detail="Reaction data changed. Please repeat the request."
        ):
            await get_movie_or_404(self.movie_repository, movie_id, lock=True)

            reaction = await self.repository.get_reaction(user_id, movie_id)
            created = reaction is None

            if reaction is None:
                reaction = MovieReactionModel(
                    user_id=user_id,
                    movie_id=movie_id,
                    reaction=data.reaction
                )

            else:
                reaction.reaction = data.reaction

            await self.repository.save(reaction)
            response = MovieReactionResponseSchema.model_validate(reaction)
            await self.repository.commit()

            return response, created

    async def delete_reaction(self, user_id: int, movie_id: int) -> None:
        """
        Remove the user reaction to the selected movie.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Raises:
            HTTPException: The record is missing or database constraints prevent
                removal.
        """
        async with database_errors(
                self.repository,
                detail="The reaction could not be removed"
        ):
            deleted = await self.repository.delete(user_id, movie_id)

            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="You have not reacted to this movie"
                )

            await self.repository.commit()
