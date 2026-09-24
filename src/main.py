from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.v1.routers import (
    accounts_router, profiles_router, movies_router, genres_router,
    stars_router, directors_router, certifications_router,
    favorites_router, reactions_router, ratings_router, comments_router,
)
from src.database import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        yield

    finally:
        await engine.dispose()


app = FastAPI(
    title="Online Cinema API",
    description="An API for browsing movies, managing user accounts, shopping carts, orders, and payments",
    lifespan=lifespan
)

api_version_prefix = "/api/v1"


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
    details = [
        {
            "type": item["type"],
            "loc": item["loc"],
            "msg": item["msg"]
        } for item in error.errors()
    ]

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": details}
    )


app.include_router(
    accounts_router,
    prefix=f"{api_version_prefix}/accounts",
    tags=["accounts"]
)

app.include_router(
    profiles_router,
    prefix=f"{api_version_prefix}/profiles",
    tags=["profiles"]
)

app.include_router(
    movies_router,
    prefix=f"{api_version_prefix}/movies",
    tags=["movies"]
)

app.include_router(
    genres_router,
    prefix=f"{api_version_prefix}/genres",
    tags=["genres"]
)

app.include_router(
    stars_router,
    prefix=f"{api_version_prefix}/stars",
    tags=["stars"]
)

app.include_router(
    directors_router,
    prefix=f"{api_version_prefix}/directors",
    tags=["directors"]
)

app.include_router(
    certifications_router,
    prefix=f"{api_version_prefix}/certifications",
    tags=["certifications"]
)

app.include_router(
    favorites_router,
    prefix=f"{api_version_prefix}/favorites",
    tags=["favorites"]
)

app.include_router(
    reactions_router,
    prefix=f"{api_version_prefix}/movies",
    tags=["reactions"]
)

app.include_router(
    ratings_router,
    prefix=f"{api_version_prefix}/movies",
    tags=["ratings"]
)

app.include_router(
    comments_router,
    prefix=api_version_prefix,
    tags=["comments"]
)
