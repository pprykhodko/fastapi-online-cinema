from src.api.v1.routers.accounts import router as accounts_router
from src.api.v1.routers.profiles import router as profiles_router
from src.api.v1.routers.movies import router as movies_router
from src.api.v1.routers.genres import router as genres_router
from src.api.v1.routers.stars import router as stars_router
from src.api.v1.routers.directors import router as directors_router
from src.api.v1.routers.certifications import router as certifications_router
from src.api.v1.routers.favorites import router as favorites_router


__all__ = [
    "accounts_router", "profiles_router", "movies_router", "genres_router",
    "stars_router", "directors_router", "certifications_router",
    "favorites_router",
]
