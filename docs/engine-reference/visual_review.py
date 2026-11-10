"""
BrandPilot - image-creative review path (Karanveer Singh's module).

Deterministic checks (no external calls, numpy + Pillow only):
  * P-011  palette drift: dominant colours vs approved palette, CIE76 delta-E
  * A-003  WCAG contrast of text on the creative (+ alt-text presence)
  * A-007  logo: clear-space, minimum size, wordmark recolour, stretch

Vision-model hook (optional): a VisionProvider supplies text regions and alt
text. If it is absent, checks degrade to heuristics with LOWER confidence and
are routed to a human as questions, never as verdicts.

Invariants from the plan (section 7):
  * "No source, no finding": every Finding carries a rule_id from the kit.
  * Deterministic results are never overridden by model output.
  * CRITICAL or low-confidence findings are routed to a human.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import Optional, Protocol

import numpy as np
from PIL import Image

BBox = tuple[int, int, int, int]  # x0, y0, x1, y1 (native pixels, x1/y1 exclusive)


# ----------------------------------------------------------------------------
# Brand kit (Appendix B, Aranya Botanics). Load your own from JSON in practice.
# ----------------------------------------------------------------------------
@dataclass
class BrandKit:
    palette: dict[str, str] = field(default_factory=lambda: {
        "forest": "#1E3B2C", "sandal": "#C9A227", "paper": "#F6F1E7", "ink": "#2F3A33",
    })
    wordmark_colors: list[str] = field(default_factory=lambda: ["#1E3B2C", "#F6F1E7"])
    text_ink: str = "#2F3A33"
    delta_e_max: float = 12.0          # P-011
    contrast_min: float = 4.5          # A-003 (AA body text)
    contrast_min_large: float = 3.0    # AA large text
    clear_space_ratio: float = 0.5     # A-007: x logo height
    min_logo_px: int = 96              # A-007: min digital width
    allow_neutrals: bool = True        # white/black/grey never count as off-palette
    logo_template_path: Optional[str] = None


# ----------------------------------------------------------------------------
# Finding schema (maps onto the `findings` table in section 6.4)
# ----------------------------------------------------------------------------
@dataclass
class Finding:
    domain: str                  # "visual" | "a11y"
    rule_id: str                 # e.g. "A-007"
    severity: str                # LOW | MEDIUM | HIGH | CRITICAL
    confidence: float            # 0..1
    title: str
    message: str
    suggestion: Optional[str] = None
    bbox: Optional[list[int]] = None
    evidence: dict = field(default_factory=dict)
    verdict_type: str = "finding"    # "finding" or "question" (low confidence)
    route: str = "creator"           # "creator" or "human_review"


class VisionProvider(Protocol):
    """Implemented later on top of the provider abstraction (Inkloom / fallbacks)."""
    def text_regions(self, image: Image.Image) -> list[BBox]: ...
    def alt_text(self, image: Image.Image) -> Optional[str]: ...


# ----------------------------------------------------------------------------
# Colour maths: sRGB -> Lab (D65), CIE76, WCAG luminance/contrast
# ----------------------------------------------------------------------------
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb) -> str:
    r, g, b = (int(round(float(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _linear(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def rgb_to_lab(rgb) -> np.ndarray:
    lin = _linear(np.asarray(rgb))
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def delta_e76(rgb1, rgb2) -> float:
    return float(np.linalg.norm(rgb_to_lab(rgb1) - rgb_to_lab(rgb2)))


def rel_luminance(rgb) -> np.ndarray:
    lin = _linear(np.asarray(rgb))
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def contrast_ratio(l1, l2):
    hi, lo = np.maximum(l1, l2), np.minimum(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# ----------------------------------------------------------------------------
# P-011  Palette drift
# ----------------------------------------------------------------------------
def dominant_colors(arr: np.ndarray, min_coverage: float = 0.03, top_n: int = 8):
    """Quantise to 4 bits/channel, return [(mean_rgb, coverage)], plus top-N coverage."""
    px = arr.reshape(-1, 3)
    keys = (px[:, 0] >> 4).astype(np.int32) * 256 + (px[:, 1] >> 4) * 16 + (px[:, 2] >> 4)
    uniq, inv, counts = np.unique(keys, return_inverse=True, return_counts=True)
    order = np.argsort(-counts)
    out = []
    for i in order[:top_n]:
        cov = counts[i] / len(px)
        if cov >= min_coverage:
            out.append((px[inv == i].mean(axis=0), float(cov)))
    topn_cov = float(counts[order[:top_n]].sum() / len(px))
    return out, topn_cov


def check_palette(arr: np.ndarray, kit: BrandKit) -> list[Finding]:
    colors, topn_cov = dominant_colors(arr)
    photographic = topn_cov < 0.5  # no clear flat-colour structure
    pal = {k: np.array(hex_to_rgb(v)) for k, v in kit.palette.items()}
    findings = []
    for rgb, cov in colors:
        lab = rgb_to_lab(rgb)
        if kit.allow_neutrals and math.hypot(lab[1], lab[2]) < 6:
            continue
        name, de = min(((k, delta_e76(rgb, v)) for k, v in pal.items()), key=lambda t: t[1])
        if de <= kit.delta_e_max:
            continue
        conf = 0.4 if photographic else 0.8
        findings.append(Finding(
            domain="visual", rule_id="P-011",
            severity="MEDIUM" if cov > 0.25 else "LOW", confidence=conf,
            title="Off-palette colour",
            message=(f"{rgb_to_hex(rgb)} covers {cov:.0%} of the creative; nearest approved "
                     f"token is '{name}' ({kit.palette[name]}) at \u0394E {de:.1f} "
                     f"(limit {kit.delta_e_max:g})."),
            suggestion=f"Replace with '{name}' {kit.palette[name]} or another palette token.",
            evidence={"colour": rgb_to_hex(rgb), "coverage": round(cov, 3),
                      "nearest": name, "delta_e": round(de, 2), "photographic": photographic}))
    return findings


# ----------------------------------------------------------------------------
# A-003  Contrast of text on the creative
# ----------------------------------------------------------------------------
def estimate_text_contrast(arr: np.ndarray, bbox: BBox):
    """Split a text region into fg/bg (1-D 2-means on luminance); conservative bg (p10)."""
    x0, y0, x1, y1 = bbox
    reg = arr[y0:y1, x0:x1].reshape(-1, 3).astype(np.float64)
    if len(reg) < 16:
        return None
    lum = rel_luminance(reg)
    if lum.max() - lum.min() < 0.02:
        return None  # flat: no text here
    c = np.array([lum.min(), lum.max()])  # extremes, so small text (<5% of pixels) still seeds a cluster
    for _ in range(12):
        lab = (np.abs(lum - c[0]) > np.abs(lum - c[1])).astype(int)
        for k in (0, 1):
            if (lab == k).any():
                c[k] = lum[lab == k].mean()
    fg_k = 0 if (lab == 0).sum() < (lab == 1).sum() else 1  # text is the minority
    fg, bg = reg[lab == fg_k], reg[lab != fg_k]
    if len(fg) < 4 or len(bg) < 4:
        return None
    bg_med = np.median(bg, axis=0)
    bg_l = float(rel_luminance(bg_med))
    far = np.argsort(-np.abs(rel_luminance(fg) - bg_l))[: max(4, len(fg) // 2)]
    fg_rgb = fg[far].mean(axis=0)
    ratios = contrast_ratio(float(rel_luminance(fg_rgb)), rel_luminance(bg))
    return {"ratio": float(np.percentile(ratios, 10)), "fg": fg_rgb, "bg": bg_med,
            "bg_std": float(bg.std(axis=0).mean())}


def check_contrast(arr: np.ndarray, kit: BrandKit, boxes: Optional[list[BBox]],
                   large_text: bool = False) -> list[Finding]:
    from_model = bool(boxes)
    boxes = boxes or [(0, 0, arr.shape[1], arr.shape[0])]
    need = kit.contrast_min_large if large_text else kit.contrast_min
    ink = np.array(hex_to_rgb(kit.text_ink))
    findings = []
    for b in boxes:
        est = estimate_text_contrast(arr, b)
        if est is None or est["ratio"] >= need:
            continue
        r = est["ratio"]
        conf = 0.9 if from_model else 0.5
        if est["bg_std"] > 40:  # busy photographic background
            conf = min(conf, 0.6)
        bg = est["bg"]
        ink_ratio = float(contrast_ratio(rel_luminance(ink), rel_luminance(bg)))
        if ink_ratio >= need:
            sug = f"Use text token {kit.text_ink} ({ink_ratio:.1f}:1 on this background)."
        else:
            alt = "#000000" if rel_luminance(bg) > 0.18 else "#FFFFFF"
            alt_r = float(contrast_ratio(rel_luminance(np.array(hex_to_rgb(alt))), rel_luminance(bg)))
            sug = (f"Brand ink does not reach {need:g}:1 here; use {alt} ({alt_r:.1f}:1) "
                   f"or darken/lighten the background.")
        findings.append(Finding(
            domain="a11y", rule_id="A-003",
            severity="MEDIUM" if r < 3.0 else "LOW", confidence=conf,
            title="Text contrast below WCAG AA",
            message=f"Text {rgb_to_hex(est['fg'])} on {rgb_to_hex(bg)} measures {r:.1f}:1; needs {need:g}:1.",
            suggestion=sug, bbox=list(b),
            evidence={"ratio": round(r, 2), "required": need, "fg": rgb_to_hex(est["fg"]),
                      "bg": rgb_to_hex(bg), "region_source": "vision" if from_model else "whole_image"}))
    return findings


def check_alt_text(alt_text: Optional[str], vision: Optional[VisionProvider],
                   img: Image.Image) -> list[Finding]:
    if alt_text and alt_text.strip():
        return []
    draft = vision.alt_text(img) if vision else None
    return [Finding(
        domain="a11y", rule_id="A-003", severity="LOW", confidence=0.95,
        title="Missing alt text", message="No alt text supplied for this creative.",
        suggestion=(f"Draft alt text (review before use): {draft}" if draft
                    else "Add a concise description of the image content."))]


# ----------------------------------------------------------------------------
# A-007  Logo checks
# ----------------------------------------------------------------------------
@dataclass
class LogoMatch:
    bbox: BBox
    score: float
    kx: float   # horizontal scale vs native template
    ky: float


def _box_sum(a: np.ndarray, h: int, w: int) -> np.ndarray:
    c = np.pad(a.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return c[h:, w:] - c[:-h, w:] - c[h:, :-w] + c[:-h, :-w]


def _ncc(img: np.ndarray, tmpl: np.ndarray) -> Optional[np.ndarray]:
    """Normalised cross-correlation map via FFT + integral images (valid region)."""
    H, W = img.shape
    h, w = tmpl.shape
    if h < 4 or w < 4 or h > H or w > W:
        return None
    t0 = tmpl - tmpl.mean()
    tn = math.sqrt(float((t0 ** 2).sum()))
    if tn < 1e-6:
        return None
    corr = np.fft.irfft2(np.fft.rfft2(img) * np.conj(np.fft.rfft2(t0, s=(H, W))), s=(H, W))
    corr = corr[: H - h + 1, : W - w + 1]
    n = h * w
    s1, s2 = _box_sum(img, h, w), _box_sum(img * img, h, w)
    var = np.maximum(s2 - s1 * s1 / n, 0)
    den = np.sqrt(var) * tn
    return np.where(den > 1e-3 * n, corr / np.maximum(den, 1e-9), 0.0)


def _gray(im: Image.Image) -> np.ndarray:
    return np.asarray(im.convert("L"), dtype=np.float64) / 255.0


def find_logo(img: Image.Image, template: Image.Image, min_score: float = 0.6) -> Optional[LogoMatch]:
    """Multi-scale match, then a small aspect-ratio sweep to detect stretching."""
    s0 = min(1.0, 1024 / max(img.size))
    work = _gray(img.resize((max(1, int(img.width * s0)), max(1, int(img.height * s0)))))
    tw, th = template.size

    def match(kx: float, ky: float):
        w, h = max(4, int(round(tw * kx * s0))), max(4, int(round(th * ky * s0)))
        m = _ncc(work, _gray(template.resize((w, h))))
        if m is None:
            return None
        y, x = np.unravel_index(int(np.argmax(m)), m.shape)
        return float(m[y, x]), x, y, w, h

    best = None
    k = 0.25
    while k <= 2.5:
        r = match(k, k)
        if r and (best is None or r[0] > best[0][0]):
            best = (r, k, k)
        k *= 1.15
    if best is None:
        return None
    (_, _, _, _, _), kb, _ = best
    for kk in (kb / 1.1, kb, kb * 1.1):          # refine isotropic
        for ratio in (1.0, 0.85, 0.92, 1.08, 1.18):  # y/x stretch sweep
            r = match(kk, kk * ratio)
            if r and r[0] > best[0][0] + 1e-6:
                best = (r, kk, kk * ratio)
    (score, x, y, w, h), kx, ky = best
    if score < min_score:
        return None
    return LogoMatch(bbox=(int(x / s0), int(y / s0), int((x + w) / s0), int((y + h) / s0)),
                     score=score, kx=kx, ky=ky)


def measure_clear_space(arr: np.ndarray, bbox: BBox, max_scan: int,
                        l1_thresh: int = 45, frac: float = 0.004) -> dict[str, tuple[int, bool]]:
    """Free pixels on each side of the logo before anything non-background appears.
    Returns {side: (pixels, hit_canvas_edge)}."""
    H, W = arr.shape[:2]
    x0, y0, x1, y1 = bbox
    pad = 3
    ring = np.zeros((H, W), dtype=bool)
    ring[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)] = True
    ring[y0:y1, x0:x1] = False
    bg = np.median(arr[ring].astype(np.int32), axis=0) if ring.any() else np.median(arr.reshape(-1, 3), axis=0)
    dev = np.abs(arr.astype(np.int32) - bg).sum(-1) > l1_thresh

    def scan(side: str):
        for d in range(1, max_scan + 1):
            if side == "left":
                if x0 - d < 0: return d - 1, True
                line = dev[y0:y1, x0 - d]
            elif side == "right":
                if x1 + d - 1 >= W: return d - 1, True
                line = dev[y0:y1, x1 + d - 1]
            elif side == "top":
                if y0 - d < 0: return d - 1, True
                line = dev[y0 - d, x0:x1]
            else:
                if y1 + d - 1 >= H: return d - 1, True
                line = dev[y1 + d - 1, x0:x1]
            if line.mean() > frac:
                return d - 1, False
        return max_scan, False

    return {s: scan(s) for s in ("left", "right", "top", "bottom")}


def check_logo(img: Image.Image, arr: np.ndarray, kit: BrandKit) -> list[Finding]:
    if not kit.logo_template_path:
        return []
    template = Image.open(kit.logo_template_path).convert("RGB")
    m = find_logo(img, template)
    if m is None:
        # Cannot tell whether the logo is absent, tiny, or distorted: ask, don't judge.
        return [Finding(domain="visual", rule_id="A-007", severity="LOW", confidence=0.4,
                        title="Logo not located",
                        message="No confident logo match found in this creative.",
                        suggestion="Confirm whether the logo is required on this asset and whether it is unmodified.",
                        verdict_type="question")]
    findings: list[Finding] = []
    x0, y0, x1, y1 = m.bbox
    w, h = x1 - x0, y1 - y0
    base_conf = min(0.95, 0.55 + 0.4 * m.score)

    # stretch
    distortion = m.ky / m.kx
    if abs(distortion - 1) > 0.06:
        findings.append(Finding(
            domain="visual", rule_id="A-007", severity="HIGH", confidence=min(base_conf, 0.8),
            title="Logo appears stretched",
            message=f"Logo aspect ratio is {distortion:.2f}x the approved proportions.",
            suggestion="Re-place the original logo file and scale it proportionally (lock aspect ratio).",
            bbox=[x0, y0, x1, y1], evidence={"aspect_distortion": round(distortion, 3), "match": round(m.score, 3)}))

    # min size
    if w < kit.min_logo_px:
        findings.append(Finding(
            domain="visual", rule_id="A-007", severity="MEDIUM", confidence=base_conf,
            title="Logo below minimum size",
            message=f"Logo is {w}px wide; minimum for digital is {kit.min_logo_px}px.",
            suggestion=f"Scale the logo to at least {kit.min_logo_px}px wide.", bbox=[x0, y0, x1, y1],
            evidence={"width_px": w, "min_px": kit.min_logo_px}))

    # clear-space
    need = kit.clear_space_ratio * h
    sides = measure_clear_space(arr, m.bbox, max_scan=int(math.ceil(need * 2)))
    worst_side, (worst_px, edge) = min(sides.items(), key=lambda kv: kv[1][0])
    if worst_px < need:
        viol = (need - worst_px) / need
        findings.append(Finding(
            domain="visual", rule_id="A-007", severity="MEDIUM" if viol >= 0.5 else "LOW",
            confidence=base_conf,
            title="Logo clear-space violated",
            message=(f"Only {worst_px}px free on the {worst_side} side"
                     f"{' (canvas edge)' if edge else ''}; need {need:.0f}px "
                     f"({kit.clear_space_ratio:g}x logo height). Violation: {viol:.0%}."),
            suggestion=f"Move neighbouring elements (or the logo) so at least {math.ceil(need)}px stays clear on every side.",
            bbox=[x0, y0, x1, y1],
            evidence={"free_px": {k: v[0] for k, v in sides.items()}, "required_px": round(need, 1),
                      "violation_pct": round(viol * 100, 1)}))

    # wordmark recolour: compare foreground pixels inside the logo box to approved colourways
    inner = arr[y0:y1, x0:x1].astype(np.int32)
    ring_bg = np.median(np.concatenate([inner[0], inner[-1], inner[:, 0], inner[:, -1]]), axis=0)
    fgmask = np.abs(inner - ring_bg).sum(-1) > 45
    if fgmask.sum() > 20:
        fg = inner[fgmask].mean(axis=0)
        de, nearest = min(((delta_e76(fg, hex_to_rgb(c)), c) for c in kit.wordmark_colors), key=lambda t: t[0])
        if de > kit.delta_e_max * 1.5:   # looser: logo has multiple colours, mean is blended
            findings.append(Finding(
                domain="visual", rule_id="A-007", severity="HIGH", confidence=min(base_conf, 0.7),
                title="Logo colourway not approved",
                message=f"Logo foreground averages {rgb_to_hex(fg)}; nearest approved colourway is {nearest} (\u0394E {de:.0f}).",
                suggestion="Use the approved logo colourway; never recolour the wordmark.",
                bbox=[x0, y0, x1, y1], evidence={"delta_e": round(de, 1), "nearest": nearest}))
    return findings


# ----------------------------------------------------------------------------
# Orchestration, routing, serialisation
# ----------------------------------------------------------------------------
_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
LOW_CONFIDENCE = 0.6


def route(findings: list[Finding]) -> list[Finding]:
    """Honest-AI routing: weak evidence becomes a question for a human, never a verdict."""
    for f in findings:
        if f.confidence < LOW_CONFIDENCE:
            f.verdict_type = "question"
        if f.severity == "CRITICAL" or f.verdict_type == "question":
            f.route = "human_review"
    return sorted(findings, key=lambda f: (_SEV_ORDER[f.severity], -f.confidence))


def review_image(path_or_image, kit: BrandKit, vision: Optional[VisionProvider] = None,
                 alt_text: Optional[str] = None, text_boxes: Optional[list[BBox]] = None,
                 large_text: bool = False) -> dict:
    img = Image.open(path_or_image) if isinstance(path_or_image, (str, bytes)) else path_or_image
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, hex_to_rgb(kit.palette.get("paper", "#FFFFFF")))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    img = img.convert("RGB")
    arr = np.asarray(img)

    boxes = text_boxes if text_boxes is not None else (vision.text_regions(img) if vision else None)
    findings: list[Finding] = []
    degraded: list[str] = []
    for name, fn in (("palette", lambda: check_palette(arr, kit)),
                     ("contrast", lambda: check_contrast(arr, kit, boxes, large_text)),
                     ("alt_text", lambda: check_alt_text(alt_text, vision, img)),
                     ("logo", lambda: check_logo(img, arr, kit))):
        try:
            findings += fn()
        except Exception as exc:  # never silently drop a check
            degraded.append(f"{name}: {exc!r}")
    findings = route(findings)
    return {
        "checks_run": ["palette", "contrast", "alt_text", "logo" if kit.logo_template_path else "logo(skipped: no template)"],
        "degraded_checks": degraded,
        "max_severity": findings[0].severity if findings else None,
        "findings": [asdict(f) for f in findings],
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="BrandPilot image review")
    ap.add_argument("image")
    ap.add_argument("--logo", help="logo template PNG")
    ap.add_argument("--alt", help="alt text supplied with the creative")
    a = ap.parse_args()
    kit = BrandKit(logo_template_path=a.logo)
    print(json.dumps(review_image(a.image, kit, alt_text=a.alt), indent=2))
