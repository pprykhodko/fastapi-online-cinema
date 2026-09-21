from src.api.v1.routers.accounts import router as accounts_router
from src.api.v1.routers.profiles import router as profiles_router
from src.api.v1.routers.movies import router as movies_router


__all__ = ["accounts_router", "profiles_router", "movies_router"]
