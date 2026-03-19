#!/usr/bin/env python3
"""Generate basic .cube LUT files for cinematic color grading.

Run once to create the preset files. These are 17x17x17 3D LUTs.
"""
import struct
from pathlib import Path


def write_cube(path: str, title: str, transform_fn) -> None:
    """Write a .cube LUT file with a transform function."""
    size = 17
    with open(path, "w") as f:
        f.write(f"TITLE \"{title}\"\n")
        f.write(f"LUT_3D_SIZE {size}\n")
        f.write(f"DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write(f"DOMAIN_MAX 1.0 1.0 1.0\n\n")
        for b_i in range(size):
            for g_i in range(size):
                for r_i in range(size):
                    r = r_i / (size - 1)
                    g = g_i / (size - 1)
                    b = b_i / (size - 1)
                    nr, ng, nb = transform_fn(r, g, b)
                    nr = max(0.0, min(1.0, nr))
                    ng = max(0.0, min(1.0, ng))
                    nb = max(0.0, min(1.0, nb))
                    f.write(f"{nr:.6f} {ng:.6f} {nb:.6f}\n")
    print(f"  Generated: {path}")


def clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def teal_orange(r: float, g: float, b: float):
    """Blockbuster teal/orange split toning."""
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    # Shadows → teal, highlights → orange
    shadow_mix = max(0, 1.0 - luma * 2)
    highlight_mix = max(0, luma * 2 - 1.0)
    nr = r + highlight_mix * 0.08 - shadow_mix * 0.03
    ng = g - highlight_mix * 0.02 + shadow_mix * 0.02
    nb = b - highlight_mix * 0.06 + shadow_mix * 0.08
    # Slight contrast boost
    nr = clamp((nr - 0.5) * 1.1 + 0.5)
    ng = clamp((ng - 0.5) * 1.05 + 0.5)
    nb = clamp((nb - 0.5) * 1.1 + 0.5)
    return nr, ng, nb


def warm_vintage(r: float, g: float, b: float):
    """Warm vintage film — lifted blacks, warm tones."""
    nr = clamp(r * 0.95 + 0.05)  # Lifted blacks
    ng = clamp(g * 0.92 + 0.04)
    nb = clamp(b * 0.85 + 0.03)  # Less blue = warmer
    # Slight fade (reduce contrast)
    nr = clamp(nr * 0.9 + 0.08)
    ng = clamp(ng * 0.9 + 0.06)
    nb = clamp(nb * 0.9 + 0.04)
    return nr, ng, nb


def cold_blue(r: float, g: float, b: float):
    """Cold desaturated blue — sci-fi, horror."""
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    # Desaturate partially
    nr = r * 0.7 + luma * 0.3
    ng = g * 0.7 + luma * 0.3
    nb = b * 0.7 + luma * 0.3
    # Push blue
    nb = clamp(nb + 0.06)
    nr = clamp(nr - 0.03)
    # Crush blacks slightly
    nr = clamp(nr * 1.05 - 0.02)
    ng = clamp(ng * 1.05 - 0.02)
    nb = clamp(nb * 1.05)
    return nr, ng, nb


def bleach_bypass(r: float, g: float, b: float):
    """Bleach bypass — high contrast, desaturated."""
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    # Strong desaturation
    nr = r * 0.4 + luma * 0.6
    ng = g * 0.4 + luma * 0.6
    nb = b * 0.4 + luma * 0.6
    # Strong contrast
    nr = clamp((nr - 0.5) * 1.4 + 0.5)
    ng = clamp((ng - 0.5) * 1.4 + 0.5)
    nb = clamp((nb - 0.5) * 1.4 + 0.5)
    return nr, ng, nb


def golden_hour(r: float, g: float, b: float):
    """Golden hour — warm sunset tones."""
    nr = clamp(r * 1.05 + 0.04)
    ng = clamp(g * 0.98 + 0.02)
    nb = clamp(b * 0.82 - 0.02)
    # Soft glow in highlights
    luma = 0.299 * nr + 0.587 * ng + 0.114 * nb
    if luma > 0.6:
        glow = (luma - 0.6) * 0.15
        nr = clamp(nr + glow)
        ng = clamp(ng + glow * 0.7)
    return nr, ng, nb


def main():
    out = Path(__file__).parent
    print("Generating .cube LUT presets:")
    write_cube(str(out / "teal-orange.cube"), "Teal Orange Blockbuster", teal_orange)
    write_cube(str(out / "warm-vintage.cube"), "Warm Vintage Film", warm_vintage)
    write_cube(str(out / "cold-blue.cube"), "Cold Blue Sci-Fi", cold_blue)
    write_cube(str(out / "bleach-bypass.cube"), "Bleach Bypass Drama", bleach_bypass)
    write_cube(str(out / "golden-hour.cube"), "Golden Hour Sunset", golden_hour)
    print("Done!")


if __name__ == "__main__":
    main()
