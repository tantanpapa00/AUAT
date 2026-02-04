#!/bin/bash
# BBooster VPS 자동 설정 스크립트
# 사용법: curl -sSL <raw-url> | bash
# 또는: bash vps_setup.sh

set -e

echo "=========================================="
echo "  BBooster VPS Setup Script"
echo "=========================================="

# 색상
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. 시스템 업데이트
echo -e "${GREEN}[1/6] 시스템 업데이트...${NC}"
sudo apt update && sudo apt upgrade -y

# 2. Docker 설치
echo -e "${GREEN}[2/6] Docker 설치...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo -e "${YELLOW}Docker 설치 완료. 재접속 후 다시 실행하세요.${NC}"
    echo "명령어: exit 후 SSH 재접속, 그 다음 bash vps_setup.sh"
    exit 0
fi

# 3. Docker Compose 확인
echo -e "${GREEN}[3/6] Docker Compose 확인...${NC}"
if ! docker compose version &> /dev/null; then
    sudo apt install docker-compose-plugin -y
fi

# 4. Nginx + Certbot 설치
echo -e "${GREEN}[4/6] Nginx + Certbot 설치...${NC}"
sudo apt install nginx certbot python3-certbot-nginx -y

# 5. 프로젝트 클론 (이미 있으면 스킵)
echo -e "${GREEN}[5/6] 프로젝트 설정...${NC}"
cd ~
if [ ! -d "bbooster" ]; then
    echo -e "${YELLOW}bbooster 폴더가 없습니다.${NC}"
    echo "다음 명령어로 프로젝트를 클론하세요:"
    echo "  git clone <your-repo-url> bbooster"
    echo "  cd bbooster && cp .env.example .env && nano .env"
else
    cd bbooster
    if [ ! -f ".env" ]; then
        cp .env.example .env
        echo -e "${YELLOW}.env 파일을 수정하세요: nano .env${NC}"
    fi
fi

# 6. 방화벽 설정
echo -e "${GREEN}[6/6] 방화벽 설정...${NC}"
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw --force enable

echo ""
echo "=========================================="
echo -e "${GREEN}  기본 설정 완료!${NC}"
echo "=========================================="
echo ""
echo "다음 단계:"
echo "1. cd ~/bbooster"
echo "2. nano .env (환경변수 수정)"
echo "3. docker compose up -d"
echo "4. bash scripts/setup_nginx.sh <your-domain.com>"
echo ""
