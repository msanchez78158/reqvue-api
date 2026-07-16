# ReqVue

FastAPI service that extracts a structured 16-field RFQ brief from procurement
documents (PDF/text) for manufacturing estimators deciding whether to quote.

**Current state / history / known limitations: see `REQVUE_STATUS.md` — that file
is the source of truth for what works, what's broken, and what was last tested.
Update it whenever extraction behavior or deployment state changes.**

## Architecture

- `main.py` — FastAPI app. `POST /parse` (production path) accepts a multipart
  file upload or JSON `{"text": ...}`, runs extraction in a background task,
  results polled via `GET /status/{job_id}`. Jobs live in an in-memory dict
  (lost on restart, single instance only).
- PDF → markdown via **pymupdf4llm** (PyMuPDF). No OCR — scanned PDFs yield
  near-empty text. (Replaced docling, which caused 20+ failed Railway deploys.)
- `trimmer.py` — `smart_trim` caps input at 18,000 chars: keeps beginning/end,
  scores 900-char middle chunks by spec-signal and risk-keyword density
  (regexes for NSN/dimensions/spec standards + tiered keywords). Heuristic —
  vocabulary gaps cause real field losses (see status file, MODOT test).
- `extractor.py` — single LLM call to **DeepSeek (deepseek/deepseek-v4-flash)
  via OpenRouter** (`OPENROUTER_API_KEY`), temperature 0, `max_tokens=6000`
  (reasoning tokens count toward the cap — do not lower it), prompt demands a
  bare JSON object, validated into `models.RFQBrief` (pydantic).
- `models.py` — `RFQBrief` (16 optional fields) and `RFQBriefV2` (adds
  confidence/classification fields, used only by v2).

## Constraints

- **Do not touch `extractor_agent.py`, the `agno` dependency, or `/parse/v2`
  without explicit instruction.** v2 is code-complete but intentionally
  disabled in production (`agno` deliberately absent from `requirements.txt`;
  the endpoint fails gracefully). Decision on shipping vs. deleting it is open.
- Do not reintroduce docling or other heavy ML dependency chains — that is
  what broke Railway deploys originally.
- `Testing/`, `.venv/`, `.env` are excluded from the Docker build context via
  `.dockerignore`/`.railwayignore`; keep it that way.

## Deployment

- Railway project **ReqVue**, service **ReqVue-api**,
  `https://reqvue-api-production.up.railway.app`. Deploy ONLY with
  `railway up` from repo root (Railway CLI may need
  `export PATH="$HOME/.hermes/node/bin:$PATH"`).
- **Do not push to or deploy from the linked GitHub repo
  (`msanchez78158/reqvue-api`) — it is stale and public**; a repo-triggered
  build would regress production to the pre-2026-07-02 extractor. See
  `REQVUE_STATUS.md` (2026-07-16 entry) until the link is removed or the repo
  is synced.
- Verify a deploy against real extraction output, not just `/health` —
  "it builds" has been misleading before. Standard check:
  `.venv/bin/python verify_deploy.py` (both baseline PDFs through the
  deployed `/parse`, asserts bid-critical fields, exits nonzero on failure).

## Testing

- Real RFQ samples live in `Testing/`. `SPE8E426T1829.PDF` (DLA titanium sheet,
  20 pp) is the regression baseline; probe strings listed in `REQVUE_STATUS.md`.
- Local venv: `.venv/bin/python`; run scripts from repo root so imports resolve.

# Project Rules & Agentic Delegation Policy

## Subagent Delegation Architecture
The main session operates as the architect: it plans, delegates, and verifies.
Delegate routine file mapping, boilerplate coding, and review sweeps to the
project subagents to keep the main context focused on design decisions.

### The Worker Directory (project agents, `.claude/agents/`)
- **runner** (`.claude/agents/runner.md`): fast scout (Haiku, low effort) —
  directory mapping, grep sweeps, running the trimmer probes and
  `verify_deploy.py`. Read/run only, never edits.
- **coder** (`.claude/agents/coder.md`): implementation (Sonnet, medium
  effort) — writes features and fixes from a blueprint; must prove changes run
  locally before reporting done.
- **reviewer** (`.claude/agents/reviewer.md`): sign-off (Fable, medium
  effort) — security and quality pass; ends with APPROVED or REJECTED plus
  mandatory fixes.

## Delegation Rules

### Rule 1 — Recon before planning
For feature changes, bug investigations, or environment inspection that spans
more than a couple of known files, send `runner` to map the relevant code,
grep for references, and run baseline tests. Trivial lookups in a file already
in context don't need a subagent.

### Rule 2 — Coder implements
Once the plan is solid, hand `coder` the precise files, the design spec, and
the constraints (see Constraints section above — they bind subagents too).
Multi-file or novel code goes to `coder`; a one-line fix the architect can see
end-to-end may be applied directly.

### Rule 3 — Reviewer before commit
After `coder` finishes, `reviewer` scans the modified files for logical flaws,
credential leaks, and consistency before anything is committed or deployed.
**Never skip `reviewer` for changes touching the API surface (`main.py`
routes), the extraction pipeline (`trimmer.py`, `extractor.py`, `models.py`),
`Dockerfile`, or `requirements.txt`.** A REJECTED verdict goes back to `coder`
with the fix list.

### Always
- Extraction-path changes are verified with the trimmer probes locally and
  `verify_deploy.py` against the deployed API after `railway up` — regardless
  of which agent wrote the code.
- Keep heavy multi-file searches out of the main context — that is `runner`'s
  job.

