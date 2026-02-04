#!/bin/bash
# BBooster 원클릭 배포 스크립트
# VPS에서 실행: bash deploy_all.sh <domain>

set -e

DOMAIN=$1

if [ -z "$DOMAIN" ]; then
    echo "=========================================="
    echo "  BBooster 원클릭 배포"
    echo "=========================================="
    echo ""
    echo "사용법: bash deploy_all.sh <your-domain.com>"
    echo ""
    echo "예시:"
    echo "  bash deploy_all.sh bbooster.mysite.com"
    echo ""
    exit 1
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "=========================================="
echo "  BBooster 배포 시작: $DOMAIN"
echo "=========================================="

# 1. Docker 확인
echo -e "${GREEN}[1/5] Docker 확인...${NC}"
if ! command -v docker &> /dev/null; then
    echo "Docker 설치 중..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo -e "${RED}Docker 설치 완료. 재접속 후 다시 실행하세요.${NC}"
    echo "  exit"
    echo "  (SSH 재접속)"
    echo "  bash deploy_all.sh $DOMAIN"
    exit 1
fi

# 2. 필수 패키지
echo -e "${GREEN}[2/5] 필수 패키지 설치...${NC}"
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx

# 3. 프로젝트 확인
echo -e "${GREEN}[3/5] 프로젝트 확인...${NC}"
cd ~
if [ ! -d "bbooster" ]; then
    echo -e "${RED}Error: ~/bbooster 폴더가 없습니다.${NC}"
    echo "먼저 프로젝트를 클론하세요:"
    echo "  git clone <repo-url> bbooster"
    exit 1
fi

cd bbooster

# .env 확인
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}.env 파일이 생성되었습니다. 수정이 필요합니다.${NC}"
        echo "nano .env 로 수정 후 다시 실행하세요."
        exit 1
    fi
fi

# 4. Docker 실행
echo -e "${GREEN}[4/5] Docker 컨테이너 시작...${NC}"
docker compose down 2>/dev/null || true
docker compose up -d

# DB 초기화 대기
echo "DB 준비 대기 중 (10초)..."
sleep 10

# DB 스키마 확인 및 초기화
if [ -f "scripts/init_schema.sql" ]; then
    echo "DB 스키마 초기화..."
    docker cp scripts/init_schema.sql bbooster-db:/tmp/
    docker exec bbooster-db psql -U bbooster -d bbooster -f /tmp/init_schema.sql 2>/dev/null || true
fi

# Health check
echo "서버 상태 확인..."
sleep 5
curl -s http://localhost:8000/api/health || echo "서버 시작 중..."

# 5. Nginx + SSL
echo -e "${GREEN}[5/5] Nginx + SSL 설정...${NC}"

# Nginx 설정
sudo tee /etc/nginx/sites-available/bbooster > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    root $HOME/bbooster/landing;
    index index.html;

    location / {
        try_files \$uri \$uri/ =404;
    }

    location ~ ^/(terms|privacy|risk)\.html$ {
        try_files \$uri =404;
    }

    location /dashboard {
        rewrite ^/dashboard(.*) /\$1 break;
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api {
        proxy_pass http://127.0.0.1:8000/api;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /tv {
        proxy_pass http://127.0.0.1:8000/tv;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }

    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
    }
}
EOF

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/bbooster /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 방화벽
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# SSL
echo ""
echo -e "${YELLOW}SSL 인증서를 발급합니다. 이메일 입력이 필요합니다.${NC}"
sudo certbot --nginx -d $DOMAIN

echo ""
echo "=========================================="
echo -e "${GREEN}  배포 완료!${NC}"
echo "=========================================="
echo ""
echo "접속 URL:"
echo "  https://$DOMAIN              - 랜딩 페이지"
echo "  https://$DOMAIN/dashboard    - 대시보드"
echo "  https://$DOMAIN/api/health   - API 상태"
echo "  https://$DOMAIN/tv           - TradingView 웹훅"
echo ""
echo "컨테이너 상태: docker compose ps"
echo "로그 확인:     docker compose logs -f app"
echo ""
