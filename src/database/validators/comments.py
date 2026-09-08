def validate_comment_content(content: str) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Comment must contain non-whitespace text.")
    return content.strip()
