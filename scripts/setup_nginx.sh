#!/bin/bash
# Nginx + SSL 자동 설정 스크립트
# 사용법: bash setup_nginx.sh your-domain.com

set -e

DOMAIN=$1

if [ -z "$DOMAIN" ]; then
    echo "사용법: bash setup_nginx.sh <your-domain.com>"
    echo "예시: bash setup_nginx.sh bbooster.example.com"
    exit 1
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "  Nginx + SSL 설정: $DOMAIN"
echo "=========================================="

# 프로젝트 경로 확인
PROJECT_DIR="$HOME/bbooster"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: $PROJECT_DIR 폴더가 없습니다."
    exit 1
fi

# Nginx 설정 파일 생성
echo -e "${GREEN}[1/4] Nginx 설정 파일 생성...${NC}"
sudo tee /etc/nginx/sites-available/bbooster > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    # 랜딩 페이지 (정적 파일)
    root $PROJECT_DIR/landing;
    index index.html;

    # 정적 파일
    location / {
        try_files \$uri \$uri/ =404;
    }

    # 법적 페이지
    location ~ ^/(terms|privacy|risk)\.html$ {
        try_files \$uri =404;
    }

    # 대시보드 (FastAPI 루트)
    location /dashboard {
        rewrite ^/dashboard(.*) /\$1 break;
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # API 엔드포인트
    location /api {
        proxy_pass http://127.0.0.1:8000/api;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # TradingView 웹훅
    location /tv {
        proxy_pass http://127.0.0.1:8000/tv;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host \$host;
    }

    # Swagger docs
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_set_header Host \$host;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
        proxy_set_header Host \$host;
    }
}
EOF

# 설정 활성화
echo -e "${GREEN}[2/4] Nginx 설정 활성화...${NC}"
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/bbooster /etc/nginx/sites-enabled/

# Nginx 테스트 및 재시작
echo -e "${GREEN}[3/4] Nginx 테스트...${NC}"
sudo nginx -t
sudo systemctl reload nginx

# SSL 인증서 발급
echo -e "${GREEN}[4/4] SSL 인증서 발급 (Let's Encrypt)...${NC}"
echo -e "${YELLOW}이메일을 입력하라는 프롬프트가 나옵니다.${NC}"
sudo certbot --nginx -d $DOMAIN

echo ""
echo "=========================================="
echo -e "${GREEN}  설정 완료!${NC}"
echo "=========================================="
echo ""
echo "접속 URL:"
echo "  - 랜딩:    https://$DOMAIN"
echo "  - 대시보드: https://$DOMAIN/dashboard"
echo "  - API:     https://$DOMAIN/api/health"
echo "  - 웹훅:    https://$DOMAIN/tv"
echo ""
echo "TradingView 웹훅 URL:"
echo "  https://$DOMAIN/tv"
echo ""
