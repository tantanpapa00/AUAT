#!/bin/bash
# BBooster 무중단 배포 스크립트
# VPS에서 실행: bash deploy.sh [version]
# 예: bash deploy.sh 1.2.0

set -e

VERSION=${1:-$(date +%Y%m%d.%H%M)}
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "=========================================="
echo "  BBooster 배포 v$VERSION"
echo "  Commit: $GIT_COMMIT"
echo "=========================================="

cd /root/bbooster

# 1. Git pull
echo -e "${GREEN}[1/5] 코드 업데이트...${NC}"
git pull

# 2. 환경변수 설정
export APP_VERSION=$VERSION
export BUILD_DATE=$BUILD_DATE
export GIT_COMMIT=$GIT_COMMIT

# 3. 이미지 빌드
echo -e "${GREEN}[2/5] Docker 이미지 빌드...${NC}"
docker compose build --build-arg APP_VERSION=$VERSION --build-arg BUILD_DATE=$BUILD_DATE --build-arg GIT_COMMIT=$GIT_COMMIT

# 4. 기존 컨테이너 태그 백업
echo -e "${GREEN}[3/5] 롤백용 이미지 태그 저장...${NC}"
docker tag bbooster-app:latest bbooster-app:rollback 2>/dev/null || echo "기존 이미지 없음, 스킵"

# 5. 컨테이너 교체
echo -e "${GREEN}[4/5] 컨테이너 교체...${NC}"
docker compose up -d --no-deps app

# 6. 헬스체크 대기
echo -e "${GREEN}[5/5] 헬스체크 대기...${NC}"
MAX_WAIT=120
WAIT=0
while [ $WAIT -lt $MAX_WAIT ]; do
    HEALTH=$(curl -s http://localhost:8000/api/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ok',''))" 2>/dev/null || echo "")
    if [ "$HEALTH" = "True" ]; then
        echo -e "${GREEN}서버 정상 가동!${NC}"
        break
    fi
    echo "대기 중... ($WAIT/$MAX_WAIT 초)"
    sleep 5
    WAIT=$((WAIT + 5))
done

if [ $WAIT -ge $MAX_WAIT ]; then
    echo -e "${RED}헬스체크 실패! 롤백 필요${NC}"
    echo "롤백: docker compose down && docker tag bbooster-app:rollback bbooster-app:latest && docker compose up -d"
    exit 1
fi

# 결과 출력
echo ""
echo "=========================================="
echo -e "${GREEN}  배포 완료!${NC}"
echo "=========================================="
curl -s http://localhost:8000/api/health | python3 -m json.tool
echo ""
echo "버전: $VERSION"
echo "커밋: $GIT_COMMIT"
echo "시간: $BUILD_DATE"
echo ""
