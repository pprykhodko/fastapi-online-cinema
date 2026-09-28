from secrets import token_urlsafe

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.notifications.emails import TEMPLATES_DIR


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/password-reset/", response_class=HTMLResponse)
async def password_reset_page(request: Request) -> HTMLResponse:
    """
    Render the public password reset form with a fresh script nonce.

    Args:
        request (Request): Incoming HTTP request.

    Returns:
        HTMLResponse: HTTP response for the requested operation.
    """
    nonce = token_urlsafe(24)
    return templates.TemplateResponse(
        request=request,
        name="password_reset.html",
        context={"nonce": nonce},
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": (
                "default-src 'none'; connect-src 'self'; "
                f"script-src 'nonce-{nonce}'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
            )
        }
    )
