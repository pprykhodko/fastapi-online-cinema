from datetime import datetime, time, timezone

from src.schemas.common import AdminTransactionListQuerySchema


def transaction_filters(model, query, user_id: int | None = None) -> list:
    """Shared filters for order/payment history, including the owner restriction"""
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
