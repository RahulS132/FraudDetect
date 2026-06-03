"""In-process async pub/sub broker backing the Server-Sent Events stream.

Each connected SSE client registers an ``asyncio.Queue``. Producers (the upload
pipeline, the bulk-create endpoint, the notification service) publish typed
events that are fanned out to the relevant subscribers:

    • a specific ``user_id``           → that user's own browser tabs
    • the special audience ``ADMINS``  → every connected admin

Events are JSON-serialisable dicts of the form::

    {"event": "<name>", "data": {...}}

This is intentionally a single-process broker (no Redis). It matches the
current single-instance FastAPI deployment described in the README. To scale
horizontally later, swap ``EventBroker.publish`` for a Redis pub/sub backend —
the public method signatures can stay the same.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional, Set

ADMINS = "__admins__"  # sentinel audience for "all admins"


class EventBroker:
    def __init__(self) -> None:
        # recipient key -> set of subscriber queues
        # recipient key is either a user_id string or the ADMINS sentinel.
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, keys: list[str]) -> asyncio.Queue:
        """Register a queue under one or more recipient keys.

        A normal user subscribes under [user_id]. An admin subscribes under
        [user_id, ADMINS] so they receive both their own and broadcast events.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            for key in keys:
                self._subscribers.setdefault(key, set()).add(queue)
        # Stash the keys on the queue object so we can clean up on unsubscribe.
        queue._broker_keys = keys  # type: ignore[attr-defined]
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        keys = getattr(queue, "_broker_keys", [])
        async with self._lock:
            for key in keys:
                subs = self._subscribers.get(key)
                if subs and queue in subs:
                    subs.discard(queue)
                    if not subs:
                        self._subscribers.pop(key, None)

    async def publish(self, key: str, event: str, data: Dict[str, Any]) -> None:
        """Fan an event out to every subscriber registered under ``key``.

        Never raises on a slow/full consumer — that subscriber simply drops the
        event (best-effort delivery; the client also polls as a fallback).
        """
        payload = {"event": event, "data": data}
        async with self._lock:
            subs = list(self._subscribers.get(key, set()))
        for q in subs:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop rather than block the producer.
                pass

    async def publish_to_user(self, user_id: str, event: str, data: Dict[str, Any]) -> None:
        await self.publish(user_id, event, data)

    async def publish_to_admins(self, event: str, data: Dict[str, Any]) -> None:
        await self.publish(ADMINS, event, data)

    @staticmethod
    def format_sse(payload: Dict[str, Any]) -> str:
        """Encode a payload as an SSE wire frame."""
        return f"event: {payload['event']}\ndata: {json.dumps(payload['data'], default=str)}\n\n"


# Module-level singleton shared across routers.
broker = EventBroker()
