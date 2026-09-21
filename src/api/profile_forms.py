from fastapi import Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from src.schemas.accounts import UserProfileUpdateRequestSchema


def empty_avatar_as_none(
    value: UploadFile | str | None,
) -> UploadFile | str | None:

    return None if value == "" else value


async def get_profile_data(
    request: Request,
    first_name: str | None = Form(None, max_length=100),
    last_name: str | None = Form(None, max_length=100),
    gender: str | None = Form(None, description="man or woman"),
    date_of_birth: str | None = Form(None, description="YYYY-MM-DD"),
    info: str | None = Form(None),
) -> UserProfileUpdateRequestSchema:
    content_type = request.headers.get("content-type", "").split(";")[0]

    if content_type == "application/json":
        try:
            data = await request.json()

        except ValueError as error:
            raise HTTPException(422, "Invalid JSON body.") from error

    elif content_type in (
        "multipart/form-data", "application/x-www-form-urlencoded",
    ):
        form = await request.form()
        fields = {
            "first_name": first_name,
            "last_name": last_name,
            "gender": gender,
            "date_of_birth": date_of_birth,
            "info": info,
        }
        data = {
            key: fields.get(key, value)
            for key, value in form.items()
            if key != "avatar"
            and (key not in fields or value != "")
        }

    else:
        raise HTTPException(415, "Use JSON or multipart/form-data.")

    try:
        return UserProfileUpdateRequestSchema.model_validate(data)

    except ValidationError as error:
        errors = [
            {**item, "loc": ("body", *item["loc"])}
            for item in error.errors()
        ]
        raise RequestValidationError(errors) from error
