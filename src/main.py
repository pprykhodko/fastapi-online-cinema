from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.database import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title="Online Cinema API",
    description=(
        "An API for browsing movies, managing user accounts, "
        "shopping carts, orders, and payments."
    ),
    lifespan=lifespan,
)
