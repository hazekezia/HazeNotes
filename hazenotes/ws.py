"""WebSocket manager + real-time note endpoint, with session and permission auth."""
import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import config
from .security import can_view, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        # note_id -> set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, note_id: str, websocket: WebSocket):
        await websocket.accept()
        if note_id not in self.active_connections:
            self.active_connections[note_id] = set()
        self.active_connections[note_id].add(websocket)

    def disconnect(self, note_id: str, websocket: WebSocket):
        if note_id in self.active_connections:
            self.active_connections[note_id].discard(websocket)
            if not self.active_connections[note_id]:
                del self.active_connections[note_id]

    async def broadcast(self, note_id: str, message: Dict[str, Any], exclude: Optional[WebSocket] = None):
        """Broadcast message to all subscribers of a note except the sender"""
        if note_id not in self.active_connections:
            return

        dead_sockets = []
        payload = json.dumps(message)

        for ws in self.active_connections[note_id]:
            if ws is exclude:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                dead_sockets.append(ws)

        # Cleanup any disconnected sockets
        for dead in dead_sockets:
            self.disconnect(note_id, dead)


ws_manager = ConnectionManager()


@router.websocket('/ws/notes/{note_id}')
async def websocket_notes_endpoint(websocket: WebSocket, note_id: str):
    user = await get_current_user(websocket)  # WebSocket exposes .cookies like Request
    if config.AUTH_REQUIRED and not user:
        await websocket.close(code=4401)  # unauthenticated
        return

    from . import db

    note = await asyncio.to_thread(db.get_note, note_id)
    if not note or not can_view(user, note):
        await websocket.close(code=4403)  # forbidden / unknown note
        return

    await ws_manager.connect(note_id, websocket)
    try:
        while True:
            # Keep connection open; changes arrive via broadcast from HTTP handlers
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(note_id, websocket)
    except Exception:
        logger.exception('websocket error on note %s', note_id)
        ws_manager.disconnect(note_id, websocket)
