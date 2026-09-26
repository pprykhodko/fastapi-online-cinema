from typing import Any

from fastapi import APIRouter, Depends, Path, Response

from src.api.dependencies import get_certification_service
from src.schemas.common import ErrorResponseSchema
from src.schemas.movies import (
    CertificationCreateRequestSchema,
    CertificationResponseSchema,
    CertificationUpdateRequestSchema
)
from src.security.dependencies import get_current_moderator
from src.services.certifications import CertificationService


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
        "description": "Duplicate certification name"
    }
}
not_found: dict[int | str, dict[str, Any]] = {
    404: {
        "model": ErrorResponseSchema,
        "description": "Certification not found"
    }
}


@router.get(
    "/",
    response_model=list[CertificationResponseSchema],
    summary="List certifications",
    description=(
        "Public list of certifications ordered by ID. Returns an empty list "
        "when no certifications exist."
    )
)
async def list_certifications(
    service: CertificationService = Depends(get_certification_service)
):
    return await service.list_certifications()


@router.post(
    "/",
    response_model=CertificationResponseSchema,
    status_code=201,
    dependencies=[Depends(get_current_moderator)],
    responses=write_responses,
    summary="Create a certification",
    description=(
        "MODERATOR or ADMIN only. Supply name (1–100 characters). "
        "Examples: G, PG, PG-13, R, NC-17. "
        "Surrounding whitespace is removed; the name must be unique."
    )
)
async def create_certification(
    data: CertificationCreateRequestSchema,
    service: CertificationService = Depends(get_certification_service)
):
    return await service.create_certification(data)


@router.patch(
    "/{certification_id}/",
    response_model=CertificationResponseSchema,
    dependencies=[Depends(get_current_moderator)],
    responses={**write_responses, **not_found},
    summary="Rename a certification",
    description=(
        "MODERATOR or ADMIN only. Supply the new unique name "
        "(1–100 characters). Surrounding whitespace is removed. "
        "Movie associations are preserved."
    )
)
async def update_certification(
    data: CertificationUpdateRequestSchema,
    certification_id: int = Path(gt=0, le=2**31 - 1),
    service: CertificationService = Depends(get_certification_service)
):
    return await service.update_certification(certification_id, data)


@router.delete(
    "/{certification_id}/",
    status_code=204,
    dependencies=[Depends(get_current_moderator)],
    responses={
        **not_found,
        401: write_responses[401],
        403: write_responses[403],
        409: {
            "model": ErrorResponseSchema,
            "description": "Certification is used by a movie."
        }
    },
    summary="Delete a certification",
    description=(
        "MODERATOR or ADMIN only. Returns 409 if any movie references "
        "this certification, including soft-deleted movies. Otherwise "
        "deletes the certification and returns an empty response."
    )
)
async def delete_certification(
    certification_id: int = Path(gt=0, le=2**31 - 1),
    service: CertificationService = Depends(get_certification_service)
):
    await service.delete_certification(certification_id)

    return Response(status_code=204)
