"""
BBooster Icon Generator
엠블럼에서 아이콘 세트 생성
"""
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow not installed. Run: pip install Pillow")
    exit(1)

# 경로 설정
BASE_DIR = Path(__file__).parent.parent
EMBLEM_PATH = BASE_DIR / "bbooster_emblem.png"
BRAND_ICONS_DIR = BASE_DIR / "brand" / "icons"
TAURI_ICONS_DIR = BASE_DIR / "pc-app" / "src-tauri" / "icons"
SITE_ASSETS_DIR = BASE_DIR / "site" / "assets"

# 디렉토리 생성
BRAND_ICONS_DIR.mkdir(parents=True, exist_ok=True)
TAURI_ICONS_DIR.mkdir(parents=True, exist_ok=True)

def load_emblem():
    """엠블럼 로드"""
    if not EMBLEM_PATH.exists():
        print(f"Emblem not found: {EMBLEM_PATH}")
        return None
    return Image.open(EMBLEM_PATH)

def create_square_icon(img, size):
    """정사각형 아이콘 생성"""
    # 이미지를 정사각형으로 리사이즈
    img_resized = img.copy()
    img_resized.thumbnail((size, size), Image.Resampling.LANCZOS)

    # 정사각형 캔버스에 중앙 배치
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    offset = ((size - img_resized.width) // 2, (size - img_resized.height) // 2)
    canvas.paste(img_resized, offset, img_resized if img_resized.mode == 'RGBA' else None)

    return canvas

def generate_icons():
    """아이콘 세트 생성"""
    emblem = load_emblem()
    if emblem is None:
        return

    print(f"Loaded emblem: {emblem.size}, mode: {emblem.mode}")

    # RGBA로 변환
    if emblem.mode != 'RGBA':
        emblem = emblem.convert('RGBA')

    # === Brand Icons ===
    print("\n=== Brand Icons ===")

    # 512x512 dark (원본 유지)
    icon_512 = create_square_icon(emblem, 512)
    icon_512.save(BRAND_ICONS_DIR / "icon-dark.png")
    print(f"Created: icon-dark.png (512x512)")

    # 512x512 light (배경 흰색)
    icon_light = Image.new('RGBA', (512, 512), (255, 255, 255, 255))
    icon_512_temp = create_square_icon(emblem, 480)
    icon_light.paste(icon_512_temp, (16, 16), icon_512_temp)
    icon_light.save(BRAND_ICONS_DIR / "icon-light.png")
    print(f"Created: icon-light.png (512x512)")

    # 512x512 mono (흑백)
    icon_mono = icon_512.convert('L').convert('RGBA')
    icon_mono.save(BRAND_ICONS_DIR / "icon-mono.png")
    print(f"Created: icon-mono.png (512x512)")

    # === Tauri Icons ===
    print("\n=== Tauri Icons ===")

    # 다양한 크기
    sizes = [32, 128, 256]
    for size in sizes:
        icon = create_square_icon(emblem, size)
        icon.save(TAURI_ICONS_DIR / f"{size}x{size}.png")
        print(f"Created: {size}x{size}.png")

    # 128x128@2x (256px)
    icon_2x = create_square_icon(emblem, 256)
    icon_2x.save(TAURI_ICONS_DIR / "128x128@2x.png")
    print(f"Created: 128x128@2x.png")

    # icon.png (기본)
    icon_default = create_square_icon(emblem, 256)
    icon_default.save(TAURI_ICONS_DIR / "icon.png")
    print(f"Created: icon.png (256x256)")

    # icon.ico (Windows)
    try:
        icon_ico = create_square_icon(emblem, 256)
        icon_ico.save(
            TAURI_ICONS_DIR / "icon.ico",
            format='ICO',
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        )
        print(f"Created: icon.ico (multi-size)")
    except Exception as e:
        print(f"Warning: Could not create icon.ico: {e}")
        # 단일 크기로 재시도
        icon_ico = create_square_icon(emblem, 256)
        icon_ico.save(TAURI_ICONS_DIR / "icon.ico", format='ICO')
        print(f"Created: icon.ico (256x256 only)")

    # === Site Assets ===
    print("\n=== Site Assets ===")

    # favicon.ico
    try:
        favicon = create_square_icon(emblem, 64)
        favicon.save(
            SITE_ASSETS_DIR / "favicon.ico",
            format='ICO',
            sizes=[(16, 16), (32, 32), (48, 48)]
        )
        print(f"Created: favicon.ico")
    except Exception as e:
        print(f"Warning: Could not create favicon.ico: {e}")
        favicon = create_square_icon(emblem, 32)
        favicon.save(SITE_ASSETS_DIR / "favicon.ico", format='ICO')
        print(f"Created: favicon.ico (32x32 only)")

    # logo.png (사이트용)
    logo = create_square_icon(emblem, 128)
    logo.save(SITE_ASSETS_DIR / "logo.png")
    print(f"Created: logo.png (128x128)")

    print("\n=== Done ===")
    print(f"Brand icons: {BRAND_ICONS_DIR}")
    print(f"Tauri icons: {TAURI_ICONS_DIR}")
    print(f"Site assets: {SITE_ASSETS_DIR}")

if __name__ == "__main__":
    generate_icons()
