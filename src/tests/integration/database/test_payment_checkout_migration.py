import importlib
from io import StringIO

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, create_engine, inspect, text
from alembic.autogenerate import compare_metadata

from src.database.models import Base


migration = importlib.import_module("src.database.alembic.versions.c4d90271a6bf_payment_checkouts")


def test_payment_migration_upgrade_and_downgrade_preserve_existing_data(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE payments (id INTEGER PRIMARY KEY, external_payment_id VARCHAR(255))"))
        connection.execute(text("INSERT INTO payments VALUES (1, 'pi_old')"))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        assert "payment_checkouts" in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT currency FROM payments WHERE id = 1")).scalar_one() == "usd"
        indexes = inspect(connection).get_indexes("payments")
        assert indexes[0]["unique"] == 1
        migration.downgrade()
        assert "payment_checkouts" not in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT external_payment_id FROM payments WHERE id = 1")).scalar_one() == "pi_old"
    engine.dispose()


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_upgrade_sql_compiles_for_both_databases(monkeypatch, dialect):
    output = StringIO()
    context = MigrationContext.configure(dialect_name=dialect, opts={"as_sql": True, "output_buffer": output})
    monkeypatch.setattr(migration, "op", Operations(context))
    migration.upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE payment_checkouts" in sql
    assert "CREATE UNIQUE INDEX ix_payments_external_payment_id_unique" in sql
    assert "ADD COLUMN currency" in sql


def test_entire_migration_chain_matches_payment_models():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        # Compare enum CHECK constraints directly: Alembic treats type-bound checks differently.
        context = MigrationContext.configure(connection, opts={
            "include_object": lambda obj, name, type_, reflected, compared: type_ != "check_constraint"
        })
        with Operations.context(context):
            for name in ["0117b21577ed_initial_migration", "2b6e0f8a4c91_seed_default_user_groups",
                         "7a92c1d4e608_backfill_user_profiles", "c4d90271a6bf_payment_checkouts",
                         "e7a51092bc34_unique_order_movies"]:
                importlib.import_module(f"src.database.alembic.versions.{name}").upgrade()
        payment_differences = [difference for difference in compare_metadata(context, Base.metadata)
                               if any(table in str(difference) for table in ["payments", "payment_items", "payment_checkouts"])]
        assert payment_differences == []
        for name in ["payments", "payment_items", "payment_checkouts"]:
            actual = {item["name"]: item["sqltext"] for item in inspect(connection).get_check_constraints(name)}
            expected = {
                constraint.name: str(constraint.sqltext.compile(compile_kwargs={"literal_binds": True})).replace(f"{name}.", "")
                for constraint in Base.metadata.tables[name].constraints if isinstance(constraint, CheckConstraint)
            }
            assert actual == expected
    engine.dispose()
