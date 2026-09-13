from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.database.session_postgresql import postgresql_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await postgresql_engine.dispose()


app = FastAPI(
    title="Online Cinema API",
    description=(
        "An API for browsing movies, managing user accounts, "
        "shopping carts, orders, and payments."
    ),
    lifespan=lifespan,
)
