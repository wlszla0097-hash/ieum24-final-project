"""시연용 가상 법인 인장 이미지 만들기 — python3 tools/make_seals.py

data/synthetic/companies.json 의 회사마다 data/synthetic/seals/<사업자번호>.png 를 만든다.
실제 인감과 구분되도록 바깥 글자에 '시연용 가상 인장'을 넣는다. (Pillow·한글 글꼴 필요, 결과 PNG는 저장소에 올려 둔다)
"""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "synthetic", "seals")
FONT = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"  # Noto Serif CJK KR (index 1)
RED = (200, 30, 30, 235)
S = 480  # 크게 그린 뒤 240으로 줄여 가장자리를 부드럽게


def font(size):
    return ImageFont.truetype(FONT, size, index=1)


def seal(name: str) -> Image.Image:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(im)
    c, r = S / 2, S / 2 - 12
    g.ellipse((c - r, c - r, c + r, c + r), outline=RED, width=16)
    g.ellipse((c - r * 0.62, c - r * 0.62, c + r * 0.62, c + r * 0.62), outline=RED, width=7)
    ring = f"주식회사 {name} · 시연용 가상 인장 · "
    f = font(46)
    step = 360 / len(ring)
    for i, ch in enumerate(ring):  # 바깥 고리 글자: 원을 따라 한 글자씩 돌려 붙인다
        ang = math.radians(-90 + i * step)
        glyph = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((32, 32), ch, font=f, fill=RED, anchor="mm")
        glyph = glyph.rotate(-(i * step), resample=Image.BICUBIC)
        x, y = c + r * 0.81 * math.cos(ang), c + r * 0.81 * math.sin(ang)
        im.alpha_composite(glyph, (int(x - 32), int(y - 32)))
    f2 = font(70)
    for txt, dy in (("대표", -42), ("이사", 42)):
        g.text((c, c + dy), txt, font=f2, fill=RED, anchor="mm")
    return im.resize((240, 240), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(ROOT, "data", "synthetic", "companies.json"), encoding="utf-8") as fp:
        companies = json.load(fp)
    for co in companies:
        name = co["company"].replace("(가상)", "").strip()
        b = "".join(ch for ch in co["busino"] if ch.isdigit())
        seal(name).save(os.path.join(OUT, f"{b}.png"), optimize=True)
        print("  ", b, name)
    print(f"{len(companies)}개 → data/synthetic/seals/")


if __name__ == "__main__":
    main()
