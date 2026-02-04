# BRAND_SPEC.md
- Last updated: 2026-02-04 KST
- Status: Week A

---

# 1) 브랜드 정보

| 항목 | 값 |
|------|-----|
| 제품명 | BBooster |
| 서브타이틀 | ATAU |
| 슬로건 | ASSET UPWARD WITH AUTO TRADING |
| 원본 엠블럼 | bbooster_emblem.png |

---

# 2) 컬러 팔레트

| 용도 | 색상 | HEX |
|------|------|-----|
| Primary (로켓) | 빨간색 | #E53935 |
| Primary Dark | 다크 레드 | #B71C1C |
| Accent (불꽃) | 오렌지 | #FF9800 |
| Background Dark | 다크 브라운 | #2D1F1F |
| Background Light | 화이트 | #FFFFFF |
| Text Light | 라이트 핑크 | #FFCDD2 |
| Border | 레드 링 | #E53935 |

---

# 3) 아이콘 세트 (B안: 텍스트 제거/미니멀)

## 3-1) 필요 파일

| 파일명 | 용도 | 크기 | 배경 |
|--------|------|------|------|
| icon-dark.png | 다크 테마용 | 512x512 | 투명 |
| icon-light.png | 라이트 테마용 | 512x512 | 투명 |
| icon-mono.png | 단색 버전 | 512x512 | 투명 |
| favicon.ico | 웹사이트 | 16,32,48 | 투명 |
| icon.ico | Windows 앱 | 256x256 | 투명 |
| ic_launcher.png | Android | 192x192 | 적응형 |
| ic_launcher_round.png | Android 원형 | 192x192 | 원형 |
| ic_launcher_foreground.png | Android 전경 | 432x432 | 투명 |

## 3-2) 아이콘 디자인 가이드 (B안)

```
[B안: 텍스트 제거 버전]

- 로켓만 중앙 배치 (텍스트 없음)
- 상승 차트 라인 유지 (선택)
- 원형 배경 유지 또는 투명

변형:
- Dark: 다크 배경(#2D1F1F) + 빨간 로켓
- Light: 투명/흰 배경 + 빨간 로켓
- Mono: 단색(흰색 또는 검정) 로켓
```

## 3-3) 생성 방법

```bash
# ImageMagick 또는 Python Pillow 사용
# 원본에서 로켓 영역만 크롭 후 리사이즈

# favicon.ico 생성 (다중 크기)
magick icon-dark.png -define icon:auto-resize=256,128,64,48,32,16 favicon.ico

# Windows .ico 생성
magick icon-dark.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico

# Android adaptive icon
# ic_launcher_foreground.png: 432x432, 로켓만 (패딩 68px 권장)
```

---

# 4) 로고 사용 가이드

## 4-1) 최소 여백
- 로고 높이의 25% 이상 여백 확보

## 4-2) 금지 사항
- 비율 변경 금지
- 색상 임의 변경 금지
- 그림자/효과 추가 금지
- 저해상도 사용 금지

---

# 5) 파일 위치

```
brand/
├── BRAND_SPEC.md          # 이 문서
├── icons/
│   ├── icon-dark.png      # 다크 테마 (512x512)
│   ├── icon-light.png     # 라이트 테마 (512x512)
│   ├── icon-mono.png      # 단색 (512x512)
│   ├── favicon.ico        # 웹사이트
│   ├── icon.ico           # Windows
│   └── android/
│       ├── ic_launcher.png
│       ├── ic_launcher_round.png
│       └── ic_launcher_foreground.png
└── original/
    └── bbooster_emblem.png  # 원본 (복사)
```

---

# 6) TODO (Week A)

- [ ] 원본 엠블럼에서 로켓만 추출
- [ ] icon-dark.png 생성 (512x512)
- [ ] icon-light.png 생성 (512x512)
- [ ] icon-mono.png 생성 (512x512)
- [ ] favicon.ico 생성
- [ ] icon.ico 생성 (Windows)
- [ ] Android adaptive icon 세트 생성

---

[END OF BRAND_SPEC]
