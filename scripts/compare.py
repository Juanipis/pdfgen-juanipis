import pathlib

import fitz
from PIL import Image, ImageChops, ImageStat

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORIG = ROOT / "boletin.pdf"
GEN = ROOT / "output.pdf"


def render_page(pdf_path, zoom=2):
    doc = fitz.open(pdf_path)
    page = doc[0]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    mode = "RGB"
    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
    return img


def diff_stats(img_a, img_b, box=None):
    if box:
        img_a = img_a.crop(box)
        img_b = img_b.crop(box)
    diff = ImageChops.difference(img_a, img_b)
    stat = ImageStat.Stat(diff)
    # mean per-channel
    mean = sum(stat.mean) / len(stat.mean)
    rms = sum(stat.rms) / len(stat.rms)
    return mean, rms


def main():
    if not ORIG.exists():
        raise SystemExit(f"Missing {ORIG}")
    if not GEN.exists():
        raise SystemExit(f"Missing {GEN}. Run render.py first.")

    img_orig = render_page(ORIG)
    img_gen = render_page(GEN)

    if img_orig.size != img_gen.size:
        raise SystemExit(f"Size mismatch: {img_orig.size} vs {img_gen.size}")

    w, h = img_orig.size
    pt_to_px = 2  # zoom=2
    header_height_pt = 120
    footer_height_pt = 120

    header_box = (0, 0, w, int(header_height_pt * pt_to_px))
    footer_box = (0, h - int(footer_height_pt * pt_to_px), w, h)

    full_mean, full_rms = diff_stats(img_orig, img_gen)
    head_mean, head_rms = diff_stats(img_orig, img_gen, header_box)
    foot_mean, foot_rms = diff_stats(img_orig, img_gen, footer_box)

    print("Diff (mean, rms) full:", round(full_mean, 2), round(full_rms, 2))
    print("Diff (mean, rms) header:", round(head_mean, 2), round(head_rms, 2))
    print("Diff (mean, rms) footer:", round(foot_mean, 2), round(foot_rms, 2))


if __name__ == "__main__":
    main()
