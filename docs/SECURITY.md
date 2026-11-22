# Security and abuse limits

What is enforced in code (each row has a test in `backend/tests/test_hardening.py`).

| Area | What BrandProof does | Setting |
|---|---|---|
| File size | Upload handlers read in bounded chunks and stop once the configured limit is exceeded; a declared oversized request is also rejected early (413). Asset/version files default to 10 MB; guideline imports to 5 MB; logos to 2 MB. | `BP_MAX_UPLOAD_MB` and route-specific caps |
| File type | Only PDF, PNG, JPG, TXT, MD (415). | fixed |
| File contents | Checks the first bytes, not just the name: a `.pdf` that is not a PDF, an image wearing a `.pdf` name, or a `.txt` that is binary is refused (415). | fixed |
| Text size | Refuses pasted text over 100,000 characters (413). | `BP_MAX_TEXT_CHARS` |
| Login brute force | 8 failed logins per IP and email in 5 minutes, then 429 even with the right password. Only failures count. Unknown email and wrong password give the same answer and the same work, so response time does not reveal which emails exist. | `BP_RATE_LOGIN_FAILS` |
| Upload flooding | 30 uploads per IP per minute (429 with `Retry-After`). | `BP_RATE_UPLOAD` |
| Public verify page | 60 checks per IP per minute. | `BP_RATE_VERIFY` |
| Secrets | With `BP_ENV=production` the API refuses a default/short `BP_SECRET`, and also refuses seeded demo accounts using the public `demo1234` password. | `BP_ENV`, `BP_SECRET`, `BP_SEED`, `BP_DEMO_PASSWORD` |
| Headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a locked-down API Content-Security-Policy, and `Cache-Control: no-store` on every API response. | fixed |
| Storage paths | Storage keys reject absolute paths and `..` traversal on both disk and database-backed storage; uploaded logo names are reduced to safe filename characters. | fixed |\n| Token parsing | Malformed signed JWT subjects are rejected with 401 rather than causing an unhandled server error. | fixed |\n| Untrusted files | Uploaded files are parsed, never executed. Hidden text and instructions aimed at the AI reviewer are handled by the Trust Layer. | see Trust Layer |

## Limits we state openly
- **Rate limits live in memory, per process.** That is right for our single API container. With several instances, or after a restart, each keeps its own counters. Put a shared store (for example Redis) or an API gateway in front before scaling out.
- **The client IP comes from `X-Forwarded-For` when present.** Behind a proxy you trust, that is correct; if the API is exposed directly, a caller could fake the header and dodge the per-IP limits. Deploy behind the platform proxy (Render does this) or strip the header at the edge.
- **Tokens are 12-hour bearer tokens kept in the browser's local storage.** A cross-site scripting bug would expose them. There is no refresh or revocation list, so a stolen token works until it expires.
- **PDF and image parsers are third-party libraries (PyMuPDF, Pillow, Tesseract).** We cap sizes and check types, but a parser vulnerability would still be a risk; keep them updated and run the API as a non-root container user.
- **No malware scan.** Files are not run through an antivirus engine.
- **No penetration test has been done.** These controls were tested by our own tests only.
\n\nThe submission-hardening branch adds regression coverage for bounded upload reads, storage path traversal, malformed JWT subjects, and production demo-password enforcement. These new tests still need to be run in CI or a clean local environment before claiming they pass.\n