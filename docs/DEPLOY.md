# DEPLOY.md - Docker 배포 가이드

> BBooster 서버를 Docker로 배포하는 방법을 설명합니다.
> Last updated: 2026-02-04

---

## 1. 사전 요구사항

### 1-1. 필수 소프트웨어
- Docker 20.10+ (Docker Desktop 권장)
- Docker Compose v2+
- Git (소스 클론용)

### 1-2. 시스템 요구사항
- CPU: 2코어 이상
- RAM: 4GB 이상 (PostgreSQL + App)
- 디스크: 10GB 이상 (Docker 이미지 + DB 데이터)
- 네트워크: 인터넷 연결 (TradingView webhook 수신용)

---

## 2. 빠른 시작

### 2-1. 소스 클론
```bash
git clone <repository-url> bbooster
cd bbooster
```

### 2-2. 환경변수 설정
```bash
# .env.example을 복사하여 .env 생성
cp .env.example .env

# .env 파일 편집
notepad .env  # Windows
nano .env     # Linux/Mac
```

필수 설정:
```env
# Database
DB_USER=bbooster
DB_PASSWORD=<강력한_비밀번호_입력>
DB_NAME=bbooster

# App
TV_SECRET=<TradingView_웹훅_시크릿>
```

### 2-3. Docker 실행
```bash
# 빌드 및 시작
docker-compose up -d

# 상태 확인
docker ps

# 로그 확인
docker logs bbooster-app -f
```

### 2-4. DB 초기화 (최초 1회)
```bash
# 스키마 초기화
docker cp scripts/init_schema.sql bbooster-db:/tmp/
docker exec bbooster-db psql -U bbooster -d bbooster -f /tmp/init_schema.sql
```

### 2-5. 동작 확인
```bash
# Health check
curl http://localhost:8000/api/health
# 응답: {"ok":true,"status":"running"}

# Home API
curl http://localhost:8000/api/home
# 응답: {"ok":true,"items":[],...}
```

---

## 3. ngrok 연동 (외부 웹훅 수신)

TradingView 웹훅을 받으려면 외부에서 접속 가능한 URL이 필요합니다.
ngrok을 사용하면 로컬 서버를 외부에 노출할 수 있습니다.

### 3-1. ngrok 계정 생성
1. https://ngrok.com 에서 무료 계정 생성
2. Dashboard에서 Authtoken 복사

### 3-2. docker-compose로 ngrok 실행 (기본 포함)

ngrok 서비스가 기본 `docker-compose.yml`에 포함되어 있습니다.

`.env` 파일에 ngrok 토큰 추가:
```env
NGROK_AUTHTOKEN=<your_ngrok_authtoken>
```

실행:
```bash
docker-compose up -d

# 3개 서비스 확인
docker-compose ps
# bbooster-db, bbooster-app, bbooster-ngrok

# ngrok 대시보드에서 URL 확인
# http://localhost:4040
```

> **참고**: NGROK_AUTHTOKEN이 없으면 ngrok 컨테이너가 시작되지만 터널이 생성되지 않습니다.

### 3-3. 방법 B: 별도로 ngrok 실행 (선택)

```bash
# ngrok 설치 (Windows)
choco install ngrok

# 또는 직접 다운로드
# https://ngrok.com/download

# Authtoken 설정
ngrok config add-authtoken <your_token>

# 터널 시작
ngrok http 8000
```

출력 예시:
```
Forwarding  https://abc123.ngrok.io -> http://localhost:8000
```

### 3-4. TradingView 웹훅 설정

1. TradingView에서 Alert 생성
2. Webhook URL 입력:
   ```
   https://abc123.ngrok.io/tv
   ```
3. Message에 JSON 템플릿 입력:
   ```json
   {
     "secret": "your_strategy_secret",
     "exchange": "OKX",
     "symbol": "{{ticker}}",
     "side": "buy",
     "qty": "0.001"
   }
   ```

### 3-5. 웹훅 테스트

```bash
# 로컬 테스트
curl -X POST http://localhost:8000/tv \
  -H "Content-Type: application/json" \
  -d '{"secret":"your_secret","exchange":"OKX","symbol":"ETH-USDT","side":"buy","qty":"0.001"}'

# ngrok URL로 테스트
curl -X POST https://abc123.ngrok.io/tv \
  -H "Content-Type: application/json" \
  -d '{"secret":"your_secret","exchange":"OKX","symbol":"ETH-USDT","side":"buy","qty":"0.001"}'
```

---

## 4. 보안 주의사항

### 4-1. 필수 보안 설정

1. **강력한 비밀번호 사용**
   - DB_PASSWORD: 최소 16자, 특수문자 포함
   - TV_SECRET: 최소 32자 랜덤 문자열 권장

2. **API 키 보안**
   - 거래소 API 키는 **출금 권한 없이** 생성
   - IP 화이트리스트 설정 (가능한 경우)
   - API 키를 .env 파일에만 저장 (커밋 금지)

3. **.env 파일 보호**
   - .gitignore에 .env 포함 확인
   - 파일 권한: `chmod 600 .env` (Linux)

### 4-2. ngrok 보안

1. **무료 플랜 제한**
   - URL이 재시작마다 변경됨
   - 운영용으로는 유료 플랜(고정 도메인) 권장

2. **Basic Auth 추가** (선택)
   ```bash
   ngrok http 8000 --basic-auth="user:password"
   ```

3. **IP 제한** (ngrok 유료 플랜)
   - TradingView IP만 허용 가능

### 4-3. 네트워크 보안

1. **방화벽 설정**
   - 8000 포트는 localhost 또는 ngrok을 통해서만 접근
   - 직접 외부 노출 금지

2. **HTTPS 사용**
   - ngrok은 자동으로 HTTPS 제공
   - 직접 배포 시 Let's Encrypt 등 SSL 인증서 필수

### 4-4. E-STOP 활용

- 이상 징후 발견 시 즉시 E-STOP 활성화
- 앱/PC/웹 3곳에서 E-STOP 제어 가능
- E-STOP ON 상태에서는 모든 주문 차단

```bash
# E-STOP 활성화
curl -X POST http://localhost:8000/api/system/estop \
  -H "Content-Type: application/json" \
  -d '{"estop":true}'
```

---

## 5. 운영 명령어

### 5-1. 컨테이너 관리

```bash
# 시작
docker-compose up -d

# 중지
docker-compose down

# 재시작
docker-compose restart

# 로그 확인
docker logs bbooster-app -f
docker logs bbooster-db -f

# 상태 확인
docker ps
docker-compose ps
```

### 5-2. 데이터베이스 관리

```bash
# DB 접속
docker exec -it bbooster-db psql -U bbooster -d bbooster

# DB 백업
docker exec bbooster-db pg_dump -U bbooster bbooster > backup.sql

# DB 복원
docker exec -i bbooster-db psql -U bbooster -d bbooster < backup.sql
```

### 5-3. 업데이트

```bash
# 소스 업데이트
git pull

# 이미지 재빌드 및 재시작
docker-compose up -d --build

# 이전 이미지 정리
docker image prune -f
```

---

## 6. 문제 해결

### 6-1. 컨테이너 시작 실패

```bash
# 로그 확인
docker logs bbooster-app

# 일반적인 원인:
# - .env 파일 누락
# - DATABASE_URL 형식 오류
# - 포트 충돌 (8000 또는 5432)
```

### 6-2. DB 연결 실패

```bash
# DB 컨테이너 상태 확인
docker logs bbooster-db

# DB 직접 접속 테스트
docker exec -it bbooster-db psql -U bbooster -d bbooster -c "SELECT 1"
```

### 6-3. ngrok 연결 안됨

```bash
# ngrok 대시보드 확인
# http://localhost:4040

# ngrok 상태 확인
docker logs bbooster-ngrok

# Authtoken 확인
echo $NGROK_AUTHTOKEN
```

### 6-4. TradingView 웹훅 실패

1. ngrok URL이 유효한지 확인
2. `/tv` 엔드포인트로 요청하는지 확인
3. JSON 형식이 올바른지 확인
4. `secret` 필드가 전략의 `tv_secret`과 일치하는지 확인

---

## 7. 프로덕션 배포 체크리스트

- [ ] .env 파일에 강력한 비밀번호 설정
- [ ] API 키에 출금 권한 없음 확인
- [ ] .env 파일이 .gitignore에 포함됨 확인
- [ ] DB 백업 스크립트 설정
- [ ] ngrok 유료 플랜 (고정 도메인) 또는 자체 도메인 설정
- [ ] SSL/HTTPS 활성화
- [ ] E-STOP 테스트 완료
- [ ] 모니터링/알림 설정 (선택)

---

[END OF DEPLOY.md]
