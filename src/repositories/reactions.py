from sqlalchemy import delete, select

from src.repositories.base import BaseRepository
from src.database.models import MovieReactionModel


class ReactionRepository(BaseRepository):
    async def get_reaction(
            self,
            user_id: int, movie_id: int
    ) -> MovieReactionModel | None:
        return await self.db.scalar(
            select(MovieReactionModel)
            .where(
                MovieReactionModel.user_id == user_id,
                MovieReactionModel.movie_id == movie_id
            )
        )

    async def save(self, reaction: MovieReactionModel) -> None:
        self.db.add(reaction)
        await self.db.flush()
        await self.db.refresh(reaction)

    async def delete(self, user_id: int, movie_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(MovieReactionModel)
            .where(
                MovieReactionModel.user_id == user_id,
                MovieReactionModel.movie_id == movie_id
            )
            .returning(MovieReactionModel.id)
        )
        return deleted_id is not None
