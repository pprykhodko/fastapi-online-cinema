from fastapi import (
    APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, Request,
    Response, status,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.api.dependencies import get_account_service
from src.database.models import UserModel
from src.notifications.emails import TEMPLATES_DIR
from src.schemas.accounts import (
    AccessTokenResponseSchema,
    AccountActivationRequestSchema,
    AccountMessageResponseSchema,
    ActivationResendRequestSchema,
    LogoutRequestSchema,
    PasswordChangeRequestSchema,
    PasswordResetConfirmRequestSchema,
    PasswordResetRequestSchema,
    TokenPairResponseSchema,
    TokenRefreshRequestSchema,
    UserLoginRequestSchema,
    UserRegistrationRequestSchema,
    UserResponseSchema,
)
from src.schemas.common import ErrorResponseSchema
from src.security.dependencies import get_current_user
from src.security.tokens import JWTAuthManager, get_jwt_auth_manager
from src.services.accounts import AccountService


router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
ACTIVATION_PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
}


@router.post(
    "/login/",
    response_model=TokenPairResponseSchema,
    summary="Log in to an activated account",
    description=(
        "Accepts email and password in a JSON body. Returns access and "
        "refresh JWTs for an active account and saves the refresh token "
        "in the database. Use the access token in the Authorization "
        "header: Bearer <access_token>."
    ),
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Incorrect email or password.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "The account has not been activated.",
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "The database is unavailable.",
        },
    },
)
async def login_user(
    login_data: UserLoginRequestSchema,
    response: Response,
    service: AccountService = Depends(get_account_service),
    jwt_manager: JWTAuthManager = Depends(get_jwt_auth_manager),
) -> TokenPairResponseSchema:
    tokens = await service.login(login_data, jwt_manager)

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    return tokens


@router.post(
    "/token/refresh/",
    response_model=AccessTokenResponseSchema,
    summary="Refresh the access token",
    description=(
        "Accepts refresh_token in a JSON body. Validates the refresh JWT, "
        "its database record and the user's active status. Returns a new "
        "access token without replacing or extending the refresh token. "
        "An access token is not required."
    ),
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Invalid, expired or revoked refresh token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "The account is not active.",
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Token refresh is temporarily unavailable.",
        },
    },
)
async def refresh_access_token(
    token_data: TokenRefreshRequestSchema,
    response: Response,
    service: AccountService = Depends(get_account_service),
    jwt_manager: JWTAuthManager = Depends(get_jwt_auth_manager),
) -> AccessTokenResponseSchema:
    token = await service.refresh_access_token(token_data, jwt_manager)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    return token


@router.post(
    "/logout/",
    response_model=AccountMessageResponseSchema,
    summary="Log out of the current session",
    description=(
        "Accepts refresh_token in a JSON body. Deletes the matching valid "
        "refresh token from the database. Other sessions are unchanged. "
        "An access token is not required; inactive users may also log out. "
        "Already issued access tokens remain valid until they expire. "
        "Repeated logout with the deleted refresh token returns 401."
    ),
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Invalid, expired or revoked refresh token.",
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Logout is temporarily unavailable.",
        },
    },
)
async def logout_user(
    logout_data: LogoutRequestSchema,
    service: AccountService = Depends(get_account_service),
    jwt_manager: JWTAuthManager = Depends(get_jwt_auth_manager),
) -> AccountMessageResponseSchema:

    return await service.logout(logout_data, jwt_manager)


@router.patch(
    "/password/change/",
    response_model=AccountMessageResponseSchema,
    summary="Change the current user's password",
    description=(
        "Requires an access token. Accepts old_password and new_password "
        "in JSON. Checks the current password and password complexity. "
        "Revokes all refresh tokens and outstanding password reset tokens. "
        "Existing access tokens remain valid until they expire."
    ),
    responses={
        400: {"model": ErrorResponseSchema,
              "description": "Wrong current password or unchanged password."},
        401: {"model": ErrorResponseSchema,
              "description": "Missing or invalid access token."},
        403: {"model": ErrorResponseSchema,
              "description": "The account is not active."},
        503: {"model": ErrorResponseSchema,
              "description": "Password change is temporarily unavailable."},
    },
)
async def change_password(
    password_data: PasswordChangeRequestSchema,
    current_user: UserModel = Depends(get_current_user),
    service: AccountService = Depends(get_account_service),
) -> AccountMessageResponseSchema:

    return await service.change_password(current_user, password_data)


@router.post(
    "/password/forgot/",
    response_model=AccountMessageResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset email",
    description=(
        "Accepts email in JSON. For an active account, saves a one-use "
        "reset token hash valid for 24 hours. Sends the original token with "
        "API instructions in a background task after the response. "
        "202 means the request was accepted, not that email was delivered. "
        "A new request replaces the previous token. Unknown and inactive "
        "accounts receive the same success response without an email."
    ),
    responses={
        503: {"model": ErrorResponseSchema,
              "description": "The database is temporarily unavailable."},
    },
)
async def request_password_reset(
    email_data: PasswordResetRequestSchema,
    background_tasks: BackgroundTasks,
    service: AccountService = Depends(get_account_service),
) -> AccountMessageResponseSchema:

    return await service.request_password_reset(email_data, background_tasks)


@router.post(
    "/password/reset/",
    response_model=AccountMessageResponseSchema,
    summary="Set a new password using a reset token",
    description=(
        "Accepts token and new_password in JSON; no access token or old "
        "password is required. Checks token expiry and account activity. "
        "Updates the password and removes the reset token and all refresh "
        "tokens in one transaction. A used token cannot be used again. "
        "Existing access tokens remain valid until they expire."
    ),
    responses={
        400: {"model": ErrorResponseSchema,
              "description": "Invalid or expired reset token."},
        503: {"model": ErrorResponseSchema,
              "description": "Password reset is temporarily unavailable."},
    },
)
async def reset_password(
    reset_data: PasswordResetConfirmRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> AccountMessageResponseSchema:

    return await service.reset_password(reset_data)


@router.post(
    "/activate/",
    response_model=AccountMessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Activate a user account",
    description=(
            "Accepts an activation token in the JSON body. The token must "
            "exist and must not have expired (24 hours after registration). "
            "Activates the account and deletes the token in one transaction. "
            "Then sends a confirmation email. If that email cannot be sent, "
            "activation still succeeds and the response message reports it. "
            "No authentication is required. A used token cannot be reused."
    ),
    responses={
        400: {
            "model": ErrorResponseSchema,
            "description": "The activation token is invalid or expired.",
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "The account is already active.",
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Account activation is temporarily unavailable.",
        },
    },
)
async def activate_user(
    activation_data: AccountActivationRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> AccountMessageResponseSchema:

    return await service.activate_account(activation_data)


@router.get(
    "/activate/",
    response_class=HTMLResponse,
    summary="Open the account activation page",
    description=(
        "Opens an HTML confirmation form linked from the activation email. "
        "Accepts a token query parameter. The form submits to "
        "POST /accounts/activate/confirm/ without JavaScript. "
        "This GET request does not activate the account."
    ),
)
async def activation_page(
    request: Request,
    token: str = Query(min_length=1, max_length=255, pattern=r"^\S+$"),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="account_activation.html",
        context={
            "token": token,
            "form_action": request.url_for("confirm_account_activation").path,
        },
        headers=ACTIVATION_PAGE_HEADERS,
    )


@router.post(
    "/register/",
    response_model=UserResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user",
    description=(
        "Register an inactive USER account with an email and a strong "
        "password. Creates an empty cart and an activation token valid "
        "for 24 hours, then sends an activation email. If email delivery "
        "fails, the account remains saved; use activation/resend to retry."
    ),
    responses={
        409: {
            "model": ErrorResponseSchema,
            "description": "A user with this email already exists.",
        },
        500: {
            "model": ErrorResponseSchema,
            "description": "The account could not be saved.",
        },
        503: {
            "model": ErrorResponseSchema,
            "description": (
                "The database or email delivery is unavailable. If the "
                "account was saved, retry through activation/resend."
            ),
        },
    },
)
async def register_user(
    user_data: UserRegistrationRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> UserResponseSchema:

    return await service.register_user(user_data)


@router.post(
    "/activate/confirm/",
    response_class=HTMLResponse,
    summary="Activate an account using the HTML form",
    description=(
        "Accepts a token as a form field and uses the same activation "
        "logic as the JSON endpoint. Returns an HTML success or error "
        "page. No JavaScript or authentication is required."
    ),
    responses={
        400: {
            "description": "Invalid or expired token; HTML error page."
        },
        409: {
            "description": "Account already active; HTML error page."
        },
        503: {
            "description": "Activation unavailable; HTML error page."
        },
    },
)
async def confirm_account_activation(
    request: Request,
    token: str = Form(min_length=1, max_length=255, pattern=r"^\S+$"),
    service: AccountService = Depends(get_account_service),
) -> HTMLResponse:
    status_code = status.HTTP_200_OK

    try:
        result = await service.activate_account(
            AccountActivationRequestSchema(token=token),
        )
        context = {"message": result.message}

    except HTTPException as error:
        status_code = error.status_code
        context = {"error": error.detail}

    return templates.TemplateResponse(
        request=request,
        name="account_activation.html",
        context=context,
        status_code=status_code,
        headers=ACTIVATION_PAGE_HEADERS,
    )


@router.post(
    "/activation/resend/",
    response_model=AccountMessageResponseSchema,
    summary="Resend an activation email",
    description=(
        "Accepts an email address. For an inactive account, replaces an "
        "expired or missing token with a new token valid for 24 hours. "
        "An unexpired token is resent without extending its expiration. "
        "Returns the same success message for unknown or active accounts "
        "without sending an email. No authentication is required. "
        "If email delivery fails, the saved token can be resent."
    ),
    responses={
        503: {
            "model": ErrorResponseSchema,
            "description": "The database or email delivery is unavailable.",
        },
    },
)
async def resend_activation_email(
    email_data: ActivationResendRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> AccountMessageResponseSchema:

    return await service.resend_activation_link(email_data)
