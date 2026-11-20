# Demo script and shot list

Two versions: a **90-second pitch** for the video and a **5-minute walkthrough** for live judging. Every step uses seeded data (`BP_SEED=1`), so nothing needs typing except the Devanagari phrase. Names below are the real seeded assets.

## Before you record (10 minutes)

1. Start fresh so the screen shows only seeded data: delete the local `brandproof.db` (or use a new Postgres schema), then start the API with `BP_SEED=1`.
2. Log in once in each role to be sure each works. Password is `demo1234`.
3. Browser at 1280x720, zoom 100%, notifications off, one clean tab. Close the guided tour (restart it from the button if you want it).
4. Have `frontend/public/samples/Diwali_Flyer_HIDDEN_TEXT.pdf` ready for upload.
5. Do a dry run and time it. Record voice-over after the screen capture so you can match it.

## 90-second pitch (target 85 to 95 seconds)

| Time | Screen (account) | Do | Say |
|---|---|---|---|
| 0:00 | Login | Show the title card or login page | "Teams now use AI to review content. But an AI reviewer can be wrong, can be attacked by the file it reads, and can't prove what it checked. BrandProof fixes that." |
| 0:10 | *Savings launch post* (creator@) | Open the asset; point at the highlighted copy | "Every finding cites a rule or a dated fact. 'Guaranteed returns' is Contradicted by fact F-12. The cashback offer is Outdated by F-19." |
| 0:25 | Same asset | Show a fix with **Re-checked** and **Intent Lock passed**; press **Accept fix** | "Every fix is re-checked and must still say what the creator meant. Nothing changes without this click." |
| 0:38 | *Brochure PDF with hidden text* > Trust Layer (manager@) | Open the Trust tab | "Hidden white text told the AI to mark this compliant. We found it, did not obey it, and the raw and cleaned reviews disagree, so a manipulation flag is raised." |
| 0:52 | Proof Pack for an approved asset | Scroll to **Not checked** | "Every approval ends in a Proof Pack: what was checked, what was not, who approved, which AI saw what." |
| 1:02 | `/verify/CODE` (no login) | Open the receipt link | "Anyone can verify the receipt. If a fact changes later, this page says the receipt is genuine but claims no longer match." |
| 1:10 | Rulebook Health > TONE-04 (owner@) | **Run red-team**, then **Approve tighter rule** | "An adversary attacks our own rules. It found loopholes; the owner approves a tighter rule; the re-test goes from 3 of 16 to 16 of 16 caught, with no false positives on normal copy." |
| 1:22 | `/evaluation` | Show the blind set with its misses | "And we publish our own accuracy on a blind set, misses included: 82% precision, 67% recall, with wide intervals. We checked the checker." |

If you run over, cut the verify page (1:02) first, then the Accept click.

## 5-minute live walkthrough

Use the numbered steps in the README section *90-second demo*, then add: **Claim Ledger** evidence view and **Request a fact** (creator, then owner under Governance > Fact requests); **Stale approvals** page after editing a fact; **Trust scoreboard** (`/trust`, 23 of 25 attacks, two declared gaps); the **CLI** (`python cli.py check ...`, show exit code 1 on the hidden-text PDF); **Confidential mode** toggle on the Disclosure page; **Audit log > Verify chain**.

## Questions judges are likely to ask, with true answers

| Question | Answer |
|---|---|
| "Is the AI doing the review?" | Deterministic checks run first. The AI only adds claims, tone and Intent Lock when a key is set, and every output is validated in code. Without a key the app says so (badge **Heuristic**). |
| "Your seeded set is 100%." | It was written with the engine, so it proves regression safety only. The blind set (82% / 67%) is the honest number, and its misses are unfixed on purpose. |
| "Is the receipt cryptographically secure?" | It is an HMAC with the server's secret plus a hash-chained audit anchor. It proves this server issued it and the log still holds it. It is not a public-key signature; that is on the roadmap. |
| "What does it miss?" | `LIMITATIONS_AND_ROADMAP.md`: paraphrased injections, look-alike-only words, subtle tone offline, several claim phrasings. |
| "Who built what?" | `docs/CONTRIBUTIONS.md` and the Git history. Each member should be able to demo their own area. |

Do not claim: user-test results you have not collected; accuracy with an LLM key unless you have measured it; legal compliance (the ASCI-style pack is illustrative, not legal advice).
