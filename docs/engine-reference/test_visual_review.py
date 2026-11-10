"""Run: python test_visual_review.py   (also pytest-compatible)"""
import os
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from visual_review import BrandKit, review_image, delta_e76, contrast_ratio, rel_luminance

PAPER, FOREST, SANDAL = "#F6F1E7", "#1E3B2C", "#C9A227"
try:  # Pillow >= 10.1 supports a size argument; older versions get a tiny bitmap font
    FONT = ImageFont.load_default(size=28)
except TypeError:
    FONT = ImageFont.load_default()


def make_logo(w=160, h=50) -> Image.Image:
    im = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    d.ellipse((4, 5, 44, 45), fill=FOREST)
    d.rectangle((54, 12, 150, 22), fill=FOREST)
    d.rectangle((54, 30, 120, 40), fill=FOREST)
    d.polygon([(20, 15), (30, 35), (10, 35)], fill=PAPER)
    return im


def canvas(size=(800, 600), color=PAPER):
    im = Image.new("RGB", size, color)
    return im, ImageDraw.Draw(im)


def kit_with_logo(tmp):
    p = os.path.join(tmp, "logo.png")
    make_logo().save(p)
    return BrandKit(logo_template_path=p)


def test_color_math():
    assert abs(delta_e76((0, 0, 0), (255, 255, 255)) - 100) < 0.5            # L* 0 -> 100
    assert abs(float(contrast_ratio(rel_luminance(np.array([0, 0, 0])),
                                    rel_luminance(np.array([255, 255, 255])))) - 21) < 0.01


def test_contrast_fail_and_pass():
    kit = BrandKit()
    bad, d = canvas(color="#6E7F70")          # Appendix B.3 low-contrast pair
    d.text((40, 250), "Visible results", font=FONT, fill="#3A5244")
    r = review_image(bad, kit, alt_text="x", text_boxes=[(20, 230, 400, 300)])
    f = [x for x in r["findings"] if x["title"].startswith("Text contrast")]
    assert f and f[0]["evidence"]["ratio"] < 3.0, r

    good, d = canvas(color=PAPER)
    d.text((40, 250), "Visible results", font=FONT, fill="#2F3A33")
    r = review_image(good, kit, alt_text="x", text_boxes=[(20, 230, 400, 300)])
    assert not [x for x in r["findings"] if x["title"].startswith("Text contrast")], r


def test_whole_image_contrast_is_low_confidence_question():
    bad, d = canvas(color="#6E7F70")
    d.text((40, 250), "Visible results", font=FONT, fill="#3A5244")
    r = review_image(bad, BrandKit(), alt_text="x")      # no vision, no boxes
    f = [x for x in r["findings"] if x["title"].startswith("Text contrast")][0]
    assert f["verdict_type"] == "question" and f["route"] == "human_review"


def test_off_palette_flagged_brand_green_not():
    kit = BrandKit()
    im, d = canvas()
    d.rectangle((0, 0, 400, 600), fill="#2E9E3F")        # bright off-brand green, ~50% coverage
    d.rectangle((400, 0, 800, 600), fill=FOREST)
    r = review_image(im, kit, alt_text="x")
    off = [x for x in r["findings"] if x["rule_id"] == "P-011"]
    assert len(off) == 1 and off[0]["evidence"]["colour"].startswith("#2")
    assert off[0]["evidence"]["delta_e"] > 12


def test_clear_space_violation_measured():
    with tempfile.TemporaryDirectory() as tmp:
        kit = kit_with_logo(tmp)
        im, d = canvas()
        im.paste(make_logo(), (300, 300))                  # logo box (300,300)-(460,350)
        d.rectangle((300, 370, 460, 400), fill=SANDAL)     # banner 20px below; need 25px
        r = review_image(im, kit, alt_text="x")
        cs = [x for x in r["findings"] if x["title"] == "Logo clear-space violated"]
        assert cs, r
        ev = cs[0]["evidence"]
        assert abs(ev["free_px"]["bottom"] - 20) <= 2 and 10 <= ev["violation_pct"] <= 30, ev


def test_clear_space_ok():
    with tempfile.TemporaryDirectory() as tmp:
        kit = kit_with_logo(tmp)
        im, d = canvas()
        im.paste(make_logo(), (300, 300))
        d.rectangle((300, 400, 460, 430), fill=SANDAL)     # 50px away
        r = review_image(im, kit, alt_text="x")
        assert not [x for x in r["findings"] if x["title"] == "Logo clear-space violated"], r


def test_logo_found_when_scaled_and_small_logo_flagged():
    with tempfile.TemporaryDirectory() as tmp:
        kit = kit_with_logo(tmp)
        im, _ = canvas()
        im.paste(make_logo().resize((80, 25)), (100, 100))   # 80px wide < 96px minimum
        r = review_image(im, kit, alt_text="x")
        assert any(x["title"] == "Logo below minimum size" for x in r["findings"]), r


def test_stretched_logo_flagged():
    with tempfile.TemporaryDirectory() as tmp:
        kit = kit_with_logo(tmp)
        im, _ = canvas()
        im.paste(make_logo().resize((160, 70)), (200, 200))  # 1.4x taller than approved
        r = review_image(im, kit, alt_text="x")
        assert any(x["title"] == "Logo appears stretched" for x in r["findings"]), r


def test_logo_missing_becomes_question():
    with tempfile.TemporaryDirectory() as tmp:
        kit = kit_with_logo(tmp)
        im, _ = canvas()
        r = review_image(im, kit, alt_text="x")
        f = [x for x in r["findings"] if x["title"] == "Logo not located"]
        assert f and f[0]["verdict_type"] == "question" and f[0]["route"] == "human_review"


def test_missing_alt_text():
    im, _ = canvas()
    r = review_image(im, BrandKit())
    assert any(x["title"] == "Missing alt text" for x in r["findings"])


def test_every_finding_has_a_rule_id():
    im, d = canvas(color="#6E7F70")
    d.text((40, 250), "x", font=FONT, fill="#3A5244")
    for f in review_image(im, BrandKit())["findings"]:
        assert f["rule_id"]


if __name__ == "__main__":
    import time
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            t = time.time()
            fn()
            print(f"ok  {name}  ({time.time() - t:.2f}s)")
