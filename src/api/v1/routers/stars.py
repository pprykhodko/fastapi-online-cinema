from typing import Any

from fastapi import APIRouter, Depends, Path, Response

from src.api.dependencies import get_star_service
from src.schemas.common import ErrorResponseSchema
from src.schemas.movies import (
    StarCreateRequestSchema, StarResponseSchema, StarUpdateRequestSchema,
)
from src.security.dependencies import get_current_moderator
from src.services.stars import StarService


router = APIRouter(
    responses={
        503: {
            "model": ErrorResponseSchema,
            "description": "Database unavailable",
        }
    }
)
write_responses: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponseSchema, "description": "Unauthorized."},
    403: {"model": ErrorResponseSchema, "description": "Moderator required."},
    409: {"model": ErrorResponseSchema, "description": "Duplicate star name"}
}
not_found: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponseSchema, "description": "Star not found."}
}


@router.get(
    "/", response_model=list[StarResponseSchema],
    summary="List actors",
    description=(
        "Public list of actors ordered by ID. Returns an empty list "
        "when no actors exist."
    ),
)
async def list_stars(
    service: StarService = Depends(get_star_service),
):
    return await service.list_stars()


@router.get(
    "/{star_id}/", response_model=StarResponseSchema,
    summary="Get a star", description="Public lookup by star ID.",
    responses=not_found,
)
async def get_star(
    star_id: int = Path(gt=0, le=2**31 - 1),
    service: StarService = Depends(get_star_service),
):
    return await service.get_star(star_id)


@router.post(
    "/", response_model=StarResponseSchema, status_code=201,
    dependencies=[Depends(get_current_moderator)], responses=write_responses,
    summary="Create a star",
    description=(
        "MODERATOR or ADMIN only. Supply name (1–100 characters). "
        "Surrounding whitespace is removed; the name must be unique."
    ),
)
async def create_star(
    data: StarCreateRequestSchema,
    service: StarService = Depends(get_star_service),
):
    return await service.create_star(data)


@router.patch(
    "/{star_id}/", response_model=StarResponseSchema,
    dependencies=[Depends(get_current_moderator)],
    responses={**write_responses, **not_found}, summary="Rename a star",
    description=(
        "MODERATOR or ADMIN only. Supply the new unique name "
        "(1–100 characters). Movie associations are preserved."
    ),
)
async def update_star(
    data: StarUpdateRequestSchema,
    star_id: int = Path(gt=0, le=2**31 - 1),
    service: StarService = Depends(get_star_service),
):
    return await service.update_star(star_id, data)


@router.delete(
    "/{star_id}/", status_code=204,
    dependencies=[Depends(get_current_moderator)],
    responses={
        **not_found, 401: write_responses[401], 403: write_responses[403],
    },
    summary="Delete a star",
    description=(
        "MODERATOR or ADMIN only. Removes the star and its movie "
        "associations, not the movies themselves. Returns an empty response."
    ),
)
async def delete_star(
    star_id: int = Path(gt=0, le=2**31 - 1),
    service: StarService = Depends(get_star_service),
):
    await service.delete_star(star_id)

    return Response(status_code=204)
