from fastapi import HTTPException, status

from src.services.database_errors import database_errors
from src.database.models import MovieReactionModel
from src.repositories.reactions import ReactionRepository
from src.repositories.movies import MovieRepository
from src.services.movie_checks import get_movie_or_404
from src.schemas.interactions import (
    MovieReactionRequestSchema, MovieReactionResponseSchema,
)


class ReactionService:
    def __init__(self, repository: ReactionRepository, movie_repository: MovieRepository):
        self.repository = repository
        self.movie_repository = movie_repository

    async def get_reaction(self, user_id: int, movie_id: int) -> MovieReactionResponseSchema:
        async with database_errors(self.repository, detail="Reactions are temporarily unavailable"):
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
        async with database_errors(
                self.repository,
                detail="The reaction could not be saved",
                conflict_detail="Reaction data changed. Please repeat the request."
        ):
            await get_movie_or_404(self.movie_repository, movie_id, lock=True)

            reaction = await self.repository.get_reaction(user_id, movie_id)
            created = reaction is None

            if reaction is None:
                reaction = MovieReactionModel(user_id=user_id, movie_id=movie_id, reaction=data.reaction)

            else:
                reaction.reaction = data.reaction

            await self.repository.save(reaction)
            response = MovieReactionResponseSchema.model_validate(reaction)
            await self.repository.commit()

            return response, created

    async def delete_reaction(self, user_id: int, movie_id: int) -> None:
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
