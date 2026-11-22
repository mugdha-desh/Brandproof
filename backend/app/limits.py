"""Hardening: upload limits, content sniffing, rate limiting, security headers, secret checks.

All limits read the environment lazily so tests can override them. Rate limiting is in memory and per process:
fine for one API instance (our deployment), not for several. Say so before scaling out (see docs/SECURITY.md).
"""
import logging
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

log = logging.getLogger("brandproof.security")

ALLOWED_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".txt", ".md")


# ------------------------------------------------------------------ configuration
def max_upload_bytes() -> int:
    return int(float(os.getenv("BP_MAX_UPLOAD_MB", "10")) * 1024 * 1024)


def max_pdf_pages() -> int:
    return int(os.getenv("BP_MAX_PDF_PAGES", "100"))


def max_image_pixels() -> int:
    return int(float(os.getenv("BP_MAX_IMAGE_MEGAPIXELS", "40")) * 1_000_000)


def max_text_chars() -> int:
    return int(os.getenv("BP_MAX_TEXT_CHARS", "100000"))


def rate_limit_enabled() -> bool:
    return os.getenv("BP_RATE_LIMIT", "1") != "0"


def _rule(env: str, default: str) -> tuple[int, int]:
    n, _, sec = os.getenv(env, default).partition("/")
    return int(n), int(sec or 60)


# ------------------------------------------------------------------ uploads
def sniff(data: bytes) -> str | None:
    """What the bytes really are, whatever the file name or content type claims."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
        return "image"
    return None


async def read_upload(upload, max_bytes: int | None = None) -> bytes:
    """Read an UploadFile in bounded chunks; reject oversized bodies before buffering them fully."""
    limit = max_upload_bytes() if max_bytes is None else max_bytes
    chunks = []
    total = 0
    while True:
        chunk = await upload.read(min(64 * 1024, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, f"File is larger than {limit // (1024 * 1024)} MB")
        chunks.append(chunk)
    return b"".join(chunks)


def check_upload(data: bytes | None, filename: str, kind: str) -> None:
    """Raise 413/415 for files we will not process. `kind` is the kind the service derived from name and type."""
    if not data:
        return
    if len(data) > max_upload_bytes():
        raise HTTPException(413, f"File is larger than {max_upload_bytes() // (1024 * 1024)} MB")
    name = (filename or "").lower()
    if not name.endswith(ALLOWED_EXT):
        raise HTTPException(415, "Unsupported file type. Use PDF, PNG, JPG, TXT or MD.")
    real = sniff(data)
    if kind in ("pdf", "image") and real != kind:
        raise HTTPException(415, f"The file says it is a {kind} but its contents are not. It was not processed.")
    if kind == "text" and real is not None:
        raise HTTPException(415, "The file name says text but its contents are a binary file. It was not processed.")
    _check_dimensions(data, kind)


def _check_dimensions(data: bytes, kind: str) -> None:
    """Refuse files that are small on disk but huge once opened (page floods, decompression bombs)."""
    if kind == "pdf":
        try:
            import pymupdf as fitz
            with fitz.open(stream=data, filetype="pdf") as doc:
                pages = doc.page_count
        except Exception:
            raise HTTPException(415, "The PDF is corrupted or cannot be opened. It was not processed.")
        if pages > max_pdf_pages():
            raise HTTPException(413, f"The PDF has {pages} pages; the limit is {max_pdf_pages()}")
    elif kind == "image":
        try:
            import io
            from PIL import Image
            with Image.open(io.BytesIO(data)) as im:
                pixels = im.width * im.height
        except Exception:
            raise HTTPException(415, "The image is corrupted or cannot be opened. It was not processed.")
        if pixels > max_image_pixels():
            raise HTTPException(413, f"The image is {pixels / 1e6:.0f} megapixels; the limit is {max_image_pixels() / 1e6:.0f}")


def check_guideline_file(data: bytes | None) -> None:
    if data and len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Guideline file is larger than 5 MB")


def check_logo(data: bytes) -> None:
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "Logo is larger than 2 MB")
    if sniff(data) != "image":
        raise HTTPException(415, "A logo must be a PNG or JPEG image")
    _check_dimensions(data, "image")

def check_text(text: str | None) -> None:
    if text and len(text) > max_text_chars():
        raise HTTPException(413, f"Text is longer than {max_text_chars():,} characters")


# ------------------------------------------------------------------ rate limiting
class Limiter:
    """Sliding window per key. Thread-safe. `hit` counts an event; `blocked` only checks."""

    def __init__(self):
        self._lock = threading.Lock()
        self._events: dict[str, deque] = defaultdict(deque)

    def _trim(self, q: deque, window: int, now: float):
        while q and q[0] <= now - window:
            q.popleft()

    def blocked(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._events[key]
            self._trim(q, window, now)
            return len(q) >= limit

    def hit(self, key: str, limit: int, window: int) -> bool:
        """Record an event. Returns True when it is within the limit."""
        now = time.monotonic()
        with self._lock:
            q = self._events[key]
            self._trim(q, window, now)
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self):
        with self._lock:
            self._events.clear()


limiter = Limiter()


def reset():
    limiter.reset()


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")) or "unknown"


def _too_many(window: int):
    return HTTPException(429, "Too many requests. Please wait a little and try again.", headers={"Retry-After": str(window)})


def throttle(bucket: str, env: str, default: str):
    """FastAPI dependency factory: limit requests per client IP, e.g. throttle('upload', 'BP_RATE_UPLOAD', '30/60')."""
    def dep(request: Request):
        if not rate_limit_enabled():
            return
        limit, window = _rule(env, default)
        if not limiter.hit(f"{bucket}:{client_ip(request)}", limit, window):
            raise _too_many(window)
    return dep


def login_blocked(request: Request, email: str) -> None:
    """Brute-force guard: only FAILED logins count, per IP+email and per IP overall."""
    if not rate_limit_enabled():
        return
    limit, window = _rule("BP_RATE_LOGIN_FAILS", "8/300")
    ip = client_ip(request)
    if limiter.blocked(f"loginfail:{ip}:{email}", limit, window) or limiter.blocked(f"loginfail-ip:{ip}", limit * 4, window):
        raise _too_many(window)


def login_failed(request: Request, email: str) -> None:
    if not rate_limit_enabled():
        return
    limit, window = _rule("BP_RATE_LOGIN_FAILS", "8/300")
    ip = client_ip(request)
    limiter.hit(f"loginfail:{ip}:{email}", 10 ** 6, window)
    limiter.hit(f"loginfail-ip:{ip}", 10 ** 6, window)


# ------------------------------------------------------------------ headers and body size
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


def install(app):
    @app.middleware("http")
    async def guard(request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > max_upload_bytes() + 1024 * 1024:     # headroom for form fields
            from fastapi.responses import JSONResponse
            resp = JSONResponse({"detail": f"Request is larger than {max_upload_bytes() // (1024 * 1024)} MB"}, status_code=413)
        else:
            resp = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp


# ------------------------------------------------------------------ secrets
def check_secrets() -> list[str]:
    """In production (BP_ENV=production) a weak secret stops the server from starting. Elsewhere it only warns."""
    from . import config
    problems = []
    sec = config.secret()
    if sec.startswith("dev-secret-change-me") or sec.startswith("change-me") or len(sec) < 32:
        problems.append("BP_SECRET is the default or shorter than 32 characters; tokens and receipts could be forged")
    if config.seed_enabled() and config.demo_password() == "demo1234":
        problems.append("Demo accounts use the default password (set BP_SEED=0 for a real deployment)")
    prod = os.getenv("BP_ENV", "").lower() == "production"
    if prod and any(p.startswith("BP_SECRET") for p in problems):
        raise RuntimeError("Refusing to start in production: " + "; ".join(problems))
    if prod and config.seed_enabled() and config.demo_password() == "demo1234":
        raise RuntimeError("Refusing to start in production: BP_DEMO_PASSWORD is the public demo default; set a strong unique value")
    for p in problems:
        log.warning("security: %s", p)
    return problems
