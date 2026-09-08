def validate_movie_reaction(reaction: str) -> str:
    if not isinstance(reaction, str) or reaction not in ("like", "dislike"):
        raise ValueError("Movie reaction must be 'like' or 'dislike'.")
    return reaction
