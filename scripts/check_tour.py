"""Static check of the guided tour (no browser needed). Run: python scripts/check_tour.py

Every step must point at a real page, every click target must exist somewhere in the UI source,
every chapter must have steps, and the tour must end with a Finish step. It cannot prove the
spotlight lands on the right pixel; run e2e/ui_flow.py or click through once for that."""
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parent.parent / "frontend"
src = (root / "components" / "Tour.tsx").read_text(encoding="utf-8")
ui = "\n".join(p.read_text(encoding="utf-8") for p in list(root.glob("app/**/*.tsx")) + list(root.glob("components/*.tsx")))
pages = {"/" + str(p.parent.relative_to(root / "app")).replace("\\", "/") for p in root.glob("app/**/page.tsx")}
pages = {("/" if q == "/." else q) for q in pages}

steps = re.findall(r"^\s*\{ ch: \"([^\"]+)\", title: \"([^\"]+)\"(.*)\},?\s*$", src, re.M)
errs = []
def field(rest, key):
    m = re.search(key + r': "((?:[^"\\]|\\.)*)"', rest) or re.search(key + r": '((?:[^'\\]|\\.)*)'", rest)
    return m.group(1) if m else None

def known(route):
    if route in pages or route == "/assets/":
        return True
    return any(p.startswith(route) or p.endswith(route) for p in pages)   # "/proof" is the tail of /assets/[id]/proof

for n, (ch, title, rest) in enumerate(steps, 1):
    for key in ("route", "to", "go"):
        v = field(rest, key)
        if v and not known(v):
            errs.append(f"step {n} '{title}': {key}={v} is not a page")
    t = field(rest, "text")
    if t and t not in ui:
        errs.append(f"step {n} '{title}': click text '{t}' not found in the UI source")
    adv = field(rest, "adv")
    if adv == "click" and not (t or field(rest, "sel")):
        errs.append(f"step {n} '{title}': adv=click without a target")

chapters = re.search(r"const CHAPTERS = \[(.*?)\]", src).group(1)
for c in re.findall(r'"([^"]+)"', chapters):
    if not any(s[0] == c for s in steps):
        errs.append(f"chapter '{c}' has no steps")
if not steps or steps[-1][0] != "Done":
    errs.append("the last step must be in chapter 'Done'")
for need in ("End tour", "Back", "Next", "Finish", "Escape"):
    if need not in src:
        errs.append(f"control missing: {need}")

print(f"{len(steps)} steps, {len(pages)} pages, chapters: {chapters}")
if errs:
    print("\n".join("FAIL " + e for e in errs)); sys.exit(1)
print("TOUR CHECK PASSED")
