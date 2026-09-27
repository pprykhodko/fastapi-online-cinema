from sqlalchemy import delete, select

from src.repositories.base import BaseRepository
from src.database.models import MovieReactionModel


class ReactionRepository(BaseRepository):
    async def get_reaction(
            self,
            user_id: int, movie_id: int
    ) -> MovieReactionModel | None:
        """
        Look up the user reaction record for the movie.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            MovieReactionModel | None: Matching database record(s), or None when allowed
                and not found.
        """
        return await self.db.scalar(
            select(MovieReactionModel)
            .where(
                MovieReactionModel.user_id == user_id,
                MovieReactionModel.movie_id == movie_id
            )
        )

    async def save(self, reaction: MovieReactionModel) -> None:
        """
        Add and flush the supplied record without committing the shared transaction.

        Args:
            reaction (MovieReactionModel): Movie reaction value or stored reaction
                record.
        """
        self.db.add(reaction)
        await self.db.flush()
        await self.db.refresh(reaction)

    async def delete(self, user_id: int, movie_id: int) -> bool:
        """
        Delete the matching record without committing and report whether it existed.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            bool: True if a matching record was deleted; otherwise False.
        """
        deleted_id = await self.db.scalar(
            delete(MovieReactionModel)
            .where(
                MovieReactionModel.user_id == user_id,
                MovieReactionModel.movie_id == movie_id
            )
            .returning(MovieReactionModel.id)
        )
        return deleted_id is not None
