from src.api.v1.auth import router as auth_router
from src.api.v1.channels import router as channels_router
from src.api.v1.pipeline import router as pipeline_router
from src.api.v1.platforms import router as platforms_router
from src.api.v1.retries import router as retries_router
from src.api.v1.rss import router as rss_router
from src.api.v1.users import router as users_router
from src.api.v1.videos import router as videos_router

routers = [
    auth_router,
    users_router,
    channels_router,
    platforms_router,
    videos_router,
    pipeline_router,
    retries_router,
    rss_router,
]
