"""
Real-time WebSocket Connection Manager for Notepad Web
Handles concurrent client subscriptions per note and broadcasts real-time changes.
"""

from typing import Dict, Set, Optional, Any
from starlette.websockets import WebSocket
import json
import logging

logger = logging.getLogger("websocket_manager")

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
            except Exception as e:
                dead_sockets.append(ws)

        # Cleanup any disconnected sockets
        for dead in dead_sockets:
            self.disconnect(note_id, dead)

ws_manager = ConnectionManager()
