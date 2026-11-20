# UI manual check (light and dark mode)

About 45 minutes. Nobody has seen the redesigned screens in a browser yet, so this list is the first real look. Tick each box, note problems in the last column, and fix or list them in `LIMITATIONS_AND_ROADMAP.md`.

## 0. Setup
- [ ] `cd frontend && npm ci && npm run build` succeeds, then run the app with demo data (`BP_SEED=1`).
- [ ] Use Chrome or Edge, plus one phone (or DevTools at 390 px wide).
- [ ] Install the **axe DevTools** browser extension.
- [ ] Keep a folder for evidence: screenshots and axe exports go in `docs/screenshots/`.

## 1. Theme behaviour
- [ ] First visit in a private window follows the computer's setting (try both).
- [ ] The sun/moon button works on the sign-in page, in the sidebar, and in the phone top bar.
- [ ] The choice survives a refresh and a new tab, with no white flash on load.
- [ ] Print preview (Ctrl+P) of the Proof Pack is light, even in dark mode.

## 2. Page by page (tick light and dark separately)

| Page | Light | Dark | Look for |
|---|---|---|---|
| Sign in | [ ] | [ ] | Demo buttons readable, Show/Hide password works, error message visible |
| Dashboard | [ ] | [ ] | Status cards, table text, empty state, skeleton while loading |
| New submission | [ ] | [ ] | The navy "What happens next" box is readable, file errors are clear |
| Asset review | [ ] | [ ] | Red, amber and grey highlights readable, selected highlight has a ring, Before/After boxes |
| Claim Ledger tab | [ ] | [ ] | Verdict badges, fact references, Request a fact |
| Proof Pack | [ ] | [ ] | Seal, glance strip, receipt code, Copy code, amber NOT checked block, timeline |
| Rulebook health | [ ] | [ ] | Meters have visible fill, diagnosis badges, Run red-team result and Before/After bars |
| Guidelines and facts | [ ] | [ ] | Search boxes, freshness strip, Edit dialogs, palette swatches |
| AI disclosure | [ ] | [ ] | Banner colour matches the mode, switches show on/off clearly |
| Help and FAQ | [ ] | [ ] | Search, FAQ open/close, role quick start |
| Verify a receipt | [ ] | [ ] | Valid and stale-notice states readable |
| Stale, Trust, Evaluation, Audit | [ ] | [ ] | Tables and badges readable (no layout redesign here) |

Common dark-mode faults: text that is almost the same colour as its background, badges with light text on a light fill, a white box left in a dark page, borders that vanish.

## 3. Phone (390 px wide)
- [ ] No sideways scrolling on Dashboard, Asset, Rulebook, Proof Pack, Help.
- [ ] Menu, Help and theme buttons in the top bar are all reachable.
- [ ] The Asset progress stepper still reads (labels are hidden on small screens, so check the numbers and ticks).
- [ ] Tables scroll inside their own box.

## 4. Keyboard only
- [ ] Tab through Sign in, New submission and an Asset. Focus ring is always visible.
- [ ] Highlighted text in the document opens its finding with Space and Enter.
- [ ] Switches on the Disclosure page toggle with Space.
- [ ] FAQ questions open and close with Enter.
- [ ] Esc ends the guided tour.

## 5. axe accessibility run (both themes)
Run on: Sign in, Dashboard, New submission, Asset, Proof Pack, Rulebook, Guidelines, Disclosure, Help, Verify.
- [ ] Zero "critical" and "serious" issues, or each one is listed with a reason.
- [ ] Colour-contrast issues in dark mode are fixed in `app/globals.css` (the `.dark` section).
- [ ] Exports saved to `docs/screenshots/`.

## 6. Guided tour, once per role
Sign in as each role and run the tour from the start. It should never point at nothing.
- [ ] Creator   - [ ] Manager   - [ ] Reviewer   - [ ] Owner
- [ ] Steps on Asset, Proof Pack, Rulebook, Governance and Disclosure highlight the right box in both themes.
- [ ] "Restart from the beginning" and "Start the guided tour" (Help page) both work.

## 6b. New in the last build (never run in a browser yet)
- [ ] Fact Vault: upload `fact-vault-template.csv`, Preview shows 1 to add, Apply adds it, a second Apply shows 0 changes.
- [ ] Upload a CSV with a bad date and a missing owner: rows are rejected with a reason and nothing else is blocked.
- [ ] Stale approvals page shows the Automatic checks card (last run, next run).
- [ ] Upload a logo, then submit a picture with it stretched, tiny, or crowded: a VIS-02 finding appears. A correct one raises nothing.
- [ ] Extension: load unpacked, sign in, select text on a normal page, Check, copy a suggestion, Open the full review. Confirm the owner role is refused.
- [ ] Extension popup is readable in light and dark mode.

## 7. Record the result
| Date | Who | Browser | Pages checked | Problems found | Fixed (commit) |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

Report only what was really checked. If something was not checked, say so in the final report.
