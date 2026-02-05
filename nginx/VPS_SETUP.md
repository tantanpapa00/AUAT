# VPS_SETUP.md - Nginx + SSL 설치 가이드

> BBooster를 VPS에 배포하기 위한 Nginx + SSL 설정 가이드
> PART 5: Nginx + SSL (3단계)

---

## 사전 요구사항

- Ubuntu 20.04+ 또는 Debian 11+ VPS
- 도메인 (예: bbooster.yourdomain.com)
- 도메인 DNS가 VPS IP를 가리키도록 설정 완료
- Docker + docker-compose 설치 완료 (PART 1)

---

## 단계 1: Nginx 설치

### 1-1. Nginx 설치

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y nginx

# 상태 확인
sudo systemctl status nginx

# 자동 시작 설정
sudo systemctl enable nginx
```

### 1-2. 방화벽 설정

```bash
# UFW 사용시
sudo ufw allow 'Nginx Full'
sudo ufw allow 22/tcp
sudo ufw enable
sudo ufw status
```

---

## 단계 2: Nginx 설정 파일 복사

### 2-1. 설정 파일 복사

```bash
# 프로젝트 폴더에서 VPS로 복사 (로컬에서 실행)
scp nginx/nginx.conf user@your-vps:/tmp/
scp nginx/bbooster.conf user@your-vps:/tmp/

# VPS에서 실행
sudo cp /tmp/nginx.conf /etc/nginx/nginx.conf
sudo cp /tmp/bbooster.conf /etc/nginx/conf.d/bbooster.conf
```

### 2-2. 도메인 수정

```bash
# 설정 파일에서 your-domain.com을 실제 도메인으로 변경
sudo nano /etc/nginx/conf.d/bbooster.conf

# 또는 sed로 일괄 변경
sudo sed -i 's/your-domain.com/bbooster.yourdomain.com/g' /etc/nginx/conf.d/bbooster.conf
```

### 2-3. 랜딩 페이지 배포

```bash
# 디렉토리 생성
sudo mkdir -p /var/www/bbooster/landing

# 랜딩 페이지 복사 (로컬에서)
scp -r landing/* user@your-vps:/tmp/landing/

# VPS에서
sudo cp -r /tmp/landing/* /var/www/bbooster/landing/
sudo chown -R www-data:www-data /var/www/bbooster
```

### 2-4. 설정 테스트

```bash
# 문법 검사
sudo nginx -t

# 성공 시 출력:
# nginx: configuration file /etc/nginx/nginx.conf syntax is ok
# nginx: configuration file /etc/nginx/nginx.conf test is successful
```

---

## 단계 3: SSL 인증서 설정 (Let's Encrypt)

### 3-1. Certbot 설치

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 3-2. 인증서 발급 (방법 A: 자동)

```bash
# Nginx 플러그인 사용 (가장 쉬움)
sudo certbot --nginx -d bbooster.yourdomain.com -d www.bbooster.yourdomain.com

# 이메일 입력, 약관 동의 후 자동 설정
```

### 3-2. 인증서 발급 (방법 B: 수동/웹루트)

```bash
# 인증용 디렉토리 생성
sudo mkdir -p /var/www/certbot

# 임시 Nginx 설정 (SSL 없이)
# /etc/nginx/conf.d/bbooster.conf 에서 443 블록 주석 처리 후

sudo nginx -t && sudo systemctl reload nginx

# 인증서 발급
sudo certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    -d bbooster.yourdomain.com \
    -d www.bbooster.yourdomain.com \
    --email your-email@example.com \
    --agree-tos

# 성공 시 인증서 위치:
# /etc/letsencrypt/live/bbooster.yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/bbooster.yourdomain.com/privkey.pem
```

### 3-3. Nginx 재시작

```bash
# SSL 설정이 포함된 전체 설정 활성화
sudo nginx -t
sudo systemctl reload nginx
```

### 3-4. 자동 갱신 확인

```bash
# Certbot 타이머 확인
sudo systemctl status certbot.timer

# 갱신 테스트 (실제 갱신 안함)
sudo certbot renew --dry-run
```

---

## 확인 및 테스트

### 사이트 접속 테스트

```bash
# HTTPS 확인
curl -I https://bbooster.yourdomain.com

# 예상 출력:
# HTTP/2 200
# ...
# strict-transport-security: max-age=63072000
```

### API 테스트

```bash
# Health check
curl https://bbooster.yourdomain.com/api/health

# 예상: {"ok":true,"status":"running"}
```

### TradingView 웹훅 테스트

```bash
curl -X POST https://bbooster.yourdomain.com/tv \
  -H "Content-Type: application/json" \
  -d '{"secret":"your_secret","exchange":"OKX","symbol":"ETH-USDT","side":"buy","qty":"0.001"}'
```

---

## 문제 해결

### Nginx 시작 실패

```bash
# 로그 확인
sudo tail -f /var/log/nginx/error.log

# 일반적인 원인:
# - 포트 충돌 (이미 80/443 사용 중)
# - 설정 문법 오류
# - SSL 인증서 파일 없음
```

### SSL 인증서 오류

```bash
# 인증서 상태 확인
sudo certbot certificates

# 수동 갱신
sudo certbot renew

# 인증서 삭제 후 재발급
sudo certbot delete --cert-name bbooster.yourdomain.com
sudo certbot --nginx -d bbooster.yourdomain.com
```

### 502 Bad Gateway

```bash
# FastAPI 앱이 실행 중인지 확인
docker ps | grep bbooster-app

# 앱 로그 확인
docker logs bbooster-app -f

# 포트 확인
curl http://127.0.0.1:8000/api/health
```

---

## 체크리스트

- [ ] Nginx 설치 완료
- [ ] 방화벽 80/443 포트 열림
- [ ] 도메인 DNS → VPS IP 설정 완료
- [ ] nginx.conf, bbooster.conf 복사 완료
- [ ] 도메인 이름 수정 완료 (your-domain.com → 실제 도메인)
- [ ] 랜딩 페이지 /var/www/bbooster/landing 에 배포
- [ ] SSL 인증서 발급 완료
- [ ] HTTPS 접속 테스트 성공
- [ ] API 프록시 테스트 성공
- [ ] certbot 자동 갱신 설정 확인

---

## 파일 구조 (VPS)

```
/etc/nginx/
├── nginx.conf              # 메인 설정
├── conf.d/
│   └── bbooster.conf       # 사이트 설정
└── ...

/var/www/bbooster/
└── landing/
    ├── index.html          # 랜딩 페이지
    ├── terms.html          # 이용약관
    ├── privacy.html        # 개인정보처리방침
    └── risk.html           # 투자위험고지

/etc/letsencrypt/live/your-domain.com/
├── fullchain.pem           # SSL 인증서
└── privkey.pem             # SSL 개인키
```

---

[END OF VPS_SETUP.md]
