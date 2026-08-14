import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from . import db, listener
from .broadcaster import broadcaster
from .schemas import AnnouncementsPage, ListenerStatus

router = APIRouter()


# Static paths registered before the /{ann_id} catch-all below, so they
# can't be shadowed by it.
@router.get("/status", response_model=ListenerStatus)
def listener_status() -> dict:
    return listener.get_status()


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    queue = broadcaster.subscribe()

    async def event_gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("", response_model=AnnouncementsPage)
def list_announcements(
    limit: int = Query(50, le=200),
    offset: int = 0,
    exchange: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    items, total = db.fetch_announcements(limit=limit, offset=offset, exchange=exchange, search=search)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{ann_id}")
def get_announcement(ann_id: int) -> dict:
    row = db.fetch_announcement(ann_id)
    if not row:
        raise HTTPException(404, "Announcement not found")
    return row
