def validate_user_rating(score: int) -> int:
    if isinstance(score, bool) or not isinstance(score, int):
        raise ValueError("Rating must be an integer between 1 and 10.")
    if not 1 <= score <= 10:
        raise ValueError("Rating must be between 1 and 10.")
    return score
