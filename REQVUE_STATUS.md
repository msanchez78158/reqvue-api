# ReqVue Status — 2026-07-16

## 2026-07-16 — Railway reactivated, production verified; GitHub-repo landmine found

Timeline: production was found DOWN (404 "Application not found" — account
lapsed/paused). Railway account reactivated same day; deployment `90d7e450`
came online and was verified against real extractions via the new
`verify_deploy.py` harness (jobs `8a9d596d` DLA, `f410bc99` MoDOT): all
bid-critical checks PASS — DLA NSN/material/dimensions/FOB intact, MoDOT
`quote_due_date` 07/09/2026 and `delivery_deadline` Sep 29 recovered. The
serving image is the last `railway up` snapshot (2026-07-02 local code).

**✅ RESOLVED same day — stale linked GitHub repo (was a landmine).** The
Railway service is linked to GitHub `msanchez78158/reqvue-api`, which was
stale (predated all 2026-07-02 fixes: no two-track trimmer, `max_tokens=2000`,
old non-JSON prompt) — any repo-triggered build would have silently regressed
production. Fixed by making the local folder a real git repo (root commit
`c4ecb81`) and force-pushing local `main` over GitHub `main` (commit
`6e87611`, old tip `f8e2d43` discarded — it contained nothing not superseded).
Repo confirmed PRIVATE. The push auto-triggered Railway deployment `60ada9e0`,
which was verified with `verify_deploy.py` (jobs `6417132d` DLA 14/16,
`36c9d341` MoDOT 9/16): all bid-critical checks PASS, including MoDOT
`quote_due_date`/`delivery_deadline`. **GitHub push → auto-deploy is now the
primary deploy path; keep local and GitHub `main` in sync.**

Local pipeline verification (same day, pre-reactivation): trimmer probes DLA
11/11 and MoDOT 5/5; local end-to-end on DLA 14/16 fields matching baseline.

**Demo hardening shipped 2026-07-16** (runner→coder→reviewer flow, reviewer
verdict APPROVED):
- **Upload size cap**: `_save_upload` rejects multipart uploads over 25 MB with
  HTTP 413 while streaming (partial file unlinked); `/parse` now creates the
  `JOB_STORE` entry only right before scheduling the background task, so 400/413
  can no longer orphan a "processing" job.
- **Scanned-PDF guard**: `_extract_markdown_from_file` raises a clear error when
  extracted text is under 150 chars/page (real text RFQs run ~3,650+/page;
  measured on both test PDFs). Scanned/image uploads now fail with an explicit
  "no OCR — submit a text-based PDF" message instead of silently returning 16
  nulls. Applies to v1 and v2 paths.
- **LLM retry**: `extract_rfq_brief` retries the full DeepSeek call exactly once
  on malformed JSON (`json.JSONDecodeError`) or schema mismatch (pydantic
  `ValidationError`). Timeouts are still not retried.

Reviewer's non-blocking notes (logged, not fixed): (1) `/parse/v2` still
creates its job entry before `_save_upload`, so an oversized v2 upload orphans
a "processing" job — v2 handler is under the no-touch constraint; fold into
the open ship-vs-delete decision. (2) Pre-existing: the JSON `{"text": ...}`
path has no body size cap (`request.json()` buffers arbitrarily large bodies).
(3) Pre-existing: `JOB_STORE` has no eviction — unbounded growth over the
process lifetime.

Nondeterminism observed at temperature 0 across runs (content survives the
trim; the model routes it to different fields):
- `incoterms_fob` (DLA): "FOB Origin" (07-08) vs "FOB DESTINATION (See
  Schedule); DELIVER FOB: ORIGIN" (07-16) — doc contains both strings.
- `qty_tiers` (DLA): null (07-08, correct) vs `[16]` CLIN qty again (07-16) —
  the known borderline issue.
- MoDOT `finishing_secondary`/`tolerances_stated`: populated 07-08, null 07-16
  with the same content folded into `missing_or_unclear`/`estimator_summary`.

`verify_deploy.py` (repo root) is now the standard post-deploy check:
`.venv/bin/python verify_deploy.py [base_url]` — uploads both baseline PDFs to
`/parse`, polls, asserts bid-critical substrings, exits nonzero on failure.

Persistent record of deployment/extraction state so future sessions don't depend on chat history.

## Test results log

| Document | Type / source | Date tested | Null or wrong fields | Pass/fail |
|---|---|---|---|---|
| `Testing/SPE8E426T1829.PDF` | Manufacturing RFQ — DLA titanium sheet, 20 pp, 73k chars | 2026-07-02 (job `40fe9424`) | `tolerances_stated` null (**correct** — doc states none); `target_price`, `competing_vendors` null (correct — none present); `qty_tiers=[16]` is the CLIN quantity, not a price break (borderline wrong) | **PASS** — all 5 previously-null spec fields recovered (NSN, material, dimensions, finishing, schedule); FOB corrected to Origin |
| `MODOT 0000000343SL_SUPPLIER.pdf` | Construction/services IFB — MoDOT overhead door install, 30 pp, 86k chars | 2026-07-02 (job `74360f91`) | `quote_due_date` null (**wrong** — doc states Close Date 07/09/2026 2:00 PM CT at char 5,420, cut by trimmer); `delivery_deadline` null (**wrong** — completion by 09/29/2026 at char 68,588, cut by trimmer); manufacturing fields null (correct for doc type) | **FAIL** — trimmer vocabulary gap: "Close Date"/"complete the work by" not covered by due-date/delivery keywords; the two most bid-critical schedule fields lost |
| `Testing/SPE8E426T1829.PDF` (retest, two-track trimmer) | Manufacturing RFQ — DLA | 2026-07-02 (job `a3da48ff`) | Same correct nulls as before (`tolerances_stated`, `target_price`, `competing_vendors`); `qty_tiers=[16]` still CLIN qty (borderline) | **PASS** — all spec fields intact under Track 1 routing; 11/11 trim probes |
| `MODOT 0000000343SL_SUPPLIER.pdf` (retest, two-track trimmer) | Construction/services IFB — MoDOT | 2026-07-02 (job `e3cf7c1d`) | Manufacturing fields null (correct for doc type); `incoterms_fob`/`legal_penalties` null (not found in kept text — unverified whether present in full doc) | **PASS** — `quote_due_date` (07/09/2026 2:00 PM CT) and `delivery_deadline` (09/29/2026) both recovered; scope/door dimensions now also extracted |
| `Testing/SPE8E426T1829.PDF` (re-verification) | Manufacturing RFQ — DLA titanium sheet, 20 pp, 73k chars | 2026-07-08 (job `b1452aac`) | `tolerances_stated` null (**correct**); `qty_tiers` null (improved — was `[16]` CLIN qty before, now correctly null since no price breaks exist); `target_price`/`competing_vendors` null (correct) | **PASS** — all spec fields intact: NSN 9535005962077, Ti-6Al-4V, 0.025"×36"×96", AMS4911T/4907M/2809B, MIL-STD-129/2073, FOB Origin, Need Ship 12/07/2026 |
| `MODOT 0000000343SL_SUPPLIER.pdf` (re-verification) | Construction/services IFB — MoDOT overhead door install, 30 pp, 86k chars | 2026-07-08 (job `fca8fb64`) | Manufacturing fields null (correct for doc type); `incoterms_fob`/`legal_penalties` null (confirmed not stated in doc — listed in `missing_or_unclear`) | **PASS** — `quote_due_date` (07/09/2026 2:00 PM CT) and `delivery_deadline` (Sep 29, 2026) both recovered; door dimensions, finishing/installation scope, OSHA/MWBE certs all extracted |

**RE-VERIFIED 2026-07-08** (jobs `b1452aac` DLA, `fca8fb64` MoDOT): both test
documents re-run through production `/parse` against the same deployed two-track
trimmer. Results confirm the 2026-07-02 fix is stable — DLA unchanged (Track 1,
all spec fields intact), MoDOT still recovers both previously-lost schedule fields
(quote_due_date and delivery_deadline). Minor improvement on DLA: `qty_tiers`
now correctly returns null instead of `[16]` (the CLIN quantity, not a price break).
See 16-field comparison tables below.

**RESOLVED 2026-07-02 — two-track trimmer** (deployment `9d25f390`): `smart_trim`
now dispatches on markdown structure. Track 1 (≥3 markdown headers): sections whose
header text matches relevance stems (schedule, pricing, scope, specification,
requirement, deliver*, deadline, timeline, completion, close/due date) are kept in
full (per-section cap 3,000 chars, budget 40%), then remaining budget fills with the
same density-scored chunks as before; boilerplate headers (terms/definitions/general)
and FAR/DFARS clause-citation headers score zero; header-only stub sections
(<100 chars) are skipped — a stub taken as a "section" blocked the chunk fill from
covering `Need Ship Date` on the DLA doc until this was added. Track 2 (<3 headers):
the previous density-scoring algorithm, unchanged (`_trim_density`).
Note: pymupdf4llm emits `##` headers even for form-layout docs, so **both** test
docs route to Track 1 in practice (DLA: 78 header lines, MODOT: 90); Track 2 is the
fallback for genuinely header-free extractions. Verified: DLA 11/11 probes,
MODOT 5/5 probes, Palladium no-crash, short-doc passthrough intact.

### Library evaluation: Unstructured.io (2026-07-02, not integrated)

Evaluated `unstructured[pdf]` as a structure-aware replacement for keyword trimming.
- **Install**: pip-only succeeds (no system packages needed to install), BUT pulls
  118 packages / **1.6 GB** incl. torch, transformers, opencv, spacy — docling-class
  Railway image-size/build risk even though `strategy="fast"` never uses them.
- **Runtime with `strategy="fast"`**: verified working on a machine with NO poppler,
  tesseract, or libmagic. Other strategies (`hi_res`, `ocr_only`, `auto`) DO require
  those system binaries — strategy must be pinned.
- **MODOT IFB**: structure detection excellent — `1.2 Schedule` returned as Title,
  immediately followed by `Close Date` Title + `07/09/2026 2:00 PM` Text. Would have
  fixed the failed fields. Title detection noisy (253 Titles incl. field labels).
- **DLA SPE8E426T1829**: structure detection unreliable — ALL critical spec content
  (NSN, titanium, dimensions, AMS specs, Need Ship Date) misclassified as **Footer**;
  only 9 Titles in 20 pages ("SECTION A/B"). A selector that trusts element types
  would have deleted the most important content.
- **Verdict**: does NOT structurally eliminate vocabulary matching — you still choose
  which sections to keep by matching header text; headers are just lower-entropy
  vocabulary. And form-style docs (DLA) yield no usable structure, requiring the
  density-scoring fallback anyway.
- **Zero-dependency alternative noted**: pymupdf4llm's existing markdown output
  already contains the same headings (`## **1.2 Schedule**` w/ adjacent close date) —
  header-based sectionizing is possible with no new dependencies.

## Current state

- **Railway**: deployed and verified working. Service `ReqVue-api`, project `ReqVue`,
  URL `https://reqvue-api-production.up.railway.app`. Latest verified deployment
  `5ecf212a` (2026-07-02 14:25 CDT), SUCCESS.
- **Production extraction path**: `POST /parse` (v1, `extractor.py`, single DeepSeek call
  via OpenRouter). Confirmed by traffic logs — no client has ever called `/parse/v2`.
- **`/parse/v2`** (Agno two-pass agent, `extractor_agent.py`): code-complete but
  **disabled in production** — `agno` is deliberately absent from `requirements.txt`;
  every call fails cleanly with "optional dependency 'agno' is not installed".
  v2 inherits the same `smart_trim` pre-processing as v1 (called in `main.py`), so it
  had the same trim bug and would have gained nothing here. Out of scope this session.
- **PyMuPDF migration**: complete. Zero docling code references in shipped code
  (one comment in `requirements.txt` only). Build logs confirm no docling packages install.

## What was broken

`trimmer.py` `smart_trim` cut all manufacturing-spec content from mid-document pages
before extraction ever ran. Test doc `Testing/SPE8E426T1829.PDF` (DLA titanium-sheet RFQ,
20 pages, 73,041 chars → 18,000 cap):

1. `RISK_KEYWORDS` covered only legal/commercial terms — nothing matched part numbers,
   NSNs, materials, dimensions, tolerances, or finishing (pages 7/9/10 content).
2. The old algorithm filled its budget in *keyword-list order*, so early-page legal
   boilerplate matches consumed the budget before mid-document content was reached.
   Even "FOB" content on page 9 was cut despite FOB being a keyword.

Verified pre-fix on production: all 10 spec probes (NSN 9535005962077, TITANIUM ALLOY,
0.025 IN THK, AMS4907M, 6AL-4V, MIL-STD-2073, MIL-STD-129, DELIVER FOB, Need Ship Date,
REVISION NR M) present in full text, **zero** survived the trim.

## What was fixed (3 changes, all deployed)

1. **`trimmer.py` rewritten — score-based chunk selection.**
   - Middle of document split into 900-char chunks; each scored for
     *spec density* (regex patterns weight 4: NSN format, dimensional callouts like
     "0.025 IN THK", spec standards like AMS/MIL-STD, alloy designations like 6AL-4V,
     schedule callouts; high-precision keywords weight 2; generic keywords weight 1)
     and *risk density* (legal/commercial keywords, now including QSLD/qualified
     supplier/approved source/sole source/incumbent).
   - Budgets: beginning 25%, spec chunks 35%, risk chunks 25%, ending 15%.
   - Highest-scoring chunks win; reassembled in document order.
   - Why not just add keywords: tried first; generic words ("material",
     "specification") matched 37k chars of boilerplate for a 5.4k budget and the
     doc-order fill starved the real spec block. Density scoring fixed it.
2. **`extractor.py` `max_tokens` 2000 → 6000.** deepseek-v4-flash is a reasoning
   model; hidden reasoning tokens count toward the cap. With richer trimmed input,
   responses truncated mid-JSON ("Unterminated string"). Measured: 1,985/2,000 tokens
   used for a ~600-token visible answer.
3. **`extractor.py` prompt now explicitly demands JSON.** Latent pre-existing bug:
   the prompt said "Return the following fields:" and never mentioned JSON — the
   model just happened to emit JSON until the input changed, then produced a markdown
   table ("Expecting value: line 1 column 1"). Prompt now requires a bare JSON object.

## Before/after — SPE8E426T1829.PDF via production `/parse`

| Field | Before (job 5618392a) | After (job 40fe9424) |
|---|---|---|
| rfq_id_and_org | SPE8E4-26-T-1829, DLA Troop Support | same, plus buyer |
| quote_due_date | 2026-06-29 COB | same |
| delivery_deadline | 160 days ADO only | + Need Ship Date 12/07/2026, Required Delivery 03/27/2027 |
| **part_number_rev** | **null** | NSN 9535005962077; SAE AMS4911T/AMS2809B/AMS4907M w/ revs; 6AL-4V ANNEALED |
| **material_and_grade** | **null** | Titanium alloy hot rolled, annealed, descaled; 6AL-4V (ELI) |
| **dimensions_raw** | **null** | 0.025 IN THK, 36.00 IN W, 96.00 IN LG; 14.784 LB/SH |
| **tolerances_stated** | **null** | null — CORRECT: the word "tolerance" appears 0 times in the full 73k-char doc (tolerances live in the referenced AMS spec) |
| **finishing_secondary** | **null** | MIL-STD-129 marking; MIL-STD-2073-1E packaging; palletization RP001 |
| qty_tiers | null | [16] (the CLIN quantity — arguably not a price break; borderline) |
| incoterms_fob | FOB Destination (wrong — missed page 9) | FOB Origin (correct per CLIN schedule) |
| target_price | null | null (correct — none stated) |
| legal_penalties | null | criminal penalties for substitution; FAR 52.249-8 default; false-cert penalties |
| qa_certs_required | QSLD/QSLM, dest. inspection | + QAP 13873 CDRL, Critical Application Item, DFARS cyber clauses |
| competing_vendors | null | null (correct — none named) |
| missing_or_unclear | "everything missing" | targeted clarifications (quantity ambiguity, tolerances, first-article) |
| estimator_summary | "critical details missing" | accurate quote-ready summary |

**Verdict: 4 of the 5 previously-null fields recover with correct data; the 5th
(tolerances_stated) stays null because the document genuinely states no tolerances —
verified by regex over the full extracted text.** Bonus: the before-run's
`incoterms_fob` was actually *wrong* (FOB Destination); the after-run corrects it to
FOB Origin from the page-9 CLIN schedule.

## Known remaining limitations (honest failure surface)

- **Heuristic, not semantic.** Chunk scoring is keyword/regex frequency. A probe sweep
  across chunk sizes (700–1200) passed 11/11 probes at the deployed size (900) but
  dropped one probe at some other sizes — boundary effects are real. A differently
  formatted RFQ (unusual vocabulary, non-DLA conventions, tables rendered oddly) can
  still lose spec content. Durable fix would be structure-aware selection (per-page
  scoring, or a cheap LLM relevance pass), not more keywords.
- **Scanned/image PDFs: no OCR.** pymupdf4llm extracts embedded text only. A scanned
  RFQ yields near-empty markdown → extraction returns mostly nulls. No detection or
  warning for this today.
- **Drawing-heavy packages.** Dimensions/tolerances living in CAD drawings (vector or
  raster) don't survive text extraction. tolerances_stated will be null for most
  machining RFQs where tolerances are on the drawing.
- **English-only patterns**, imperial-unit-biased dimensional regexes (IN/MM/FT).
- **`qty_tiers` semantics**: model put the CLIN quantity (16) in a field defined as
  *price-break* tiers. Prompt-level distinction may need tightening.
- **In-memory `JOB_STORE`**: job status is lost on redeploy/restart; single-instance only.
- **No retry on LLM JSON failure**: one malformed response = failed job (surfaced as
  status "failed"; client must re-submit).
- **`.env` only holds `OPENROUTER_API_KEY` locally; Railway holds its own copy** —
  rotate in both places.
- **`/parse/v2` unresolved**: decide whether to ship agno (adds heavy dependency chain —
  the same class of risk that killed the docling deploys) or delete the endpoint.

## Test artifacts

- Baseline (old trimmer) production job: `5618392a-81c9-4e7e-9411-30055d6f8689`
- Verified (new trimmer) production job: `40fe9424-6a4c-4c3b-8ef5-31d129b4c600`
- 2026-07-08 re-verification jobs: DLA `b1452aac-4668-492e-a5bf-3da1291f0025`,
  MoDOT `fca8fb64-9c51-42d2-8c8d-3679c640f604`
- Local probe harness used during the fix: run `smart_trim` over
  `Testing/SPE8E426T1829.PDF` and check the 11 probe strings listed above.

## 16-field comparison — 2026-07-08 re-verification (production `/parse`)

### DLA — `SPE8E426T1829.PDF` (job `b1452aac`, Track 1 — 78 markdown headers)

| # | Field | Value | Status |
|---|---|---|---|
| 1 | rfq_id_and_org | SPE8E4-26-T-1829 — DLA Troop Support Construction & Equipment (Metals), Buyer: Pamela Duffey | ✅ |
| 2 | quote_due_date | 2026 JUN 29 (close of business) | ✅ |
| 3 | delivery_deadline | Original Required Delivery: 03/27/2027; Need Ship: 12/07/2026; 160 days ADO | ✅ |
| 4 | part_number_rev | NSN 9535005962077; SAE AMS4911T Rev T; AMS4907M Rev M; AMS2809B Rev B; QAP 13873 | ✅ |
| 5 | material_and_grade | Titanium alloy, Ti-6Al-4V (and ELI), hot rolled, annealed, descaled | ✅ |
| 6 | dimensions_raw | 0.025 in thick, 36.00 in wide, 96.00 in long; ~14.784 lb/sheet | ✅ |
| 7 | tolerances_stated | null | ✅ correct — doc states none (tolerances in referenced AMS spec) |
| 8 | finishing_secondary | MIL-STD-129 marking; MIL-STD-2073-1E packaging; adhesive labels | ✅ |
| 9 | qty_tiers | null | ✅ improved — was `[16]` (CLIN qty, not a price break); now correctly null |
| 10 | incoterms_fob | FOB Origin | ✅ |
| 11 | target_price | null | ✅ correct — none stated |
| 12 | legal_penalties | Criminal penalties for substitution; FAR 52.249-8 default; false-cert penalties | ✅ |
| 13 | qa_certs_required | Critical Application Item; QAP 13873 CDRL; dest. inspection; DLA Tech/Quality Master List | ✅ |
| 14 | competing_vendors | null | ✅ correct — none named |
| 15 | missing_or_unclear | Tolerances, set-aside status, conflicting delivery dates, QSL applicability | ✅ targeted |
| 16 | estimator_summary | Accurate quote-ready summary (16 sheets Ti-6Al-4V, 0.025"×36"×96", 160 days ADO, FOB Origin) | ✅ |

**Verdict: 14/16 fields populated with correct data; 2 nulls are correct
(tolerances not stated, target price not stated). `qty_tiers` improved from
borderline-wrong `[16]` to correct `null`. No regressions from 2026-07-02.**

### MoDOT — `MODOT 0000000343SL_SUPPLIER.pdf` (job `fca8fb64`, Track 1 — 90 markdown headers)

| # | Field | Value | Status |
|---|---|---|---|
| 1 | rfq_id_and_org | MODOT 0000000343SL — State of Missouri, MoDOT; buyer Logan Wilbers | ✅ |
| 2 | quote_due_date | 07/09/2026 2:00 PM Central Time | ✅ **RECOVERED** (was null pre-fix) |
| 3 | delivery_deadline | September 29, 2026 (completion date); work upon Notice to Proceed | ✅ **RECOVERED** (was null pre-fix) |
| 4 | part_number_rev | null | ✅ correct — construction/services doc, no part numbers |
| 5 | material_and_grade | null | ✅ correct — door material/gauge not specified (noted in missing_or_unclear) |
| 6 | dimensions_raw | (13) 16'-0"×14'-0" ± and (1) 12'×14' ± sectional overhead doors; glass opening 24"×7" per door | ✅ |
| 7 | tolerances_stated | ± after door dimensions (no explicit tolerance values) | ⚠️ borderline — doc uses "±" without numeric tolerances |
| 8 | finishing_secondary | Disposal of removed items; side mount jack shaft operator; safety stop; springs; weather strip; 3-button control; track; light curtain (Lift Master LC36M); EMT wiring ≥10' AFF; 208V receptacles by MoDOT | ✅ |
| 9 | qty_tiers | null | ✅ correct — no price breaks |
| 10 | incoterms_fob | null | ✅ correct — not stated (listed in missing_or_unclear) |
| 11 | target_price | null | ✅ correct — none stated |
| 12 | legal_penalties | null | ✅ correct — no LD/penalty clauses (listed in missing_or_unclear) |
| 13 | qa_certs_required | OSHA 10 for all employees/subs; photo ID; M/WBE participation; SDV/E preference; business compliance; inspection hold points | ✅ |
| 14 | competing_vendors | null | ✅ correct — none named |
| 15 | missing_or_unclear | Door material/gauge, target price, FOB terms, liquidated damages, exact brand/model, tolerance values, wiring specs | ✅ comprehensive |
| 16 | estimator_summary | IFB for 14 overhead door replacements at Macon Maintenance Building; mandatory site visit by Jun 29; quotes due Jul 9; complete by Sep 29 | ✅ |

**Verdict: 11/16 fields populated; 5 nulls are correct for a construction/services
IFB. The two previously-lost bid-critical fields (quote_due_date and
delivery_deadline) are both recovered with correct data. Door dimensions,
installation scope, and OSHA/MWBE certification requirements also extracted.**
