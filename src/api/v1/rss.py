from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    get_channel_crud,
    get_pipeline_run_crud,
    get_rss_feed_crud,
    get_rss_news_item_crud,
)
from src.core.database import get_async_session
from src.core.exception_handling_route import ExceptionHandlingRoute
from src.core.permission import Permission
from src.models.auth import User
from src.schemas.rss import (
    ChannelFeedGrantIn,
    RssFeedCreateIn,
    RssFeedOut,
    RssNewsItemOut,
    RssScheduleOut,
)
from src.services import rss as rss_service
from src.utils.require_permission import require_permission

router = APIRouter(
    route_class=ExceptionHandlingRoute,
    prefix="/api/v1/rss",
    tags=["rss"],
)


@router.get("/feeds", response_model=list[RssFeedOut])
async def list_feeds(
    _user: User = Depends(require_permission(Permission.RSS_FEED_READ)),
    db: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100,
    feed_crud=Depends(get_rss_feed_crud),
):
    return await rss_service.list_feeds(
        db,
        skip=skip,
        limit=limit,
        feed_crud=feed_crud,
    )


@router.post("/feeds", response_model=RssFeedOut, status_code=status.HTTP_201_CREATED)
async def create_feed(
    data: RssFeedCreateIn,
    _user: User = Depends(require_permission(Permission.RSS_FEED_MANAGE)),
    db: AsyncSession = Depends(get_async_session),
    feed_crud=Depends(get_rss_feed_crud),
):
    return await rss_service.create_feed(db, data, feed_crud=feed_crud)


@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape(
    _user: User = Depends(require_permission(Permission.RSS_FEED_MANAGE)),
):
    task_id = rss_service.trigger_rss_scrape()
    return {"message": "RSS scrape enqueued", "task_id": task_id}


@router.get("/channels/{channel_id}/feeds", response_model=list[RssFeedOut])
async def list_channel_feeds(
    channel_id: int,
    user: User = Depends(require_permission(Permission.RSS_FEED_READ)),
    db: AsyncSession = Depends(get_async_session),
    feed_crud=Depends(get_rss_feed_crud),
):
    return await rss_service.list_channel_granted_feeds(
        db,
        user,
        channel_id,
        feed_crud=feed_crud,
    )


@router.post("/channels/{channel_id}/feeds", response_model=list[RssFeedOut])
async def grant_channel_feeds(
    channel_id: int,
    data: ChannelFeedGrantIn,
    user: User = Depends(require_permission(Permission.RSS_FEED_READ)),
    db: AsyncSession = Depends(get_async_session),
    feed_crud=Depends(get_rss_feed_crud),
):
    return await rss_service.grant_feeds_to_channel(
        db,
        user,
        channel_id,
        data.feed_ids,
        feed_crud=feed_crud,
    )


@router.delete(
    "/channels/{channel_id}/feeds/{feed_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_channel_feed(
    channel_id: int,
    feed_id: int,
    user: User = Depends(require_permission(Permission.RSS_FEED_READ)),
    db: AsyncSession = Depends(get_async_session),
    feed_crud=Depends(get_rss_feed_crud),
):
    await rss_service.revoke_feed_from_channel(
        db,
        user,
        channel_id,
        feed_id,
        feed_crud=feed_crud,
    )


@router.get("/channels/{channel_id}/news", response_model=list[RssNewsItemOut])
async def list_channel_news(
    channel_id: int,
    user: User = Depends(require_permission(Permission.RSS_FEED_READ)),
    db: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 50,
    news_item_crud=Depends(get_rss_news_item_crud),
):
    return await rss_service.list_channel_news(
        db,
        user,
        channel_id,
        skip=skip,
        limit=limit,
        news_item_crud=news_item_crud,
    )


@router.post(
    "/channels/{channel_id}/schedule",
    response_model=RssScheduleOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def schedule_channel_pipelines(
    channel_id: int,
    force: bool = False,
    user: User = Depends(require_permission(Permission.RSS_FEED_READ)),
    db: AsyncSession = Depends(get_async_session),
    feed_crud=Depends(get_rss_feed_crud),
    news_item_crud=Depends(get_rss_news_item_crud),
    channel_crud=Depends(get_channel_crud),
    pipeline_run_crud=Depends(get_pipeline_run_crud),
):
    return await rss_service.schedule_channel_pipelines(
        db,
        user,
        channel_id,
        force=force,
        feed_crud=feed_crud,
        news_item_crud=news_item_crud,
        channel_crud=channel_crud,
        pipeline_run_crud=pipeline_run_crud,
    )
