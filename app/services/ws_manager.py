"""
WebSocket 연결 관리자.
사용자별 WebSocket 연결을 관리하고, 이벤트를 전송한다.
"""
from typing import Dict, List
from fastapi import WebSocket
from app.services.notification import NotificationEvent, notification_manager


class WebSocketManager:
    """WebSocket 연결 관리"""

    def __init__(self):
        # user_id → [WebSocket, ...] (한 사용자가 여러 탭/기기에서 연결 가능)
        self._connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket):
        """새 연결 등록."""
        await ws.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(ws)
        print(f"[WS] 연결: user={user_id}, 총 {len(self._connections[user_id])}개 연결")

    def disconnect(self, user_id: int, ws: WebSocket):
        """연결 해제."""
        if user_id in self._connections:
            self._connections[user_id] = [w for w in self._connections[user_id] if w != ws]
            if not self._connections[user_id]:
                del self._connections[user_id]
        print(f"[WS] 해제: user={user_id}")

    async def send_to_user(self, user_id: int, data: dict):
        """특정 사용자의 모든 연결에 메시지 전송."""
        if user_id not in self._connections:
            return

        dead = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_json(data)
            except Exception as e:
                print(f"[WS] 전송 실패: {e}")
                dead.append(ws)

        # 끊어진 연결 정리
        for ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast(self, data: dict):
        """모든 연결에 메시지 전송 (시스템 알림 등)."""
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, data)

    @property
    def connection_count(self) -> int:
        """총 연결 수."""
        return sum(len(conns) for conns in self._connections.values())

    @property
    def user_count(self) -> int:
        """연결된 사용자 수."""
        return len(self._connections)


# 글로벌 싱글톤
ws_manager = WebSocketManager()


# =============================================================================
# notification_manager에 WebSocket 핸들러 등록
# =============================================================================

async def _ws_notification_handler(event: NotificationEvent):
    """알림 이벤트 → WebSocket 전송."""
    await ws_manager.send_to_user(event.user_id, event.to_dict())


notification_manager.register(_ws_notification_handler)
