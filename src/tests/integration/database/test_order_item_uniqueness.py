import importlib
from decimal import Decimal
from io import StringIO

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from src.database.models import OrderItemModel, OrderModel


def test_model_rejects_duplicate_movie_in_same_order(
        db_session, catalog_users, catalog_movies
):
    order = OrderModel(user_id=catalog_users[0].id, total_amount=Decimal("20"))
    db_session.add(order)
    db_session.flush()
    db_session.add_all(
        [
            OrderItemModel(
                order_id=order.id,
                movie_id=catalog_movies[0].id,
                price_at_order=Decimal("10")
            )
            for _ in range(2)
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_unique_movie_migration_is_reversible_without_deleting_rows():
    migration = importlib.import_module(
        "src.database.alembic.versions.e7a51092bc34_unique_order_movies"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE order_items (id INTEGER PRIMARY KEY, "
                "order_id INTEGER, movie_id INTEGER)"
            )
        )
        connection.execute(text("INSERT INTO order_items VALUES (1, 1, 1)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            with pytest.raises(IntegrityError):
                connection.execute(text("INSERT INTO order_items VALUES (2, 1, 1)"))
            connection.execute(text("INSERT INTO order_items VALUES (3, 2, 1)"))
            migration.downgrade()
        assert (
            connection.execute(text("SELECT COUNT(*) FROM order_items")).scalar_one()
            == 2
        )
    engine.dispose()


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_unique_order_index_compiles_for_both_databases(dialect):
    migration = importlib.import_module(
        "src.database.alembic.versions.e7a51092bc34_unique_order_movies"
    )
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name=dialect, opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        migration.upgrade()
        migration.downgrade()
    assert (
        "CREATE UNIQUE INDEX uq_order_items_order_movie "
        "ON order_items (order_id, movie_id)"
        in output.getvalue()
    )
    assert "DROP INDEX uq_order_items_order_movie" in output.getvalue()
