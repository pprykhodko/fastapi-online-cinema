def validate_user_rating(score: int) -> int:
    """
    Require an integer rating from 1 to 10, rejecting booleans.

    Args:
        score (int): Numeric score to validate.

    Returns:
        int: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if isinstance(score, bool) or not isinstance(score, int):
        raise ValueError("Rating must be an integer between 1 and 10.")
    if not 1 <= score <= 10:
        raise ValueError("Rating must be between 1 and 10.")
    return score
