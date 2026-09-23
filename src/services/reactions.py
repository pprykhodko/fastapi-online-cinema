from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import MovieReactionModel
from src.repositories.reactions import ReactionRepository
from src.schemas.interactions import (
    MovieReactionRequestSchema, MovieReactionResponseSchema,
)


class ReactionService:
    def __init__(self, repository: ReactionRepository):
        self.repository = repository

    async def get_reaction(
        self, user_id: int, movie_id: int,
    ) -> MovieReactionResponseSchema:
        try:
            if not await self.repository.movie_exists(movie_id):
                raise HTTPException(404, "Movie not found.")

            reaction = await self.repository.get_reaction(user_id, movie_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Reactions are temporarily unavailable.",
            ) from error

        if reaction is None:
            raise HTTPException(404, "You have not reacted to this movie.")

        return MovieReactionResponseSchema.model_validate(reaction)

    async def set_reaction(
        self, user_id: int, movie_id: int, data: MovieReactionRequestSchema,
    ) -> tuple[MovieReactionResponseSchema, bool]:
        try:
            if not await self.repository.movie_exists(movie_id, lock=True):
                raise HTTPException(404, "Movie not found.")

            reaction = await self.repository.get_reaction(user_id, movie_id)
            created = reaction is None

            if reaction is None:
                reaction = MovieReactionModel(
                    user_id=user_id, movie_id=movie_id, reaction=data.reaction,
                )

            else:
                reaction.reaction = data.reaction
            await self.repository.save(reaction)
            response = MovieReactionResponseSchema.model_validate(reaction)
            await self.repository.commit()

            return response, created

        except HTTPException:
            await self.repository.rollback()
            raise

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "Reaction data changed. Please repeat the request.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The reaction could not be saved.",
            ) from error

    async def delete_reaction(self, user_id: int, movie_id: int) -> None:
        try:
            deleted = await self.repository.delete(user_id, movie_id)

            if not deleted:
                raise HTTPException(404, "You have not reacted to this movie.")

            await self.repository.commit()

        except HTTPException:
            await self.repository.rollback()
            raise

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The reaction could not be removed.",
            ) from error
