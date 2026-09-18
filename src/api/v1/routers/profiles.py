from fastapi import APIRouter, Depends, File, Path, UploadFile

from src.api.dependencies import get_profile_service
from src.api.profile_forms import get_profile_data
from src.schemas.accounts import (
    UserProfileResponseSchema, UserProfileUpdateRequestSchema,
)
from src.schemas.common import ErrorResponseSchema
from src.security.dependencies import get_current_user, get_profile_owner
from src.services.profiles import ProfileService


router = APIRouter(responses={
    401: {"model": ErrorResponseSchema, "description": "Unauthorized."},
    403: {"model": ErrorResponseSchema, "description": "Access denied."},
    404: {"model": ErrorResponseSchema, "description": "Profile not found."},
    503: {"model": ErrorResponseSchema, "description": "Service unavailable."},
})


@router.get(
    "/{user_id}/",
    response_model=UserProfileResponseSchema,
    dependencies=[Depends(get_current_user)],
    summary="Get a user profile",
    description=(
        "Requires an active account and an access token. Supply the account's "
        "user_id, not the profile's id. Returns an active user's profile. "
        "Missing profiles and inactive users return 404."
    ),
)
async def get_profile(
    user_id: int = Path(gt=0, le=2**63 - 1),
    service: ProfileService = Depends(get_profile_service),
) -> UserProfileResponseSchema:
    profile = await service.get_profile(user_id)

    return await service.serialize_profile(profile)


@router.patch(
    "/{user_id}/",
    response_model=UserProfileResponseSchema,
    dependencies=[Depends(get_profile_owner)],
    summary="Update your profile",
    description=(
        "Only the owner can update the profile, including for admin accounts. "
        "Send JSON for text fields, or multipart/form-data with an avatar. "
        "Fields: first_name, last_name, gender (man/woman), date_of_birth "
        "(YYYY-MM-DD), info. Omitted fields stay unchanged; JSON null or an "
        "empty form field clears a value. Avatar must be JPEG/PNG, at most "
        "5 MiB by default and 4096px per side. The avatar response is a "
        "temporary signed URL; get the profile again when it expires. "
        "This endpoint never creates a profile."
    ),
    responses={
        413: {"description": "Avatar exceeds the configured size limit."},
        415: {"description": "Unsupported request content type."},
    },
    openapi_extra={"requestBody": {"content": {"application/json": {
        "schema": UserProfileUpdateRequestSchema.model_json_schema(
            ref_template="#/components/schemas/{model}",
        ),
    }}}},
)
async def update_profile(
    data: UserProfileUpdateRequestSchema = Depends(get_profile_data),
    avatar: UploadFile | None = File(None),
    user_id: int = Path(gt=0, le=2**63 - 1),
    service: ProfileService = Depends(get_profile_service),
) -> UserProfileResponseSchema:
    return await service.update_profile(user_id, data, avatar)
