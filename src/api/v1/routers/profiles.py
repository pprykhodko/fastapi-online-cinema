from fastapi import APIRouter, Depends, Path

from src.api.dependencies import get_profile_service
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

    return UserProfileResponseSchema.model_validate(profile)


@router.patch(
    "/{user_id}/",
    response_model=UserProfileResponseSchema,
    dependencies=[Depends(get_profile_owner)],
    summary="Update your profile",
    description=(
        "Only the owner can update the profile, including for admin accounts. "
        "Send a JSON object with first_name, last_name, gender (man/woman), "
        "date_of_birth (YYYY-MM-DD), or info. Omitted fields stay unchanged; "
        "null clears a field. An empty object makes no changes. "
        "Avatar upload is not supported yet. A missing profile returns 404; "
        "this endpoint never creates a profile."
    ),
)
async def update_profile(
    data: UserProfileUpdateRequestSchema,
    user_id: int = Path(gt=0, le=2**63 - 1),
    service: ProfileService = Depends(get_profile_service),
) -> UserProfileResponseSchema:
    return await service.update_profile(user_id, data)
