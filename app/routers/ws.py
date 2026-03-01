"""
WebSocket 엔드포인트.
실시간 알림 전송을 위한 WebSocket 연결 관리.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.services.ws_manager import ws_manager
from app.auth import verify_token

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    WebSocket 연결 엔드포인트.

    연결 시 JWT 토큰으로 인증 필요.
    URL: ws://host/ws?token=<jwt_token>

    수신 메시지 형식:
    {
        "type": "order_filled" | "signal_received" | "report_done" | ...,
        "title": "알림 제목",
        "message": "알림 내용",
        "data": { ... }
    }
    """
    # JWT 토큰 검증
    token_data = verify_token(token)
    if not token_data or not token_data.user_id:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    user_id = token_data.user_id

    # 연결 등록
    await ws_manager.connect(user_id, websocket)

    try:
        # 연결 유지 (클라이언트 메시지 수신 대기)
        while True:
            try:
                # 클라이언트로부터 메시지 수신 (ping/pong 또는 커스텀 메시지)
                data = await websocket.receive_text()

                # ping 메시지 처리
                if data == "ping":
                    await websocket.send_text("pong")

            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"[WS] 수신 에러: {e}")
                break

    finally:
        # 연결 해제
        ws_manager.disconnect(user_id, websocket)


@router.get("/ws/status")
async def websocket_status():
    """WebSocket 연결 상태 조회."""
    return {
        "success": True,
        "data": {
            "total_connections": ws_manager.connection_count,
            "total_users": ws_manager.user_count
        }
    }
