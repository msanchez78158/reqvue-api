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
  `https://reqvue-api-production.up.railway.app`. Deploy with `railway up`
  from repo root (not a git repo; Railway CLI may need
  `export PATH="$HOME/.hermes/node/bin:$PATH"`).
- Verify a deploy against real extraction output (`Testing/*.PDF` through
  `/parse`), not just `/health` — "it builds" has been misleading before.

## Testing

- Real RFQ samples live in `Testing/`. `SPE8E426T1829.PDF` (DLA titanium sheet,
  20 pp) is the regression baseline; probe strings listed in `REQVUE_STATUS.md`.
- Local venv: `.venv/bin/python`; run scripts from repo root so imports resolve.

# Project Rules & Agentic Delegation Policy

##  Subagent Delegation Architecture
You operate as the primary 'architect' session. You MUST NOT execute routine file mapping, boilerplate coding, or security sweeps yourself. You must use the built-in subagent tool to delegate these tasks to specialized workers to save token efficiency and context window bloat.

###  The Worker Directory
- **runner** (`~/.claude/agents/runner.md`): Low-effort scout bot (Haiku).
- **coder** (`~/.claude/agents/coder.md`): Medium-effort implementation bot (Sonnet).
- **reviewer** (`~/.claude/agents/reviewer.md`): Medium-effort sign-off bot (Fable).

---

##  Step-by-Step Subagent Trigger Rules

### Rule 1: Before Planning Anything (Recon Stage)
- **TRIGGER**: Whenever the user asks to modify a feature, investigate a bug, or inspect the environment.
- **ACTION**: Do not use your own tools to scan files. Instantly invoke the `runner` subagent.
- **INSTRUCTION**: Ask `runner` to map out the relevant directory, grep for references, or run tests to gather baseline details. 

### Rule 2: Before Implementation (Feature Writing Stage)
- **TRIGGER**: Once a task plan is solidified and code needs to be generated or updated.
- **ACTION**: Do not write the code. Invoke the `coder` subagent.
- **INSTRUCTION**: Provide `coder` with the precise files, the design specifications, and ask it to write out the features or boilerplate.

### Rule 3: Before Committing Code (Security & Senior Pass Stage)
- **TRIGGER**: As soon as `coder` finishes modifying files and updates the codebase.
- **ACTION**: Do not accept the raw code immediately. Invoke the `reviewer` subagent.
- **INSTRUCTION**: Command `reviewer` to scan the newly modified files specifically checking for logical flaws, credential leaks, and structure consistency.

---

##  Hard Restrictions (The Negatives)
- **NEVER** write feature code in the main `architect` context. Keep your main session strictly for high-level technical blueprints and delegation.
- **NEVER** skip the `reviewer` step for any changes touching routing, database models, configuration, or authentication modules.
- **NEVER** run heavy grep or search commands directly. Use `runner` for directory discovery.

