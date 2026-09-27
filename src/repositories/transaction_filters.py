from datetime import datetime, time, timezone

from src.schemas.common import AdminTransactionListQuerySchema


def transaction_filters(model, query, user_id: int | None = None) -> list:
    """
    Build owner, status and inclusive UTC date filters for transaction history.

    The caller controls the transaction commit.

    Args:
        model: Order or payment model whose columns are used in the filters.
        query: Validated pagination and any supported search, sort or filter options.
        user_id (int | None): ID of the account whose data is being accessed.

    Returns:
        list: SQLAlchemy conditions to combine with AND.
    """
    filters = []

    if user_id is not None:
        filters.append(model.user_id == user_id)

    if isinstance(query, AdminTransactionListQuerySchema):
        if query.user_id is not None:
            filters.append(model.user_id == query.user_id)

        transaction_status = getattr(query, "status", None)

        if transaction_status is not None:
            filters.append(model.status == transaction_status)

        if query.date_from is not None:
            filters.append(
                model.created_at >= datetime.combine(
                    query.date_from, time.min, timezone.utc
                )
            )

        if query.date_to is not None:
            filters.append(
                model.created_at <= datetime.combine(
                    query.date_to, time.max, timezone.utc
                )
            )

    return filters
