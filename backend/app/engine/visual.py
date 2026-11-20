"""Picture checks that need no AI: approved-brand-colour use and logo placement.

Everything here is deterministic image analysis (Pillow, plus OpenCV for logo matching). It never calls an external service.
Honest limits, which are also written into every Proof Pack's "not checked" list:
- Brand colours are estimated from the largest colour areas of the picture. Photos and gradients can be misjudged.
- A logo is found by template matching against the logos the owner uploaded. It finds flat, unrotated copies in the same
  colours; a recoloured, rotated, or partly hidden logo may not be found, and then nothing is reported about it.
- Clear space is judged by how busy the surroundings are, not by what they contain.
"""
import io

from PIL import Image, ImageChops

from . import textutil as tu

try:
    import cv2
    import numpy as np
    HAVE_CV = True
except Exception:  # OpenCV is optional: without it the logo checks are listed as not run
    HAVE_CV = False

MAX_SIDE = 1000
DEFAULTS = {"clear_space_ratio": 0.25, "min_width_ratio": 0.05, "min_match": 0.62, "required": False}


# ------------------------------------------------------------------ loading
def pages(kind: str, data: bytes | None, limit: int = 2) -> list[tuple[str, Image.Image]]:
    if not data:
        return []
    out = []
    try:
        if kind == "image":
            out.append(("image", Image.open(io.BytesIO(data)).convert("RGB")))
        elif kind == "pdf":
            import pymupdf
            doc = pymupdf.open(stream=data, filetype="pdf")
            for i in range(min(limit, doc.page_count)):
                pix = doc[i].get_pixmap(dpi=90)
                out.append((f"page {i + 1}", Image.frombytes("RGB", (pix.width, pix.height), pix.samples)))
    except Exception:
        return []
    for _, im in out:
        im.thumbnail((MAX_SIDE, MAX_SIDE))
    return out


def _logo_gray(blob: bytes):
    im = Image.open(io.BytesIO(blob))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    im = im.convert("RGB")
    box = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()  # trim the white border
    if box:
        im = im.crop(box)
    return np.array(im.convert("L"))


# ------------------------------------------------------------------ approved colours in pictures
def palette_issues(img: Image.Image, palette: list[tuple[str, str]], max_delta: float) -> list[dict]:
    """Large, clearly coloured areas that are not close to any approved palette colour."""
    items = [(n, h, tu.hex_to_rgb(h)) for n, h in palette]
    small = img.copy()
    small.thumbnail((160, 160))
    q = small.quantize(colors=10, method=Image.Quantize.MEDIANCUT)
    pal, total = q.getpalette(), small.width * small.height
    out = []
    for count, idx in sorted(q.getcolors(), reverse=True):
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        share = count / total
        if share < 0.04 or tu.is_neutral(rgb):
            continue
        near = min(items, key=lambda p: tu.delta_e(rgb, p[2]))
        de = tu.delta_e(rgb, near[2])
        if de > max_delta * 1.6:
            out.append({"hex": tu.rgb_to_hex(rgb), "share": share, "near": near[0], "near_hex": near[1], "de": de})
    return out[:3]


# ------------------------------------------------------------------ logo use
def _best(gray, tpl_gray, widths, aspects):
    H, W = gray.shape
    lh, lw = tpl_gray.shape
    best = (0.0, None, 1.0)
    for tw in widths:
        for a in aspects:
            th = int(tw * lh / lw * a)
            if tw < 12 or th < 12 or tw >= W or th >= H:
                continue
            t = cv2.resize(tpl_gray, (tw, th), interpolation=cv2.INTER_AREA)
            if t.std() < 8:
                continue
            _, mx, _, loc = cv2.minMaxLoc(cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED))
            if mx > best[0]:
                best = (mx, (loc[0], loc[1], tw, th), a)
    return best


def locate_logo(gray, tpl_gray, min_match: float) -> dict | None:
    H, W = gray.shape
    coarse = [int(W * f) for f in np.geomspace(0.02, 0.6, 20)]
    score, box, _ = _best(gray, tpl_gray, coarse, (1.0,))
    if box is None or score < min_match - 0.12:
        return None
    tw0 = box[2]
    fine = sorted({int(tw0 * f) for f in (0.85, 0.92, 1.0, 1.08, 1.17)})
    s_uni, b_uni, _ = _best(gray, tpl_gray, fine, (1.0,))
    s_any, b_any, a_any = _best(gray, tpl_gray, fine, (0.7, 0.8, 0.9, 1.0, 1.12, 1.25, 1.4))
    stretched = a_any != 1.0 and s_any >= s_uni + 0.05 and s_any >= min_match
    if stretched:
        return {"score": s_any, "box": b_any, "aspect": a_any, "stretched": True}
    if s_uni >= min_match:
        return {"score": s_uni, "box": b_uni, "aspect": 1.0, "stretched": False}
    return None


def crowded(gray, box, ratio: float) -> bool:
    x, y, w, h = box
    H, W = gray.shape
    m = max(4, int(max(w, h) * ratio))
    edges = cv2.Canny(gray, 80, 160)
    x0, y0, x1, y1 = max(0, x - m), max(0, y - m), min(W, x + w + m), min(H, y + h + m)
    mask = np.zeros(gray.shape, dtype=bool)
    mask[y0:y1, x0:x1] = True
    pad = 3
    mask[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad)] = False
    n = mask.sum()
    return bool(n) and (edges[mask] > 0).sum() / n > 0.03


# ------------------------------------------------------------------ entry point
def analyze(kind: str, data: bytes | None, rules: list, lib: dict, read_blob) -> dict:
    """Returns {"findings": [(rule, text, quote, confidence)], "notes": [str]}.  `read_blob(path)` loads a stored logo."""
    by = {r.method: r for r in rules}
    out = {"findings": [], "notes": []}
    if kind not in ("image", "pdf") or not data:
        return out
    pgs = pages(kind, data)
    if not pgs:
        return out

    pal_rule = by.get("palette")
    palette = [(i.name, i.value["hex"]) for i in lib.get("palette", []) if i.value.get("hex")]
    if kind == "image" and pal_rule and palette:
        for pg, im in pgs:
            for c in palette_issues(im, palette, float(pal_rule.params.get("max_delta_e", 25))):
                out["findings"].append((pal_rule, f"A colour near {c['hex']} fills about {c['share'] * 100:.0f}% of the picture and is not "
                                        f"in the approved palette. Closest approved colour: {c['near']} {c['near_hex']} (difference {c['de']:.0f}).",
                                        c["hex"], 0.8))
        out["notes"].append("Brand colours in pictures are estimated from the largest colour areas; photos and gradients can be misjudged.")

    logo_rule = by.get("logo")
    if logo_rule:
        logos = [(i.name, i.file_path) for i in lib.get("logo", []) if i.file_path]
        if not logos:
            out["notes"].append("No approved logo is uploaded, so logo use in pictures was not checked.")
        elif not HAVE_CV:
            out["notes"].append("Logo checks did not run on this server (OpenCV is not installed).")
        else:
            p = {**DEFAULTS, **(logo_rule.params or {})}
            tpls = []
            for name, path in logos:
                try:
                    tpls.append((name, _logo_gray(read_blob(path))))
                except Exception:
                    continue
            for pg, im in pgs:
                gray = np.array(im.convert("L"))
                where = "" if kind == "image" else f" ({pg})"
                hit = None
                for name, tg in tpls:
                    hit = locate_logo(gray, tg, float(p["min_match"]))
                    if hit:
                        hit["name"] = name
                        break
                if not hit:
                    if p.get("required") and pg in ("image", "page 1"):
                        out["findings"].append((logo_rule, "None of the approved logos was found in this picture.", "", 0.7))
                    continue
                x, y, w, h = hit["box"]
                if hit["stretched"]:
                    off = abs(hit["aspect"] - 1) * 100
                    out["findings"].append((logo_rule, f"The {hit['name']} logo{where} looks stretched or squashed (about {off:.0f}% off its "
                                            "original proportions).", hit["name"], 0.8))
                if w / gray.shape[1] < float(p["min_width_ratio"]):
                    out["findings"].append((logo_rule, f"The {hit['name']} logo{where} is only {w / gray.shape[1] * 100:.0f}% of the width; "
                                            f"the minimum is {float(p['min_width_ratio']) * 100:.0f}%.", hit["name"], 0.8))
                if crowded(gray, hit["box"], float(p["clear_space_ratio"])):
                    out["findings"].append((logo_rule, f"Other content sits inside the {hit['name']} logo's clear space{where} "
                                            f"(about {float(p['clear_space_ratio']) * 100:.0f}% of the logo size is needed on every side).",
                                            hit["name"], 0.7))
            out["notes"].append(f"Logo use was checked by image matching against {len(tpls)} uploaded logo(s). Only flat, unrotated copies in the "
                                "original colours are found; a recoloured, rotated or partly hidden logo may be missed.")
    return out
