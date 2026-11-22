"""Round 3 step 6: upload limits, content sniffing, rate limiting, security headers and secret checks."""
import pytest

from app import limits
from conftest import login, pdf_bytes

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
INTENT = "Announce our new savings account"


def post(client, h, name="a.txt", data=None, content_type="text/plain", text=None, title="t"):
    form = {"title": title, "intent": INTENT, "channel": "social"}
    if text is not None:
        form["text"] = text
    files = {"file": (name, data, content_type)} if data is not None else None
    return client.post("/api/assets", data=form, files=files, headers=h)


# ------------------------------------------------------------------ uploads
def test_oversized_file_is_refused_with_413(client, monkeypatch):
    monkeypatch.setenv("BP_MAX_UPLOAD_MB", "0.001")          # about 1 KB
    h = login(client)
    r = post(client, h, "big.pdf", b"%PDF-1.4 " + b"x" * 5000, "application/pdf")
    assert r.status_code == 413


def test_huge_request_is_stopped_before_it_is_read(client, monkeypatch):
    monkeypatch.setenv("BP_MAX_UPLOAD_MB", "0.001")
    h = login(client)
    r = post(client, h, "huge.pdf", b"%PDF-1.4 " + b"x" * (2 * 1024 * 1024), "application/pdf")
    assert r.status_code == 413 and "larger" in r.json()["detail"]


def test_unsupported_file_types_are_refused(client):
    h = login(client)
    assert post(client, h, "run.exe", b"MZ\x90\x00", "application/octet-stream").status_code == 415
    assert post(client, h, "doc.docx", b"PK\x03\x04", "application/vnd.openxmlformats").status_code == 415


def test_file_contents_must_match_the_claimed_type(client):
    h = login(client)
    assert post(client, h, "fake.pdf", b"this is not a pdf", "application/pdf").status_code == 415
    assert post(client, h, "fake.png", b"<html>not an image</html>", "image/png").status_code == 415
    assert post(client, h, "photo.pdf", PNG, "application/pdf").status_code == 415       # an image wearing a .pdf name
    assert post(client, h, "notes.txt", PNG, "text/plain").status_code == 415            # binary wearing a .txt name


def test_real_pdf_and_png_are_still_accepted(client):
    h = login(client)
    pdf = pdf_bytes(lambda p, m: p.insert_text((60, 90), "Open Finora Save.", fontsize=14))
    assert post(client, h, "ok.pdf", pdf, "application/pdf").status_code == 200
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (20, 33, 61)).save(buf, "PNG")
    assert post(client, h, "ok.png", buf.getvalue(), "image/png").status_code == 200


def test_very_long_text_is_refused(client, monkeypatch):
    monkeypatch.setenv("BP_MAX_TEXT_CHARS", "200")
    h = login(client)
    assert post(client, h, text="word " * 100).status_code == 413
    assert post(client, h, text="Open Finora Save in about 5 minutes.").status_code == 200


def test_new_versions_are_checked_too(client, monkeypatch):
    h = login(client)
    aid = post(client, h, text="Open Finora Save in about 5 minutes.").json()["id"]
    r = client.post(f"/api/assets/{aid}/versions", headers=h, data={"note": "x"}, files={"file": ("v.pdf", b"nope", "application/pdf")})
    assert r.status_code == 415


# ------------------------------------------------------------------ rate limiting
def test_repeated_failed_logins_are_throttled_even_for_the_right_password(client):
    for _ in range(8):
        assert client.post("/api/auth/login", json={"email": "creator@finora.example", "password": "bad"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "creator@finora.example", "password": "demo1234"})
    assert r.status_code == 429 and r.headers["retry-after"]
    # another account from the same machine is not locked out by one account's failures
    assert client.post("/api/auth/login", json={"email": "manager@finora.example", "password": "demo1234"}).status_code == 200


def test_successful_logins_never_count_against_the_limit(client):
    for _ in range(20):
        assert client.post("/api/auth/login", json={"email": "creator@finora.example", "password": "demo1234"}).status_code == 200


def test_unknown_email_and_wrong_password_look_the_same(client):
    a = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"})
    b = client.post("/api/auth/login", json={"email": "creator@finora.example", "password": "x"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_upload_rate_limit(client, monkeypatch):
    monkeypatch.setenv("BP_RATE_UPLOAD", "2/60")
    h = login(client)
    assert post(client, h, text="Open Finora Save in about 5 minutes.").status_code == 200
    assert post(client, h, text="Open Finora Save in about 5 minutes.").status_code == 200
    r = post(client, h, text="Open Finora Save in about 5 minutes.")
    assert r.status_code == 429 and r.headers["retry-after"] == "60"


def test_public_verify_is_throttled_and_never_leaks_which_codes_exist(client, monkeypatch):
    monkeypatch.setenv("BP_RATE_VERIFY", "3/60")
    codes = [client.get("/api/verify/NOPE").status_code for _ in range(5)]
    assert codes[:3] == [404, 404, 404] and codes[3:] == [429, 429]


def test_rate_limit_can_be_switched_off_for_load_tests(client, monkeypatch):
    monkeypatch.setenv("BP_RATE_LIMIT", "0")
    monkeypatch.setenv("BP_RATE_VERIFY", "1/60")
    assert [client.get("/api/verify/NOPE").status_code for _ in range(4)] == [404] * 4


def test_limiter_window_logic():
    lim = limits.Limiter()
    assert all(lim.hit("k", 3, 60) for _ in range(3)) and not lim.hit("k", 3, 60)
    assert lim.hit("other", 3, 60)
    lim.reset()
    assert lim.hit("k", 3, 60)


# ------------------------------------------------------------------ headers and secrets
def test_security_headers_and_no_store_on_api(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_production_refuses_to_start_with_a_weak_secret(monkeypatch):
    monkeypatch.setenv("BP_ENV", "production")
    monkeypatch.setenv("BP_SECRET", "change-me-before-real-use")
    with pytest.raises(RuntimeError, match="BP_SECRET"):
        limits.check_secrets()
    monkeypatch.setenv("BP_SECRET", "short")
    with pytest.raises(RuntimeError):
        limits.check_secrets()
    monkeypatch.setenv("BP_SECRET", "a" * 40)
    monkeypatch.setenv("BP_SEED", "0")
    assert limits.check_secrets() == []


def test_outside_production_a_weak_secret_only_warns(monkeypatch, caplog):
    monkeypatch.delenv("BP_ENV", raising=False)
    monkeypatch.setenv("BP_SECRET", "dev-secret-change-me")
    with caplog.at_level("WARNING", logger="brandproof.security"):
        problems = limits.check_secrets()
    assert problems and "security:" in caplog.text

def test_upload_reader_stops_at_limit_without_reading_unbounded_data():
    import asyncio
    from fastapi import HTTPException

    class Stream:
        def __init__(self):
            self.data = b"x" * 100
            self.requested = []

        async def read(self, size):
            self.requested.append(size)
            chunk, self.data = self.data[:size], self.data[size:]
            return chunk

    stream = Stream()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(limits.read_upload(stream, 32))
    assert exc.value.status_code == 413
    assert sum(stream.requested) <= 33

