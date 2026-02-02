# APPENDIX_LOG.md
- PowerShell 출력/실측 원문을 날짜별로 누적(삭제 금지)

# 2026-02-02 16:02:46 +09:00ST — KIS diag proof (raw)

## 1) GET /api/diag/home (miss 가능)

## 2) GET /api/diag/home?refresh_kis=1 (refresh)

## 3) GET /api/diag/home (hit + kis_cached_at 유지)

## 4) KIS diag endpoints
=== GET /api/diag/kis-preflight ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)

=== GET /api/diag/kis-balance ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)

=== GET /api/diag/kis-balance-summary ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)

=== GET /api/diag/kis-check ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)

=== GET /api/diag/kis-refresh ===
대상 컴퓨터에서 연결을 거부했으므로 연결하지 못했습니다. (127.0.0.1:8000)

