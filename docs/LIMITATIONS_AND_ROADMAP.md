# Limitations and roadmap

## Limitations we know about

| Area | Limit | Effect |
|---|---|---|
| Evaluation | Seeded set (52) and held-out probe (16) were written by the team; the held-out probe is partly tuned (HO9 fixed as a bug). Blind set (34) is small; 95% intervals are wide (precision 62-93%, recall 48-81%). Only 2 labelled claims in the blind set. | Numbers show direction, not guaranteed accuracy on real content |
| AI path | Live calls to the Anthropic and Gemini APIs were tested only against mocked replies. The AI-disagreement probe likewise. | LLM-assisted accuracy is unmeasured |
| Tone | Offline tone checks use a lexicon heuristic (labelled **Heuristic**) | Subtle or new pressure wording is missed |
| Claims | Blind set misses: "under a minute", "regulated by SEBI", an expired offer phrased as "ended last month, but...", "Pakka munafa" (TERM-01), a phone number with spaces and +91 | Known phrasing gaps, left unfixed so the blind set stays blind |
| False positive | B29 raised ASCI-02 on a sentence with no rate | Real, listed |
| Trust Layer | Paraphrased instructions (case G01) and words made only of look-alike letters (G02) are not caught by patterns | Verifier and human reviewer are the backstop |
| OCR | Tesseract can miss small, stylised or low-contrast text; max 4 pictures per PDF; embedded attachments are not analysed | Listed in each Proof Pack's "not checked" |
| Receipts | HMAC with the server secret, not a public-key signature | A third party cannot verify offline |
| Red-team | Paraphrases and misspellings stay open on purpose; false-positive guard uses about 20 normal sentences (plus 6 AI-written with a key) | Five hold-out loopholes remain open and need a human rewrite |
| Language | English, Hinglish (Latin spelling and Devanagari for owner-chosen phrases) | No other Indian languages; no meaning-level matching |
| Stale alerts | Re-check claims only; run on fact edits, server start and on demand; no "Published" state; no built-in scheduler | Schedule `POST /api/stale/scan` daily |
| Confidential mode | A block, not a local model | Tone checks fall back to the heuristic |
| CLI | Advisory gate; cannot stop manual publishing | Use as a pipeline step |
| Security | Rate limits are per process and in memory; client IP trusts `X-Forwarded-For`; no penetration test or antivirus scan | See `SECURITY.md` |
| Accessibility and mobile | Only a static jsx-a11y lint was run; no axe or screen-reader test; mobile layout not re-checked in Round 3 | Team must audit before submitting |
| Scale | One organisation per deployment; no SSO; local or database file storage | Not multi-tenant |
| Not tested here | Docker image builds, `next build`, Playwright flow re-run, real deployment | Listed in `PRE_SUBMISSION_CHECKLIST.md` |
| Users | No real user-testing results are recorded yet | The five assumptions in `USER_TESTING.md` are still untested |

## Roadmap

**Next (weeks):** fix the blind-set phrasing gaps and measure them on a **new** blind set; run and publish the LLM-path evaluation; daily scheduler for stale scans; public-key (Ed25519) receipts; Redis-backed rate limits; accessibility and mobile audit results.

**Then (months):** browser extension and add-ons for Google Docs, Canva and CMS or social schedulers with a pre-publish gate; more Indian languages and code-mixed text; DAM and design-tool connectors; a "Published" state so stale alerts can focus on live content.

**Later:** video and audio review; C2PA content credentials for signed provenance; more regulatory rule packs beyond the ASCI-style pack (not legal advice); SSO, multi-tenant workspaces, private or on-premise models; a precedent library of approved decisions and learning from human corrections with manager approval.


## Added late in Round 3: what they do not do
- **Logo checks** match the uploaded logo by image matching. They miss recoloured, rotated, partly hidden or very low-resolution logos, and then report nothing about that logo. Clear space is judged by how busy the surroundings are, not by what they contain. Logo placement rules (corner, exact margins) are not checked.
- **Picture colours** are estimated from the largest colour areas. Photos and gradients can be misjudged, so these findings are marked as estimates.
- **Fact feed** supports CSV and JSON over https only. There are no Notion, Confluence or product-API connectors, and no two-way sync. Rows with matching rules from a feed are rejected on purpose.
- **Scheduler** is a single in-process timer. With several instances, run it on one. Missed runs while the server is down are caught by the startup check.
- **Browser extension** works on ordinary web text only. Google Docs and Figma draw text on a canvas, so the selection cannot be read there. Not tested on Firefox or Safari and not published to a web store. The token lives in browser session storage.
