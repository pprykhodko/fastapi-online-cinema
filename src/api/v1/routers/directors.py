from typing import Any

from fastapi import APIRouter, Depends, Path, Response

from src.api.dependencies import get_director_service
from src.schemas.common import ErrorResponseSchema
from src.schemas.movies import (
    DirectorCreateRequestSchema,
    DirectorResponseSchema,
    DirectorUpdateRequestSchema
)
from src.security.dependencies import get_current_moderator
from src.services.directors import DirectorService


router = APIRouter(
    responses={
        503: {
            "model": ErrorResponseSchema,
            "description": "Database unavailable"
        }
    }
)
write_responses: dict[int | str, dict[str, Any]] = {
    401: {
        "model": ErrorResponseSchema,
        "description": "Unauthorized"
    },
    403: {
        "model": ErrorResponseSchema,
        "description": "Moderator required"
    },
    409: {
        "model": ErrorResponseSchema,
        "description": "Duplicate director name"
    }
}
not_found: dict[int | str, dict[str, Any]] = {
    404: {
        "model": ErrorResponseSchema,
        "description": "Director not found"
    }
}


@router.get(
    "/",
    response_model=list[DirectorResponseSchema],
    summary="List directors",
    description=(
        "Public list of directors ordered by ID. "
        "Returns an empty list when no directors exist."
    )
)
async def list_directors(
    service: DirectorService = Depends(get_director_service)
):
    return await service.list_directors()


@router.post(
    "/",
    response_model=DirectorResponseSchema,
    status_code=201,
    dependencies=[Depends(get_current_moderator)],
    responses=write_responses,
    summary="Create a director",
    description=(
        "MODERATOR or ADMIN only. Supply name (1–100 characters). "
        "Only English letters, spaces and hyphens are allowed; "
        "at least one letter is required. "
        "Surrounding whitespace is removed; the name must be unique."
    )
)
async def create_director(
    data: DirectorCreateRequestSchema,
    service: DirectorService = Depends(get_director_service)
):
    return await service.create_director(data)


@router.patch(
    "/{director_id}/",
    response_model=DirectorResponseSchema,
    dependencies=[Depends(get_current_moderator)],
    responses={**write_responses, **not_found},
    summary="Rename a director",
    description=(
        "MODERATOR or ADMIN only. Supply the new unique name "
        "(1–100 characters, English letters, spaces and hyphens; "
        "at least one letter required). Movie associations are preserved."
    )
)
async def update_director(
    data: DirectorUpdateRequestSchema,
    director_id: int = Path(gt=0, le=2**31 - 1),
    service: DirectorService = Depends(get_director_service)
):
    return await service.update_director(director_id, data)


@router.delete(
    "/{director_id}/",
    status_code=204,
    dependencies=[Depends(get_current_moderator)],
    responses={
        **not_found,
        401: write_responses[401],
        403: write_responses[403]
    },
    summary="Delete a director",
    description=(
        "MODERATOR or ADMIN only. Removes the director and its movie "
        "associations, not the movies themselves. Returns an empty response."
    )
)
async def delete_director(
    director_id: int = Path(gt=0, le=2**31 - 1),
    service: DirectorService = Depends(get_director_service)
):
    await service.delete_director(director_id)

    return Response(status_code=204)
