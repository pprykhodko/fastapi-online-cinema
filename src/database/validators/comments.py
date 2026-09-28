def validate_comment_content(content: str) -> str:
    """
    Reject blank or non-string comments and strip surrounding whitespace.

    Args:
        content (str): Comment text to validate.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Comment must contain non-whitespace text.")
    return content.strip()
