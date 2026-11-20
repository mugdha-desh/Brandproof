# Round 3 progress log

Updated after every step. Each row says what changed and where it can be checked.

## Step 1: I1 Claim Ledger + Intent Lock (complete)

| Change | Where to verify |
|---|---|
| **Structured intent.** At the first review the creator's intent plus the original copy become a short list of must-keep elements (subject, audience, call to action). Stored on the asset, not re-derived on later versions. | `backend/app/engine/intent.py`, `tests/test_intent_lock.py` |
| **Intent Lock v2.** Every suggested fix is checked element by element. A fix that removes a call to action (or any element that was in the copy) is withheld, with the lost element named. Pressure phrases ("act now") never count as the creator's CTA, so removing them is allowed. | `engine/review.py` (`intent_lock`, `verify_fix`), Findings tab chips |
| **AI elements are validated in code.** With an LLM key the model proposes elements, but each must quote text that exists in the copy; invented, unknown-kind or pressure-phrase elements are dropped. A bad reply falls back to code. | `tests/test_intent_lock.py::test_ai_elements_must_quote_real_text` |
| **Evidence view per claim.** Claim and approved fact side by side with source, owner, validity dates and a freshness chip (in date / N days left / expired). | Claim Ledger tab, `service.fact_evidence` |
| **Request a fact.** Unsupported and Needs-human claims get a "Request a fact from the owner" action. The guideline owner answers from Governance > Fact requests: approve as a new dated fact (re-run turns the claim Supported) or decline with a reason. Both are audit-logged and listed in the Proof Pack. | `tests/test_fact_requests.py`, Governance > Fact requests |
| **Safe upgrade of an existing database.** New `assets.intent_elements` column is added automatically on start (idempotent), so the deployed Postgres keeps its data. New table `fact_requests` is created by `create_all`. | `db.migrate`, `tests/test_fact_requests.py::test_existing_database_gets_the_new_column` |

Numbers after this step: 107 backend tests (was 92), smoke test 27/27 (was 23), eval report unchanged.

## Step 2: I2 Trust Layer + Proof Pack (complete)

| Change | Where to verify |
|---|---|
| **Wider hidden-content detection in PDFs.** Text covered by a later image, hidden or off-page annotations, annotations or document properties that carry instructions, and embedded file attachments (reported as not analysed). Ordinary reviewer comments and normal metadata are not flagged. | `engine/trust.py`, `tests/test_trust_layer_v2.py` |
| **False positive removed.** White text placed on a picture was flagged as "same colour as its background", because the page was assumed white. Text drawn on top of an image now skips that test. | `test_text_drawn_on_top_of_an_image_is_not_hidden` |
| **Look-alike letters (new rule TRUST-04).** Cyrillic or Greek letters inside Latin words are folded to Latin before review (so a hidden "guаranteed" is still judged as a false claim) and flagged. Genuine Russian, Greek and Hindi/Hinglish text is left alone. Existing databases receive the rule on startup. | `fold_lookalikes`, `seed.ensure_core_rules` |
| **More injection encodings.** Spaced-out letters, base64-encoded instructions, Hinglish and Hindi phrasings, and hidden HTML elements in text submissions. | `scan_injection`, `_HIDDEN_HTML` |
| **Local OCR.** Text inside images and inside PDF pictures is read by Tesseract on the server, so image text is reviewed even without an LLM key. Nothing is sent out. The "not checked" list says exactly what OCR did and did not cover. | `trust.local_ocr`, `review.not_checked` |
| **Signed Proof Pack receipts.** Issued on approval: a public-safe snapshot (no copy, claim text, comments or emails), SHA-256 digest, HMAC signature and an anchor in the audit log. | `receipts.py`, `tests/test_receipts.py` |
| **Public verify page** (`/verify/CODE`, no login). Checks signature, digest, audit anchor and chain, shows whether the asset changed since approval, and compares a file's SHA-256 (hashed in the browser, never uploaded). | `routers/verify.py`, `app/verify` |
| **Proof Pack PDF export.** Full pack with receipt code, digest and verify link; an unapproved asset gets a PDF that says it has no receipt. Assets approved before this feature get a receipt on first export. | `GET /api/assets/{id}/proofpack.pdf` |
| **Trust Layer test suite and scoreboard** (`/trust`). 25 attack files and 8 clean controls generated in code and scored live. Two known gaps are included and reported as misses with a reason. | `engine/trust_suite.py`, `tests/test_trust_suite.py` |

Numbers after this step: 137 backend tests (was 107), smoke test 31/31 (was 27). Trust suite: 23 of 25 attacks caught, 2 declared gaps, 8 of 8 controls clean. Eval report unchanged.

### Limits we state openly
- **Receipts are signed with the server's secret.** Verification therefore proves the receipt is the one this server issued and that the audit log still contains it; it is not a public-key signature a third party could check offline. Signed provenance (C2PA) stays on the roadmap.
- **Paraphrased instructions** (suite case G01) and **words made only of look-alike letters** (G02) are not caught by pattern matching. The verifier and the human reviewer are the backstop.
- **OCR** is Tesseract: it can miss small, stylised or low-contrast text, and reads up to 4 pictures per PDF.
- Deploy note: rebuild the API image (Tesseract and a font are installed in the Dockerfile) and set `BP_PUBLIC_URL`.

## Step 3: I3 Rulebook Red-Team (complete)

| Change | Where to verify |
|---|---|
| **Hinglish transliteration matching.** A rule's `translit_phrases` match on a sound skeleton, so 'pakka munafa' also catches 'pakkaa munaafa', 'paka munapha' and the Devanagari 'पक्का मुनाफा'. Phrases whose skeleton is too short are refused, so ordinary Hinglish words are not flagged. Works in real reviews, not only in the red-team. | `engine/translit.py`, `rules.phrase_matches`, `tests/test_redteam_v2.py` (first 3 tests) |
| **Train / hold-out split.** A proposal is written only from train variants. Hold-out variants (including paraphrases, misspellings and Devanagari) are never used for that. Catching them after approval shows the rule generalised; the ones still missed are listed as **open loopholes** for a human rewrite. | `redteam.HOLDOUT`, `redteam.retest`, Rulebook Health |
| **False-positive guard.** Every proposal is checked against a fixed corpus of normal copy (including everyday Hinglish) plus compliant sentences the AI writes when a key is set. Phrases that would flag normal copy are dropped; if the change still flags normal copy, it is **blocked**, and approval is refused by the API (checked again at approval time). Only newly introduced false positives count. | `redteam.guarded`, `routers/redteam.decide`, tests `test_guard_*`, `test_blocked_proposal_*` |
| **Stale-proposal protection.** A proposal made against v1 cannot be approved after the rule has moved on to v2. | `test_blocked_proposal_cannot_be_approved_and_stale_one_cannot_either` |
| **Fresh AI adversary.** Each run tells the AI which variants earlier runs already tried and asks for new ones. Output is validated in code (text must exist, core phrase must appear in the text); half the variants are train, half hold-out. | `redteam.llm_variants`, `test_ai_variants_are_validated_split_and_exclude_known` |
| **Ambiguity score.** Weighted mean of three signals: override rate (0.4), reviewer split (0.3, 4p(1-p)) and AI self-disagreement (0.3, from repeated AI runs with the cache bypassed). Diagnosis: *unclear* (people or AI disagree), *ignored* (consistently overridden), *healthy*, *not enough data* (under 3 decisions and no probe). Each flag shows its reasons. | `engine/ambiguity.py`, `service.insights`, `POST /api/redteam/ambiguity-probe` |
| **Rulebook Health screen.** Diagnosis chip with reasons and score, probe button, train and hold-out counts, version history (v1 3/16 -> v2 16/16), generalisation line in each loophole report, blocked-proposal warning. | `frontend/app/rulebook/page.tsx` |
| **Eval report updated.** Red-team table now has hold-out columns and lists the open loopholes; the held-out probe (with its misses) is now printed in the report; limitation notes brought up to date. | `docs/EVAL_REPORT.md`, `eval/run_eval.py` |

Numbers after this step: 164 backend tests (was 137), smoke test 35/35 (was 31), TypeScript type-check clean.
Hold-out generalisation (offline, no LLM): TERM-01 0 -> 3 of 5, TONE-04 1 -> 3 of 4, MSG-07 3 -> 4 of 4, ASCI-02 0 -> 2 of 4.

### Limits we state openly
- **Paraphrases and misspellings stay open on purpose** ('Your money can never go down', 'Gaurenteed returns', '6.5 pct'). Matching them by code would flag normal copy; they need the AI judge or a human rewrite of the rule. The loophole report says so instead of claiming 100%.
- **Hinglish matching is spelling-tolerance, not understanding.** It covers Latin spelling variants and Devanagari for phrases the owner chose, and nothing else (no other Indian languages, no meaning).
- **The hold-out set is small and written by the team**, so it is a generalisation check, not independent accuracy. A blind set generated after the freeze is still planned for the evaluation step.
- **The AI-disagreement probe needs an LLM key and was tested here only with mocked model replies.** Without a key the endpoint says so (409) and the score uses the two human signals only. It covers the three AI-judged rules (TONE-01, TONE-02, TONE-03) on five built-in borderline texts each.
- **The false-positive guard is only as good as its normal-copy corpus** (about 20 sentences plus 6 AI-written ones when a key is set).
- Existing databases pick up the new `rule_probes` table automatically (`create_all`); no column changes.
- The frontend build (`next build`) could not be run in the sandbox because it cannot download Google Fonts; `tsc --noEmit` passes. Please run `npm run build` once on your machine before submitting.



## Step 4: Evaluation honesty (complete)

| Change | Where to verify |
|---|---|
| **Blind set v1 (34 items).** Written in one pass after the engine and held-out probe were frozen. Labels follow what a human reviewer would flag, not what the engine flags. The engine was **not** changed after seeing the results. | `backend/eval/blind_set.py`, `docs/EVAL_REPORT.md` |
| **95% Wilson confidence intervals** on precision, recall, attack catch rate, claim accuracy and clean controls, for every set. Small samples show wide intervals on purpose. | `eval/run_eval.py::wilson`, `tests/test_eval_results.py` |
| **In-app Evaluation page** (`/evaluation`) showing blind, held-out and seeded sets, with misses and false positives listed. | `frontend/app/evaluation/page.tsx`, `GET /api/eval` |
| **Test that the blind set keeps its misses**, so nobody quietly tunes it to 100%. | `test_eval_endpoint_needs_login_and_reports_blind_misses` |

Numbers after this step: 166 backend tests (was 164), TypeScript type-check clean.
Blind set, offline mode: precision 82% (95% CI 62% to 93%), recall 67% (48% to 81%), attacks caught 5/5 (CI 57% to 100%), clean controls 7/8.

### What the blind set showed (limits stated openly)
- **Tone is the weak spot offline.** B10 to B13 (Hinglish pressure phrase, "careless", "losing everything", "is a joke") were missed because tone rules TONE-01 to TONE-03 are AI-judged and this run has no LLM. The number is the offline floor, not the product with a key.
- **Claim phrasing gaps:** "under a minute" (B3), "regulated by SEBI" (B5), "ended last month, but you can still get it" (B7), "Pakka munafa" (B14) and a phone number with spaces and a +91 prefix (B19) were missed.
- **False positives:** B1 ("risk free") also hit TERM-01, B7 hit MSG-07, B23 (white text) also raised CLAIM-01, and B29 raised ASCI-02 on a sentence with no rate. B1 and B23 are arguably legitimate co-triggers; B29 is a real false positive.
- **Claim accuracy** is based on only 2 labelled claims, so it is reported but not meaningful.
- These are listed, not fixed, so the blind set stays blind. Fixes belong in the next step, tracked against the held-out probe, never this file.


## Step 5: Stale-approval alerts, pre-publish CLI, confidential mode (complete)

| Change | Where to verify |
|---|---|
| **Stale-approval alerts.** When a fact is added, changed or deleted, when the server starts, or on a manual scan, every Approved asset is re-judged against the current Fact Vault. A claim that is now Contradicted or Outdated (and was not at approval) raises an alert. Local and deterministic: no AI call. Nothing is changed automatically; the asset stays Approved. | `backend/app/stale.py`, `tests/test_stale_cli_confidential.py` |
| **Alert handling.** Manager, reviewer or owner can list, scan and dismiss (a reason of at least a few words is required and logged). A new version resolves the open alerts. All steps are audit-logged. | `routers/stale.py`, `/stale` page |
| **Receipt stays honest.** The Proof Pack lists stale alerts. The public verify page shows a red notice ("this receipt is genuine, but N claim(s) no longer match the current facts") with a count only, never the claim text. The signed receipt itself is unchanged. | `receipts.verify`, `app/verify/[code]/page.tsx` |
| **`brandproof check` CLI.** Uploads a file, prints findings, writes the Proof Pack as JSON, and returns an exit code: 0 pass, 1 gate failed, 2 could not run. `--fail-on low|medium|high`; a manipulation flag always fails. It never approves anything. | `backend/cli.py`, `docs/CLI.md`, `.github/workflows/brandproof-gate.example.yml` |
| **Confidential mode.** One owner toggle blocks every external AI call at the gateway, whatever provider is configured. Disclosure page, Proof Pack (`confidential_mode`) and audit log show it. The offline engine keeps working. | `llm/adapter.py::Gateway`, Disclosure page |

Numbers after this step: 180 backend tests (was 166), TypeScript type-check clean.

### Limits we state openly
- **Stale alerts only re-check claims.** Tone, terminology and visuals do not depend on the Fact Vault. The scan also needs the asset's text: purged assets (retention on) and image-only files with no OCR text are skipped.
- **The scan runs at fact edits, at server start and on demand.** A deployment that stays up for weeks will not notice a date passing until someone scans or the server restarts. A scheduled call to `POST /api/stale/scan` (a daily cron) closes that gap; it is not built in.
- **There is no "Published" state**, so "approved but unpublished" is not distinguished. Every Approved asset is checked.
- **Confidential mode is a block, not a local model.** Reviews fall back to the labelled heuristic, so tone checks that need an AI model are weaker (see the blind-set numbers). The original idea of a local model stays on the roadmap.
- **The CLI uses the same login as the web app.** Use a dedicated creator account or `BRANDPROOF_TOKEN` in CI, and keep the password in a secret store.
- The `brandproof check` gate is advisory for a pipeline; it does not stop a person publishing by hand.


## Step 6: Hardening and polish (complete)

| Change | Where to verify |
|---|---|
| **Upload limits.** 10 MB per file, five allowed types, content sniffing (a fake `.pdf`, an image named `.pdf`, or binary named `.txt` is refused), 100,000-character text cap, and oversized requests are stopped before they are read. Applies to new submissions, new versions and the CLI. | `app/limits.py`, `tests/test_hardening.py` |
| **Rate limiting.** Failed-login throttle (per IP+email and per IP), upload and public-verify limits, `429` with `Retry-After`. Login no longer reveals whether an email exists. | `limits.throttle`, `routers/auth.py` |
| **Secret handling.** `BP_ENV=production` refuses a weak or default `BP_SECRET`; warnings elsewhere. `render.yaml` sets it. | `limits.check_secrets` |
| **Security headers** on every response; `no-store` on the API. | `limits.install` |
| **UX.** Friendly error, not-found and loading pages; the submission form checks file type and size before uploading, with the same limits as the server. | `app/error.tsx`, `app/not-found.tsx`, `app/loading.tsx`, `app/new/page.tsx` |
| **Accessibility fixes from a static lint (jsx-a11y).** Highlighted text in the document viewer was a `<mark>` acting as a button; it is now a real button (works with Space and Enter). Finding cards also select on keyboard focus. | `app/assets/[id]/page.tsx` |
| **Security notes** with every limit and every limit of the limits. | `docs/SECURITY.md` |

Numbers after this step: 197 backend tests (was 180), live smoke test 42/42 (was 35), TypeScript type-check clean, jsx-a11y lint clean on all pages and components.

### Limits we state openly
- **No live accessibility audit was run.** The sandbox has no browser, so contrast, focus order and screen-reader behaviour were not tested with axe or a screen reader. The jsx-a11y lint only catches markup problems. Please run axe (browser extension) on Dashboard, New submission, Asset, Rulebook, Evaluation and Verify before submitting, and keep the results.
- **Mobile layout was not re-checked** in this step.
- **Rate limits are per process and in memory**, and the client IP trusts `X-Forwarded-For` (see `docs/SECURITY.md`).
- **No penetration test or antivirus scan.**
- The Playwright flow in `e2e/ui_flow.py` was not re-run (no browser here); run it once after deploying.


## Step 7: Submission package (complete)

| Change | Where to verify |
|---|---|
| **Final report** with measured numbers (seeded, held-out, blind, Trust suite), responsible-AI summary, deviations and a judge's reading order. | `docs/FINAL_REPORT.md` |
| **Limitations and roadmap** in one table, including every blind-set miss and what was not tested. | `docs/LIMITATIONS_AND_ROADMAP.md` |
| **Demo script**: 90-second shot list with timings, 5-minute walkthrough, likely judge questions with true answers. | `docs/DEMO_SCRIPT.md` |
| **Pre-submission checklist** of what only the team can do (build, deploy, axe, user sessions, video, window rules). | `docs/PRE_SUBMISSION_CHECKLIST.md` |
| **Stale docs brought up to date**: README, TEST_REPORT (197 tests, 42/42 smoke), ARCHITECTURE (Round 3 map, hidden-text coverage), AI_DISCLOSURE (Tesseract), SCOPE_LOCK (Round 3 final scope and deviations), USER_TESTING (results template). | each file |

Re-verified in this step: 197 backend tests pass, smoke test 42/42, `tsc --noEmit` clean, eval report regenerates unchanged.

### Not done (cannot be done here)
User-testing sessions, demo video, deployment, `npm run build`, axe audit, Docker build, Playwright re-run, any live LLM measurement.


## Step 8: Merge of the parallel "Round3_Complete" branch (complete)

A second zip (`BrandProof_Round3_Complete`) turned out to be an earlier branch: it lacks steps 1 to 7 (receipts, stale alerts, CLI, confidential mode, trust scoreboard, blind set, intent elements). We kept this project as the base and ported only what was genuinely better, each with tests.

| Ported | Why | Where to verify |
|---|---|---|
| **Future-dated facts become Needs human.** A fact whose `valid_from` is after today can no longer mark a claim Supported. | Real bug: not-yet-valid facts were treated as current. | `engine/claims.py`, `tests/test_round3_finish.py` |
| **`!!` counts as two exclamation marks.** | Real bug: a run of marks was counted as one. Fixed held-out miss HO9 (recall 81% to 88%). The blind set did not change. | `engine/rules.py::eval_exclaim` |
| **Comments cannot point at another asset's finding.** | Cross-asset leak. | `routers/assets.py` |
| **PDF page cap (100) and image cap (40 megapixels)**, corrupt files refused with 415; **guideline file 5 MB; logo 2 MB, must be PNG/JPEG**. | Small files that explode when opened; unvalidated owner uploads. | `limits.py`, `routers/governance.py` |
| **Fact snapshot per review run.** The facts a run cited are stored with it. The Claim Ledger shows them as they were, flags *edited* or *deleted since this review*, and labels older runs as "current fact, not a historical record". | Without it, editing a fact silently rewrote the evidence behind an old verdict. | `ReviewRun.fact_snapshot`, `service.fact_evidence`, Claim Ledger |
| **Longer default dev secret** (no weak-key warnings); production check still refuses it. | Test output was full of HS256 warnings. | `config.py`, `limits.check_secrets` |
| **`WINDOWS_SETUP.md`**, adapted to this project. | Team develops on Windows 11. | repo root |

**Tour:** added a clear **End tour** button (it was a small "Skip tour" link), **Esc** to end, a progress bar, a sixth chapter **Proof** (Stale approvals, Trust Layer tests, Evaluation), and a note about receipts and PDF on the Proof Pack step. New `scripts/check_tour.py` statically checks all 44 steps.

**Deliberately not taken from that branch:** blocking red-team approval whenever any variant is still missed (it conflicts with our open-loophole reporting); its per-review SHA-256 digest (we already sign receipts and anchor them in the audit log); its extra pressure-phrase lists (they were tuned on the probe, and we do not tune on the blind set); its older docs and test counts.

Numbers after this step: 208 backend tests (was 197), smoke test 42/42, TypeScript type-check clean, tour check passed. Held-out probe now 88% / 88% (partly tuned, stated in the report). Blind set unchanged: precision 82%, recall 67%.

### Not done (cannot be done here)
The tour was not clicked through in a browser (none available). `npm run build`, Docker, axe and user sessions are still on the checklist.


## Step 9: UI redesign, dark mode and Help (complete)

| Change | Where to verify |
|---|---|
| **Dark and light themes.** Colours are CSS variables, so every page follows the toggle. Follows the system setting on first visit, no flash on load, printing is always light. | `tailwind.config.js`, `app/globals.css`, `components/ThemeToggle.tsx`, `lib/theme.ts` |
| **Help and FAQ page.** Role-based quick start, "where is what", searchable FAQ, key terms, tour restart. | `app/help/page.tsx` |
| **Redesigned screens.** Login, asset review (stepper, finding cards, before/after fixes), Rulebook health (rule cards with meters), Proof Pack (receipt layout, glance strip, timeline). | `app/login`, `app/assets/[id]`, `app/rulebook`, `app/assets/[id]/proof` |
| **Loading, empty and error states.** Skeleton loaders, empty states with an action. | `components/ui.tsx` |

Checked: `tsc --noEmit` clean, Tailwind compiles, tour check passes (44 steps).

### Not done (cannot be done here)
No browser was available, so none of this was viewed on screen: contrast in dark mode, the 390 px layout, and the guided tour on the redesigned pages still need a manual pass and an axe run. `npm run build` was not run.

### Step 9, part 2: Governance and Disclosure
| Change | Where to verify |
|---|---|
| **Governance.** Search boxes for rules and facts, a Fact Vault freshness strip (total, expiring in 30 days, expired), category chips, larger palette swatches, draft rules shown as a callout. | `app/governance/page.tsx` |
| **Disclosure.** A status banner, totals strip, and accessible on/off switches for Confidential mode, retention and image reading. Same settings and API as before. | `app/disclosure/page.tsx`, `components/ui.tsx` (`Switch`) |

Checked: `tsc --noEmit` clean, Tailwind compiles, tour check passes. Not viewed in a browser.


## Step 10: the three Round 2 "Round 3 improvements" completed

| Improvement named in the Round 2 submission | What was built | Where to verify |
|---|---|---|
| **1. Vision and layout compliance** | Logo check (stretched, too small, crowded clear space) by image matching; off-palette colour areas in pictures; PDF pages rendered for the logo check. Local OCR and annotation scanning were already in. | `backend/app/engine/visual.py`, rule `VIS-02`, tests in `test_round3_connectors.py` |
| **2. Fact connectors and expiry alerts** | CSV/JSON fact import with preview and audit; optional https feed; scheduler for feed pull plus stale scan; status card. | `backend/app/facts_import.py`, `schedule.py`, `components/FactImport.tsx` |
| **3. Browser extension** | Manifest V3 extension: select text, check, see verified fixes, open full review. Never approves. | `extension/` |

Backend tests: 229 passing (was 208). Evaluation numbers unchanged (52/52 seeded, 7/7 injection). Not done: Notion or Confluence connectors, Figma and Google Docs integration, extension in a web store, any browser run of the new screens or the extension.
