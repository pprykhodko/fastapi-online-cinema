def validate_movie_reaction(reaction: str) -> str:
    """
    Accept only like or dislike movie reactions.

    Args:
        reaction (str): Movie reaction value or stored reaction record.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if not isinstance(reaction, str) or reaction not in ("like", "dislike"):
        raise ValueError("Movie reaction must be 'like' or 'dislike'.")
    return reaction
