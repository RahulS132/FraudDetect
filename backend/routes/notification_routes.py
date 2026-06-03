"""Notifications REST API + the Server-Sent Events stream.

    GET  /api/notifications              list recent notifications + unread count
    POST /api/notifications/mark-read    mark some/all as read
    GET  /api/stream?token=<jwt>         SSE stream (notifications + data-change events)

The SSE endpoint authenticates via a ``token`` query parameter because the
browser ``EventSource`` API cannot attach an Authorization header. The token is
the same JWT used everywhere else.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool

from models import NotificationListResponse, MarkReadRequest, UserRole
from auth import get_current_user, verify_token
from services import notifications as notif_service
from services.events import broker, ADMINS

router = APIRouter(tags=["Notifications"])


def _is_admin(user: dict) -> bool:
    return user.get("role") == UserRole.ADMIN.value


@router.get("/api/notifications", response_model=NotificationListResponse)
async def list_notifications(
    current_user: dict = Depends(get_current_user),
    limit: int = 50,
):
    return await run_in_threadpool(
        notif_service.list_for_recipient,
        user_id=current_user["id"],
        is_admin=_is_admin(current_user),
        limit=limit,
    )


@router.post("/api/notifications/mark-read")
async def mark_notifications_read(
    payload: MarkReadRequest,
    current_user: dict = Depends(get_current_user),
):
    modified = await run_in_threadpool(
        notif_service.mark_read,
        user_id=current_user["id"],
        is_admin=_is_admin(current_user),
        notification_ids=payload.notification_ids,
    )
    return {"success": True, "modified": modified}


@router.get("/api/stream")
async def event_stream(request: Request, token: str):
    """Server-Sent Events stream for the authenticated user.

    Subscribes to:
        • the user's own channel (notifications + data-change events)
        • the ADMINS broadcast channel (if the user is an admin)
    """
    # Authenticate from the query-param token (raises 401 on failure).
    token_data = verify_token(token)
    user_id = token_data.id
    is_admin = token_data.role == UserRole.ADMIN.value

    keys = [user_id]
    if is_admin:
        keys.append(ADMINS)

    queue = await broker.subscribe(keys)

    async def event_generator():
        try:
            # Initial hello so the client knows the stream is live.
            yield broker.format_sse({"event": "connected", "data": {"ok": True}})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield broker.format_sse(payload)
                except asyncio.TimeoutError:
                    # Keepalive comment to hold the connection open through proxies.
                    yield ": keepalive\n\n"
        finally:
            await broker.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
        },
    )
