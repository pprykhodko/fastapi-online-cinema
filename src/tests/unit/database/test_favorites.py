from src.database import MovieFavoriteModel


def test_favorite_representation() -> None:
    favorite = MovieFavoriteModel(id=1, user_id=2, movie_id=3)
    assert repr(favorite) == (
        "<MovieFavoriteModel(id=1, user_id=2, movie_id=3)>"
    )
