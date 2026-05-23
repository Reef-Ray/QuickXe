"""Generate QuickXe icon: a padlock with a heart-shaped keyhole.

Renders at 512x512 with anti-aliasing (drawn at 4x then downsampled),
then saves both PNG and a multi-resolution .ico for Windows.
"""

from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path

OUT_DIR = Path(__file__).parent
SIZE = 512
SCALE = 4  
W = SIZE * SCALE

PURPLE_DARK = (75, 30, 130, 255)
PURPLE_MID = (139, 60, 220, 255)
PURPLE_LIGHT = (180, 110, 255, 255)
ORANGE = (255, 138, 61, 255)
ORANGE_BRIGHT = (255, 175, 100, 255)
ORANGE_DEEP = (220, 100, 30, 255)
SHADOW = (20, 8, 40, 180)


def make_gradient(size, color1, color2, vertical=True):
    """Linear gradient image."""
    img = Image.new("RGBA", size, color1)
    draw = ImageDraw.Draw(img)
    if vertical:
        for y in range(size[1]):
            t = y / max(1, size[1] - 1)
            r = int(color1[0] * (1 - t) + color2[0] * t)
            g = int(color1[1] * (1 - t) + color2[1] * t)
            b = int(color1[2] * (1 - t) + color2[2] * t)
            a = int(color1[3] * (1 - t) + color2[3] * t)
            draw.line([(0, y), (size[0], y)], fill=(r, g, b, a))
    else:
        for x in range(size[0]):
            t = x / max(1, size[0] - 1)
            r = int(color1[0] * (1 - t) + color2[0] * t)
            g = int(color1[1] * (1 - t) + color2[1] * t)
            b = int(color1[2] * (1 - t) + color2[2] * t)
            a = int(color1[3] * (1 - t) + color2[3] * t)
            draw.line([(x, 0), (x, size[1])], fill=(r, g, b, a))
    return img


def heart_polygon(cx, cy, size):
    """Return a list of (x,y) points forming a heart shape centered at (cx,cy).

    `size` is roughly the half-width of the heart.
    """
    import math
    pts = []

    steps = 200
    for i in range(steps):
        t = 2 * math.pi * i / steps
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t)
              - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * size / 16, cy + y * size / 16))
    return pts


def render_icon():

    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))


    shackle_layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shackle_layer)

    sh_left = W * 0.28
    sh_right = W * 0.72
    sh_top = W * 0.08
    sh_bottom = W * 0.50
    sh_thickness = int(W * 0.085)
    sd.arc([sh_left, sh_top, sh_right, sh_bottom],
           start=180, end=360, fill=PURPLE_LIGHT, width=sh_thickness)

    leg_w = sh_thickness
    body_top = int(W * 0.42)
    sd.rectangle([sh_left, (sh_top + sh_bottom) / 2,
                  sh_left + leg_w, body_top], fill=PURPLE_LIGHT)
    sd.rectangle([sh_right - leg_w, (sh_top + sh_bottom) / 2,
                  sh_right, body_top], fill=PURPLE_LIGHT)


    sd.arc([sh_left + leg_w * 0.25, sh_top + leg_w * 0.25,
            sh_right - leg_w * 0.25, sh_bottom - leg_w * 0.25],
           start=180, end=360, fill=PURPLE_MID, width=int(leg_w * 0.35))


    shadow = shackle_layer.copy()
    shadow_data = shadow.split()

    shadow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    sm = Image.new("L", (W, W), 0)
    sm.paste(shadow_data[3])
    shadow.putalpha(sm)

    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=int(W * 0.012)))

    sh_tint = Image.new("RGBA", (W, W), SHADOW)
    sh_tint.putalpha(shadow.split()[3])
    img = Image.alpha_composite(img, sh_tint)
    img = Image.alpha_composite(img, shackle_layer)

    body_layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body_layer)
    bx1 = int(W * 0.14)
    by1 = int(W * 0.40)
    bx2 = int(W * 0.86)
    by2 = int(W * 0.92)
    radius = int(W * 0.10)
    bd.rounded_rectangle([bx1, by1, bx2, by2], radius=radius,
                         fill=PURPLE_DARK)


    grad = make_gradient((bx2 - bx1, by2 - by1), PURPLE_MID, PURPLE_DARK, vertical=True)
 
    mask = Image.new("L", (bx2 - bx1, by2 - by1), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, bx2 - bx1, by2 - by1], radius=radius, fill=255)
    grad.putalpha(mask)
    body_layer.alpha_composite(grad, (bx1, by1))


    bsh = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    bsh_d = ImageDraw.Draw(bsh)
    bsh_d.rounded_rectangle([bx1, by1 + int(W * 0.01), bx2, by2 + int(W * 0.015)],
                            radius=radius, fill=SHADOW)
    bsh = bsh.filter(ImageFilter.GaussianBlur(radius=int(W * 0.015)))
    img = Image.alpha_composite(img, bsh)
    img = Image.alpha_composite(img, body_layer)


    hl = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.rounded_rectangle(
        [bx1 + int(W * 0.04), by1 + int(W * 0.035),
         bx2 - int(W * 0.04), by1 + int(W * 0.10)],
        radius=int(W * 0.04),
        fill=(255, 255, 255, 35),
    )
    hl = hl.filter(ImageFilter.GaussianBlur(radius=int(W * 0.006)))
    img = Image.alpha_composite(img, hl)

    heart_layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    hd = ImageDraw.Draw(heart_layer)
    cx = W / 2
    cy = W * 0.62
    heart_size = W * 0.16

    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.polygon(heart_polygon(cx, cy, heart_size * 1.25), fill=(255, 138, 61, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=int(W * 0.025)))
    img = Image.alpha_composite(img, glow)

    hd.polygon(heart_polygon(cx, cy, heart_size), fill=ORANGE)

    inner = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    id_ = ImageDraw.Draw(inner)
    id_.polygon(heart_polygon(cx - heart_size * 0.05, cy - heart_size * 0.1,
                              heart_size * 0.8),
                fill=ORANGE_BRIGHT)
    inner = inner.filter(ImageFilter.GaussianBlur(radius=int(W * 0.008)))
    heart_layer = Image.alpha_composite(heart_layer, inner)

    edge = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge)
    ed.polygon(heart_polygon(cx + heart_size * 0.08, cy + heart_size * 0.1,
                             heart_size * 0.7),
               fill=(0, 0, 0, 60))
    edge = edge.filter(ImageFilter.GaussianBlur(radius=int(W * 0.01)))
    heart_mask = Image.new("L", (W, W), 0)
    hm = ImageDraw.Draw(heart_mask)
    hm.polygon(heart_polygon(cx, cy, heart_size), fill=255)
    edge_alpha = edge.split()[3]
    final_edge_alpha = Image.new("L", (W, W), 0)
    final_edge_alpha.paste(edge_alpha, mask=heart_mask)
    edge.putalpha(final_edge_alpha)

    img = Image.alpha_composite(img, heart_layer)
    img = Image.alpha_composite(img, edge)


    spec = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    sd = ImageDraw.Draw(spec)
    sd.ellipse([cx - heart_size * 0.55, cy - heart_size * 0.7,
                cx - heart_size * 0.15, cy - heart_size * 0.3],
               fill=(255, 240, 220, 180))
    spec = spec.filter(ImageFilter.GaussianBlur(radius=int(W * 0.005)))
    spec_alpha = spec.split()[3]
    final_spec_alpha = Image.new("L", (W, W), 0)
    final_spec_alpha.paste(spec_alpha, mask=heart_mask)
    spec.putalpha(final_spec_alpha)
    img = Image.alpha_composite(img, spec)

    final = img.resize((SIZE, SIZE), Image.LANCZOS)
    return final


def main():
    icon = render_icon()
    png_path = OUT_DIR / "quickxe.png"
    icon.save(png_path)
    print(f"Saved {png_path}")

    ico_path = OUT_DIR / "quickxe.ico"
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    icon.save(ico_path, format="ICO", sizes=sizes)
    print(f"Saved {ico_path}")


if __name__ == "__main__":
    main()
