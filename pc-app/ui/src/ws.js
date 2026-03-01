/**
 * BBooster WebSocket Client
 * 실시간 알림 수신을 위한 WebSocket 연결 관리
 */

// WebSocket 상태
let ws = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 3000;
const PING_INTERVAL = 30000;
let pingTimer = null;

// 알림 핸들러 목록
const notificationHandlers = [];

/**
 * WebSocket 서버 URL 생성
 */
function getWsUrl(token) {
    const host = window.API_BASE_URL || 'https://qube-system.com';
    const wsProtocol = host.startsWith('https') ? 'wss' : 'ws';
    const wsHost = host.replace(/^https?:\/\//, '');
    return `${wsProtocol}://${wsHost}/ws?token=${encodeURIComponent(token)}`;
}

/**
 * WebSocket 연결
 */
export function connect(token) {
    if (!token) {
        console.log('[WS] 토큰 없음 - 연결 스킵');
        return;
    }

    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
        console.log('[WS] 이미 연결됨');
        return;
    }

    const url = getWsUrl(token);
    console.log('[WS] 연결 시도...');

    try {
        ws = new WebSocket(url);

        ws.onopen = () => {
            console.log('[WS] 연결 성공');
            reconnectAttempts = 0;
            startPing();
            notifyConnectionChange(true);
        };

        ws.onmessage = (event) => {
            try {
                // pong 응답 처리
                if (event.data === 'pong') {
                    return;
                }

                const data = JSON.parse(event.data);
                console.log('[WS] 메시지 수신:', data);
                handleNotification(data);
            } catch (e) {
                console.error('[WS] 메시지 파싱 실패:', e);
            }
        };

        ws.onclose = (event) => {
            console.log('[WS] 연결 종료:', event.code, event.reason);
            stopPing();
            notifyConnectionChange(false);
            scheduleReconnect(token);
        };

        ws.onerror = (error) => {
            console.error('[WS] 에러:', error);
        };

    } catch (e) {
        console.error('[WS] 연결 실패:', e);
        scheduleReconnect(token);
    }
}

/**
 * WebSocket 연결 종료
 */
export function disconnect() {
    stopPing();
    clearReconnect();

    if (ws) {
        ws.close(1000, 'User disconnect');
        ws = null;
    }
    console.log('[WS] 연결 해제됨');
}

/**
 * Ping 시작 (연결 유지)
 */
function startPing() {
    stopPing();
    pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
        }
    }, PING_INTERVAL);
}

/**
 * Ping 중지
 */
function stopPing() {
    if (pingTimer) {
        clearInterval(pingTimer);
        pingTimer = null;
    }
}

/**
 * 재연결 예약
 */
function scheduleReconnect(token) {
    clearReconnect();

    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.log('[WS] 최대 재연결 시도 초과');
        return;
    }

    reconnectAttempts++;
    const delay = RECONNECT_DELAY * reconnectAttempts;
    console.log(`[WS] ${delay}ms 후 재연결 시도 (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);

    reconnectTimer = setTimeout(() => {
        connect(token);
    }, delay);
}

/**
 * 재연결 타이머 취소
 */
function clearReconnect() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
}

/**
 * 알림 핸들러 등록
 */
export function onNotification(handler) {
    if (typeof handler === 'function') {
        notificationHandlers.push(handler);
    }
}

/**
 * 알림 핸들러 제거
 */
export function offNotification(handler) {
    const idx = notificationHandlers.indexOf(handler);
    if (idx !== -1) {
        notificationHandlers.splice(idx, 1);
    }
}

/**
 * 알림 처리
 */
function handleNotification(data) {
    // 모든 핸들러에게 전달
    notificationHandlers.forEach(handler => {
        try {
            handler(data);
        } catch (e) {
            console.error('[WS] 핸들러 에러:', e);
        }
    });

    // 브라우저 알림 표시 (권한 있으면)
    showBrowserNotification(data);
}

/**
 * 브라우저 알림 표시
 */
function showBrowserNotification(data) {
    if (!('Notification' in window)) return;

    if (Notification.permission === 'granted') {
        createNotification(data);
    } else if (Notification.permission !== 'denied') {
        Notification.requestPermission().then(permission => {
            if (permission === 'granted') {
                createNotification(data);
            }
        });
    }
}

/**
 * 알림 생성
 */
function createNotification(data) {
    const notification = new Notification(data.title || 'BBooster 알림', {
        body: data.message || '',
        icon: '/favicon.ico',
        tag: data.type || 'notification',
        silent: false
    });

    notification.onclick = () => {
        window.focus();
        notification.close();
    };

    // 5초 후 자동 닫기
    setTimeout(() => notification.close(), 5000);
}

/**
 * 연결 상태 변경 알림
 */
const connectionHandlers = [];

export function onConnectionChange(handler) {
    if (typeof handler === 'function') {
        connectionHandlers.push(handler);
    }
}

function notifyConnectionChange(connected) {
    connectionHandlers.forEach(handler => {
        try {
            handler(connected);
        } catch (e) {
            console.error('[WS] 연결 핸들러 에러:', e);
        }
    });
}

/**
 * 연결 상태 확인
 */
export function isConnected() {
    return ws && ws.readyState === WebSocket.OPEN;
}

/**
 * 재연결 시도 횟수 초기화
 */
export function resetReconnect() {
    reconnectAttempts = 0;
}
