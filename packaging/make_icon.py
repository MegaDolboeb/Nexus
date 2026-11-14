"""Генерирует иконку Nexus (синяя бесконечность, мягкий градиент) — .ico для сборки и PNG
для окна/трея. Запускать вручную при желании поменять иконку: python packaging/make_icon.py"""
import math
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
C1 = (130, 180, 255)      # светлый край градиента
C2 = (35, 95, 225)        # глубокий синий


def make_infinity(size: int, supersample: int = 4) -> Image.Image:
    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = s / 2
    a = s * 0.33
    n = max(300, size * 2)
    w = s * 0.145
    r = w / 2
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        denom = 1 + math.sin(t) ** 2
        x = a * math.cos(t) / denom
        y = a * math.sin(t) * math.cos(t) / denom
        frac = (math.sin(2 * math.pi * i / n) + 1) / 2
        col = tuple(int(C1[k] + (C2[k] - C1[k]) * frac) for k in range(3)) + (255,)
        d.ellipse([cx + x - r, cy + y - r, cx + x + r, cy + y + r], fill=col)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    make_infinity(256).save(ROOT / "packaging" / "nexus.ico",
                            sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    make_infinity(128).save(ROOT / "nexus" / "panel" / "icon.png")
    print("готово: packaging/nexus.ico, nexus/panel/icon.png")
