from fastapi import APIRouter, Depends, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from src.security.docs import get_docs_user


router = APIRouter(
    dependencies=[Depends(get_docs_user)],
    include_in_schema=False
)
DOCS_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer"
}


@router.get("/openapi.json", name="protected_openapi")
async def openapi_schema(request: Request) -> JSONResponse:
    return JSONResponse(request.app.openapi(), headers=DOCS_HEADERS)


@router.get("/docs")
async def swagger_docs(request: Request) -> HTMLResponse:
    response = get_swagger_ui_html(
        openapi_url=request.url_for("protected_openapi").path,
        title=f"{request.app.title} - Swagger UI"
    )
    response.headers.update(DOCS_HEADERS)

    return response


@router.get("/redoc")
async def redoc_docs(request: Request) -> HTMLResponse:
    response = get_redoc_html(
        openapi_url=request.url_for("protected_openapi").path,
        title=f"{request.app.title} - ReDoc"
    )
    response.headers.update(DOCS_HEADERS)

    return response
