# User testing protocol and log (Rounds 2 and 3)

Goal: test the assumptions from the Round 1 plan with 3-5 volunteers (marketers, students running a social account, agency staff). Sessions take about 20 minutes. Use the demo data; never use real customer information.

## Setup

Open the deployed link (or `docker compose up`). Give the volunteer the **creator@finora.example** login. Ask for consent to take notes; record only first names and roles.

## Tasks (read aloud, do not help)

1. "Open *Savings launch post* and tell me what is wrong with it. How do you know?"
2. "Fix the copy so it is safe to publish. Keep the message: announce our new savings account."
3. "Imagine your manager asks why this was approved. What would you show?" (observe whether they find the Proof Pack)
4. *(Reviewer/manager volunteers)* "Open *Brochure PDF with hidden text*. Would you approve it? Why?"

## Questions after the tasks

* Which finding did you trust least? Why?
* Did any suggested fix change what you meant?
* What was missing or confusing?
* Would you use this before publishing? What would stop you?

## Measure (per session)

Time to understand the first finding; fixes accepted / edited / rejected; confusion points; whether they found the Claim Ledger, Trust tab and Proof Pack unaided; manual baseline (how long the volunteer takes to review the same post without the tool).

## Log (fill in after each session; one row per volunteer)

| # | Role (no surname) | Date | Manual baseline (min) | With BrandProof (min) | Accepted / edited / rejected | Biggest confusion | Quote | Change we made |
|---|---|---|---|---|---|---|---|---|
|   |   |   |   |   |   |   |   |   |

Assumptions under test: (1) reviewers cannot easily show why an asset was approved; (2) unsupported claims are the riskiest and least-checked items; (3) creators accept fixes that keep their intent; (4) rules often contain loopholes; (5) reviewers trust a Proof Pack more than a score.

## Results summary (fill in only from real sessions)

Do not estimate. If fewer than 3 sessions were run, write how many and say so in the final report.

| Assumption | Sessions run | What we observed (counts, not impressions) | Supported / not supported / unclear |
|---|---|---|---|
| 1. Reviewers cannot easily show why an asset was approved | | e.g. n of N found the Proof Pack unaided | |
| 2. Unsupported claims are the riskiest and least-checked | | e.g. claim-related misses in the manual baseline; ranking of issue types | |
| 3. Creators accept fixes that keep their intent | | accepted / edited / rejected totals; Intent Lock failures seen | |
| 4. Rules often contain loopholes | | from the red-team run (see `EVAL_REPORT.md`), not from testers | |
| 5. Reviewers trust a Proof Pack more than a score | | which output each tester said they would rely on in an audit, and why | |

Time comparison: median manual baseline ___ min; median with BrandProof ___ min (n = ___). Report the range too; with 3 to 5 people this is an anecdote, not a statistic.

Changes made because of testing (each linked to a commit): ___

Where we were wrong: ___
