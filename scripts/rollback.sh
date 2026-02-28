#!/bin/bash
# BBooster 롤백 스크립트
# 배포 실패 시 직전 버전으로 롤백
# VPS에서 실행: bash rollback.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo -e "${YELLOW}  BBooster 롤백 시작${NC}"
echo "=========================================="

cd /root/bbooster

# 롤백 이미지 확인
if ! docker image inspect bbooster-app:rollback &>/dev/null; then
    echo -e "${RED}롤백 이미지가 없습니다!${NC}"
    echo "bbooster-app:rollback 태그가 존재하지 않습니다."
    exit 1
fi

# 현재 버전 확인
CURRENT_VERSION=$(curl -s http://localhost:8000/api/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('version','unknown'))" 2>/dev/null || echo "unknown")
echo "현재 버전: $CURRENT_VERSION"

# 컨테이너 중지
echo -e "${GREEN}[1/3] 현재 컨테이너 중지...${NC}"
docker compose stop app

# 이미지 태그 교체
echo -e "${GREEN}[2/3] 롤백 이미지로 교체...${NC}"
docker tag bbooster-app:rollback bbooster-app:latest

# 컨테이너 재시작
echo -e "${GREEN}[3/3] 컨테이너 재시작...${NC}"
docker compose up -d app

# 헬스체크 대기
echo "헬스체크 대기..."
sleep 30

HEALTH=$(curl -s http://localhost:8000/api/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "{}")
echo "$HEALTH"

ROLLBACK_VERSION=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('version','unknown'))" 2>/dev/null || echo "unknown")

echo ""
echo "=========================================="
echo -e "${GREEN}  롤백 완료!${NC}"
echo "=========================================="
echo "이전 버전: $CURRENT_VERSION"
echo "롤백 버전: $ROLLBACK_VERSION"
echo ""
