import re

RISK_KEYWORDS = [
    "liquidated damages",
    "penalty",
    "penalties",
    "late fee",
    "late fees",
    "default",
    "termination",
    "warranty",
    "indemnification",
    "liability",
    "certification",
    "certifications",
    "inspection",
    "quality",
    "QA",
    "AS9100",
    "ISO",
    "ITAR",
    "DFARS",
    "FAR",
    "export control",
    "compliance",
    "delivery",
    "deadline",
    "due date",
    "quote due",
    "FOB",
    "incoterms",
    "target price",
    "lowest price",
    "award",
    "vendor",
    "vendors",
    "qualified supplier",
    "qsld",
    "qsl",
    "approved source",
    "sole source",
    "incumbent",
]

# Manufacturing-spec signals, tiered by precision. Government/commercial RFQs
# are dominated by legal boilerplate that reuses words like "material" and
# "specification", so generic words alone cannot decide what to keep — they
# score low, while structured identifiers (NSN, dimensional callouts, spec
# numbers) score high and pull their surrounding chunk into the kept set.
SPEC_KEYWORDS_HIGH = [
    "part number",
    "part no",
    "part piece",
    "p/n",
    "nsn",
    "national stock number",
    "item description",
    "unit price",
    "tolerance",
    "heat treat",
    "plating",
    "anodiz",
    "passivat",
    "deburr",
    "temper",
    "alloy",
    "annealed",
    "thickness",
    "diameter",
    "need ship",
    "required delivery",
]

SPEC_KEYWORDS_GENERIC = [
    "material",
    "grade",
    "dimension",
    "finish",
    "coating",
    "drawing",
    "revision",
    "specification",
]

SPEC_PATTERNS = [
    # NSN: 13 digits, with or without 4-2-3-4 dash grouping (9535005962077 / 9535-00-596-2077)
    r"\b\d{4}-?\d{2}-?\d{3}-?\d{4}\b",
    # Dimensional callouts: "0.025 IN THK", "36.00 IN W", "96.00 IN LG", "1.5 MM DIA"
    r"\b\d+(?:\.\d+)?\s*(?:IN|MM|FT)\.?\s*(?:THK|W|LG|DIA|OD|ID|WD|HT)\b",
    # Decimal + unit alone: "0.025 IN", "36.00 IN"
    r"\b\d+\.\d{2,}\s*(?:IN|MM)\b",
    # Spec/standard identifiers: "AMS4907M", "SAE AMS4907", "MIL-STD-2073-1E", "ASTM B265"
    r"\b(?:AMS|ASTM|AISI|SAE|NAS|MIL-STD|MIL-DTL|MIL-PRF|MIL-C|MIL-A|MIL-T|QQ-[A-Z])\s*-?\s*\d+[A-Z0-9-]*\b",
    # Alloy/temper designations: "6AL-4V", "7075-T6"
    r"\b\d+[A-Z]{1,3}-[TOH]?\d+[A-Z]{0,2}\b",
    # Hard schedule callouts: "Need Ship Date:12/07/2026", "Required Delivery Date: ..."
    r"\b(?:ship|delivery|due)\s+date\b",
]

# Backward-compatible alias (old single flat list).
SPEC_KEYWORDS = SPEC_KEYWORDS_HIGH + SPEC_KEYWORDS_GENERIC

CHUNK_SIZE = 900
PATTERN_WEIGHT = 4
HIGH_KEYWORD_WEIGHT = 2
GENERIC_KEYWORD_WEIGHT = 1

# Budget shares of max_chars. Beginning must still fully cover a typical
# cover page (~4-5k chars at the default 18k cap).
BEGINNING_SHARE = 0.25
ENDING_SHARE = 0.15
SPEC_SHARE = 0.35
# risk gets the remainder (0.25)


def _count_hits(chunk_lower: str, keywords: list[str]) -> int:
    return sum(chunk_lower.count(keyword.lower()) for keyword in keywords)


def _spec_score(chunk: str, chunk_lower: str) -> int:
    score = PATTERN_WEIGHT * sum(
        len(re.findall(pattern, chunk, re.IGNORECASE)) for pattern in SPEC_PATTERNS
    )
    score += HIGH_KEYWORD_WEIGHT * _count_hits(chunk_lower, SPEC_KEYWORDS_HIGH)
    score += GENERIC_KEYWORD_WEIGHT * _count_hits(chunk_lower, SPEC_KEYWORDS_GENERIC)
    return score


def _risk_score(chunk_lower: str) -> int:
    return _count_hits(chunk_lower, RISK_KEYWORDS)


# --- Track 1: structure-aware selection over markdown headers -----------------

HEADER_RE = re.compile(r"(?m)^#{1,6}\s+(.*)$")
MIN_HEADERS_FOR_STRUCTURED = 3

# Header-relevance vocabulary. Headers are short and low-entropy, so plain
# substring stems are reliable here in a way they are not in body text.
SECTION_KEYWORDS_HIGH = [
    "schedule",
    "pricing",
    "price",
    "scope",
    "specification",
    "requirement",
    "deliverable",
    "deliver",
    "deadline",
    "timeline",
    "completion",
    "close date",
    "due date",
]

SECTION_KEYWORDS_BOILERPLATE = [
    "terms",
    "definitions",
    "general",
]

SECTION_BUDGET_SHARE = 0.40
SECTION_MAX_CHARS = 3000
# A "section" that is only a header line has no content worth a budget slot —
# and taking it would block the chunk fill from covering that area.
SECTION_MIN_CHARS = 100
STRUCTURED_BEGINNING_SHARE = 0.20
STRUCTURED_ENDING_SHARE = 0.10


def _find_sections(text: str) -> list[tuple[str, int, int]]:
    """Return (header_text, start, end) for each markdown-header section.
    start is the header line start; end is the next header start (or EOF)."""
    matches = list(HEADER_RE.finditer(text))
    sections = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        header_text = re.sub(r"[*#_]", "", match.group(1)).strip()
        sections.append((header_text, match.start(), end))
    return sections


def _section_score(header_text: str) -> int:
    lower = header_text.lower()
    # FAR/DFARS clause citations ("52.242-17 ...", "252.203-7000 ...") are
    # boilerplate even when their titles contain words like "requirements".
    if re.match(r"^\d{1,3}\.\d{3}-\d+", header_text.strip()):
        return 0
    score = sum(1 for kw in SECTION_KEYWORDS_HIGH if kw in lower)
    if score == 0 and any(kw in lower for kw in SECTION_KEYWORDS_BOILERPLATE):
        return -1
    return score


def _trim_structured(text: str, max_chars: int) -> str:
    """Track 1: headers exist — take full content of relevant sections first,
    then fill the remaining budget with density-scored chunks (same scoring as
    Track 2) over the parts of the document not already covered."""

    beginning_chars = int(max_chars * STRUCTURED_BEGINNING_SHARE)
    ending_chars = int(max_chars * STRUCTURED_ENDING_SHARE)
    section_budget = int(max_chars * SECTION_BUDGET_SHARE)

    region_start = beginning_chars
    region_end = len(text) - ending_chars

    beginning = text[:beginning_chars]
    ending = text[-ending_chars:]

    # Rank sections by header relevance; take positive scorers only.
    candidates = [
        (header, start, min(end, start + SECTION_MAX_CHARS))
        for header, start, end in _find_sections(text)
        if start >= region_start
        and start < region_end
        and end - start >= SECTION_MIN_CHARS
        and _section_score(header) > 0
    ]
    candidates.sort(key=lambda s: (-_section_score(s[0]), s[1]))

    taken_spans: list[tuple[int, int]] = []
    remaining = section_budget
    for _header, start, end in candidates:
        end = min(end, region_end)
        size = end - start
        if size <= 0 or size > remaining:
            continue
        taken_spans.append((start, end))
        remaining -= size

    # Unused section budget rolls into the chunk fill.
    fill_budget = (max_chars - beginning_chars - ending_chars - section_budget) + remaining
    spec_fill = int(fill_budget * 0.58)
    risk_fill = fill_budget - spec_fill

    middle = text[region_start:region_end]
    chunks = [middle[i : i + CHUNK_SIZE] for i in range(0, len(middle), CHUNK_SIZE)]
    chunks_lower = [chunk.lower() for chunk in chunks]

    def overlaps_taken(index: int) -> bool:
        chunk_start = region_start + index * CHUNK_SIZE
        chunk_end = chunk_start + len(chunks[index])
        return any(chunk_start < e and chunk_end > s for s, e in taken_spans)

    taken_chunks: set[int] = set()
    for score_fn, budget in (
        (lambda i: _spec_score(chunks[i], chunks_lower[i]), spec_fill),
        (lambda i: _risk_score(chunks_lower[i]), risk_fill),
    ):
        ranked = sorted(
            (i for i in range(len(chunks)) if i not in taken_chunks and not overlaps_taken(i)),
            key=score_fn,
            reverse=True,
        )
        left = budget
        for i in ranked:
            if left < len(chunks[i]):
                break
            if score_fn(i) == 0:
                break
            taken_chunks.add(i)
            left -= len(chunks[i])

    # Assemble every kept piece in document order.
    pieces = [(s, text[s:e]) for s, e in taken_spans]
    previous_index: int | None = None
    for i in sorted(taken_chunks):
        chunk_start = region_start + i * CHUNK_SIZE
        if previous_index is not None and i == previous_index + 1:
            last_start, last_text = pieces[-1]
            pieces[-1] = (last_start, last_text + chunks[i])
        else:
            pieces.append((chunk_start, chunks[i]))
        previous_index = i
    pieces.sort(key=lambda p: p[0])

    middle_text = "\n\n--- MID-DOCUMENT EXCERPT ---\n\n".join(p[1] for p in pieces)

    trimmed = (
        beginning
        + "\n\n--- DOCUMENT TRIMMED: SECTION- AND DENSITY-SELECTED EXCERPTS BELOW ---\n\n"
        + middle_text
        + "\n\n--- DOCUMENT END EXCERPT ---\n\n"
        + ending
    )
    return trimmed[:max_chars]


def smart_trim(text: str, max_chars: int = 18000) -> str:
    """
    Two-track trim dispatcher.

    Track 1 (structured): if the markdown carries MIN_HEADERS_FOR_STRUCTURED or
    more headers, take full content of relevance-scored sections first, then
    fill with density-scored chunks (_trim_structured).

    Track 2 (form layout): fewer headers — pure density scoring (_trim_density,
    the original algorithm, unchanged).
    """

    if len(text) <= max_chars:
        return text

    if len(HEADER_RE.findall(text)) >= MIN_HEADERS_FOR_STRUCTURED:
        return _trim_structured(text, max_chars)
    return _trim_density(text, max_chars)


def _trim_density(text: str, max_chars: int = 18000) -> str:
    """
    Track 2: trim long markdown while preserving spec-heavy and risk-heavy sections.

    Strategy:
    1. Keep the beginning of the document because RFQ metadata often appears early.
    2. Split the middle into fixed chunks and score each chunk twice:
       - spec score: weighted density of manufacturing-spec signals (part
         numbers, NSNs, materials, dimensional callouts, spec standards).
       - risk score: density of legal/commercial risk keywords.
    3. Spend a protected spec budget on the highest-spec-scoring chunks, then a
       risk budget on the highest-risk-scoring remaining chunks. Density-based
       ranking means one stray "material" in boilerplate cannot outrank a real
       spec table, which was the failure mode of doc-order keyword matching.
    4. Keep the end of the document because terms, clauses, and certifications
       often appear near the back.

    Kept chunks are reassembled in document order; adjacent chunks are joined
    seamlessly so tables spanning chunk boundaries stay readable.
    """

    if len(text) <= max_chars:
        return text

    beginning_chars = int(max_chars * BEGINNING_SHARE)
    ending_chars = int(max_chars * ENDING_SHARE)
    spec_budget = int(max_chars * SPEC_SHARE)
    risk_budget = max_chars - beginning_chars - ending_chars - spec_budget

    beginning = text[:beginning_chars]
    ending = text[-ending_chars:]

    middle = text[beginning_chars : len(text) - ending_chars]

    chunks = [middle[i : i + CHUNK_SIZE] for i in range(0, len(middle), CHUNK_SIZE)]
    chunks_lower = [chunk.lower() for chunk in chunks]

    spec_ranked = sorted(
        range(len(chunks)),
        key=lambda i: _spec_score(chunks[i], chunks_lower[i]),
        reverse=True,
    )
    taken: set[int] = set()
    remaining = spec_budget
    for i in spec_ranked:
        if remaining < len(chunks[i]):
            break
        if _spec_score(chunks[i], chunks_lower[i]) == 0:
            break
        taken.add(i)
        remaining -= len(chunks[i])

    risk_ranked = sorted(
        (i for i in range(len(chunks)) if i not in taken),
        key=lambda i: _risk_score(chunks_lower[i]),
        reverse=True,
    )
    remaining = risk_budget
    for i in risk_ranked:
        if remaining < len(chunks[i]):
            break
        if _risk_score(chunks_lower[i]) == 0:
            break
        taken.add(i)
        remaining -= len(chunks[i])

    # Reassemble in document order; adjacent chunks join without a separator.
    excerpts: list[str] = []
    previous_index: int | None = None
    for i in sorted(taken):
        if previous_index is not None and i == previous_index + 1:
            excerpts[-1] += chunks[i]
        else:
            excerpts.append(chunks[i])
        previous_index = i

    middle_text = "\n\n--- MID-DOCUMENT EXCERPT ---\n\n".join(excerpts)

    trimmed = (
        beginning
        + "\n\n--- DOCUMENT TRIMMED: SPEC- AND RISK-RELEVANT EXCERPTS BELOW ---\n\n"
        + middle_text
        + "\n\n--- DOCUMENT END EXCERPT ---\n\n"
        + ending
    )

    return trimmed[:max_chars]
