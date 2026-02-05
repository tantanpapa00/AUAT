#!/bin/bash
# ssl-setup.sh - Let's Encrypt SSL 인증서 설정 스크립트
# VPS 서버에서 실행

set -e

# ============================================
# 설정 (수정 필요)
# ============================================
DOMAIN="your-domain.com"
EMAIL="your-email@example.com"
WEBROOT="/var/www/certbot"

# ============================================
# 색상 출력
# ============================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================
# 1단계: Certbot 설치
# ============================================
echo_info "1단계: Certbot 설치 확인..."

if ! command -v certbot &> /dev/null; then
    echo_info "Certbot 설치 중..."

    # Ubuntu/Debian
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y certbot python3-certbot-nginx
    # CentOS/RHEL
    elif command -v yum &> /dev/null; then
        sudo yum install -y epel-release
        sudo yum install -y certbot python3-certbot-nginx
    else
        echo_error "지원하지 않는 OS입니다. 수동으로 certbot을 설치하세요."
        exit 1
    fi
else
    echo_info "Certbot이 이미 설치되어 있습니다."
fi

# ============================================
# 2단계: 웹루트 디렉토리 생성
# ============================================
echo_info "2단계: 웹루트 디렉토리 생성..."

sudo mkdir -p $WEBROOT
sudo chown -R www-data:www-data $WEBROOT 2>/dev/null || sudo chown -R nginx:nginx $WEBROOT

# ============================================
# 3단계: SSL 인증서 발급
# ============================================
echo_info "3단계: SSL 인증서 발급..."

# 도메인 확인
if [ "$DOMAIN" == "your-domain.com" ]; then
    echo_error "DOMAIN 변수를 실제 도메인으로 수정하세요!"
    echo_warn "예: DOMAIN=\"bbooster.example.com\""
    exit 1
fi

if [ "$EMAIL" == "your-email@example.com" ]; then
    echo_error "EMAIL 변수를 실제 이메일로 수정하세요!"
    exit 1
fi

# 인증서 발급 (웹루트 방식)
echo_info "인증서 발급 중... (도메인: $DOMAIN)"

sudo certbot certonly \
    --webroot \
    --webroot-path=$WEBROOT \
    -d $DOMAIN \
    -d www.$DOMAIN \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --non-interactive

# ============================================
# 4단계: Nginx 설정 업데이트
# ============================================
echo_info "4단계: Nginx 설정 파일의 도메인 교체..."

NGINX_CONF="/etc/nginx/conf.d/bbooster.conf"

if [ -f "$NGINX_CONF" ]; then
    sudo sed -i "s/your-domain.com/$DOMAIN/g" $NGINX_CONF
    echo_info "Nginx 설정 파일 업데이트 완료"
else
    echo_warn "Nginx 설정 파일을 찾을 수 없습니다: $NGINX_CONF"
    echo_warn "수동으로 도메인을 교체하세요."
fi

# ============================================
# 5단계: Nginx 재시작
# ============================================
echo_info "5단계: Nginx 설정 테스트 및 재시작..."

sudo nginx -t
if [ $? -eq 0 ]; then
    sudo systemctl reload nginx
    echo_info "Nginx 재시작 완료"
else
    echo_error "Nginx 설정 오류! 로그를 확인하세요."
    exit 1
fi

# ============================================
# 6단계: 자동 갱신 설정
# ============================================
echo_info "6단계: 인증서 자동 갱신 크론잡 확인..."

# certbot 타이머 확인 (systemd)
if systemctl list-timers | grep -q certbot; then
    echo_info "Certbot 자동 갱신 타이머가 이미 설정되어 있습니다."
else
    echo_warn "수동으로 크론잡을 추가하세요:"
    echo "    0 0,12 * * * root certbot renew --quiet --post-hook 'systemctl reload nginx'"
fi

# ============================================
# 완료
# ============================================
echo ""
echo_info "=========================================="
echo_info "SSL 설정 완료!"
echo_info "=========================================="
echo ""
echo "  - 도메인: https://$DOMAIN"
echo "  - 인증서 위치: /etc/letsencrypt/live/$DOMAIN/"
echo "  - 자동 갱신: certbot renew"
echo ""
echo_info "테스트:"
echo "  curl -I https://$DOMAIN"
echo ""
