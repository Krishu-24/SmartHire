"""
Resilient multi-engine PDF ingestion.

Contract: extract() NEVER raises. A resume that cannot be read becomes a
quality-0 stub that still flows through ranking and still appears in the UI,
flagged for manual review. A candidate silently vanishing from a shortlist is a
far worse failure than one shown with an honest warning.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from backend import config
from backend.core import blind, context, normalizer
from backend.core.context import ChunkContext
from backend.core.normalizer import Chunk

try:
    import pymupdf
except ImportError:  # pragma: no cover
    import fitz as pymupdf


# ─────────────────────────────────────────────────────────────────────────────
# Section vocabulary
# ─────────────────────────────────────────────────────────────────────────────

SECTION_SYNONYMS: dict[str, list[str]] = {
    "EXPERIENCE": [
        "experience", "work experience", "professional experience", "employment",
        "employment history", "work history", "professional background", "career history",
        "internship", "internships", "industry experience", "relevant experience",
    ],
    "EDUCATION": [
        "education", "academic background", "academics", "qualifications",
        "educational qualifications", "academic qualifications", "coursework",
    ],
    "SKILLS": [
        "skills", "technical skills", "core competencies", "competencies",
        "technologies", "tech stack", "areas of expertise", "proficiencies", "toolkit",
    ],
    "PROJECTS": [
        "projects", "personal projects", "academic projects", "key projects",
        "selected projects", "portfolio", "side projects",
    ],
    "SUMMARY": [
        "summary", "profile", "about", "about me", "objective", "career objective",
        "professional summary", "overview",
    ],
    "CERTIFICATIONS": [
        "certifications", "certificates", "licenses", "courses", "training",
    ],
    "ACHIEVEMENTS": [
        "achievements", "awards", "honors", "honours", "accomplishments",
        "publications", "activities", "extracurricular",
    ],
    "INTERESTS": ["interests", "hobbies", "personal interests"],
}

_HEADER_MAX_LEN = 60
_HEADER_RE = re.compile(r"^[A-Za-z][A-Za-z /&'-]{2,58}:?$")


@dataclass(slots=True)
class HiddenSpan:
    """Text present in the PDF but not meant to be seen by a human reader."""
    text: str
    reason: str                 # invisible-colour | sub-legible-size
    detail: str
    page: int


@dataclass(slots=True)
class ParsedDoc:
    """One ingested document, ready for the engine.

    Two texts, and the difference matters. `text` is what the engine matched on
    and what every chunk span indexes — it has already had identity removed, so
    the ranking is blind by construction rather than by policy. `raw_text` keeps
    the pre-redaction form for provenance only; nothing scores against it.
    """
    doc_id: str
    name: str
    filename: str
    text: str                                       # redacted; chunk spans index this
    raw_text: str = ""                              # pre-redaction, never scored
    chunks: list[Chunk] = field(default_factory=list)
    chunk_contexts: list[ChunkContext] = field(default_factory=list)
    sections: dict[str, tuple[int, int]] = field(default_factory=dict)
    redaction: blind.RedactionReport | None = None
    hidden: list[HiddenSpan] = field(default_factory=list)
    engine: str = "none"
    pages: int = 0
    chars: int = 0
    quality: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def context_for(self, chunk_idx: int) -> ChunkContext | None:
        if 0 <= chunk_idx < len(self.chunk_contexts):
            return self.chunk_contexts[chunk_idx]
        return None

    @property
    def canonical_text(self) -> str:
        return normalizer.canonicalize(self.text)

    @property
    def tokens(self) -> list[str]:
        return normalizer.tokenize(self.canonical_text)


# ─────────────────────────────────────────────────────────────────────────────
# Extraction engines
# ─────────────────────────────────────────────────────────────────────────────

def _extract_pymupdf(path: pathlib.Path) -> tuple[str, int]:
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text("text") for page in doc), doc.page_count


# Two-column resumes are common (a narrow skills/contact rail beside the main
# body) and they are the layout that silently destroys a keyword engine: reading
# in raw order interleaves the two, so "Python" from the rail lands in the middle
# of an unrelated sentence and every chunk spans two topics.
_COLUMN_GAP_RATIO = 0.10        # a gutter must be this share of page width
_COLUMN_MIN_SHARE = 0.15        # ...and each side must hold this share of the text


def _extract_columns(path: pathlib.Path) -> tuple[str, int, bool]:
    """Layout-aware extraction that reads each column fully before the next.

    Returns (text, page_count, found_columns). `found_columns` is False when
    every page was single-column, and the caller then keeps the original fast
    path text — so this can never reorder a document that was already correct.
    """
    out: list[str] = []
    pages = 0
    found = False

    with pymupdf.open(path) as doc:
        pages = doc.page_count
        for page in doc:
            blocks = [b for b in page.get_text("blocks") if len(b) >= 5 and str(b[4]).strip()]
            if not blocks:
                continue

            width = float(page.rect.width) or 1.0
            split = _column_split(blocks, width)

            if split is None:
                blocks.sort(key=lambda b: (round(b[1], 1), b[0]))
                out.append("\n".join(str(b[4]).strip() for b in blocks))
                continue

            found = True
            left = [b for b in blocks if (b[0] + b[2]) / 2 < split]
            right = [b for b in blocks if (b[0] + b[2]) / 2 >= split]
            for column in (left, right):
                column.sort(key=lambda b: (round(b[1], 1), b[0]))
                out.append("\n".join(str(b[4]).strip() for b in column))

    return "\n".join(out), pages, found


def _column_split(blocks: list, width: float) -> float | None:
    """The x of a real vertical gutter, or None when the page is one column.

    Looks for a band of x that no text block crosses. A table or a centred
    heading spanning the full width breaks the gutter and correctly returns None.
    """
    if len(blocks) < 6:
        return None

    # Candidate gutters only in the middle of the page; a margin is not a column.
    lo, hi = width * 0.30, width * 0.70
    spans = [(float(b[0]), float(b[2])) for b in blocks]

    best: tuple[float, float] | None = None       # (gap width, centre)
    step = max(width / 120.0, 1.0)
    x = lo
    while x <= hi:
        if not any(x0 < x < x1 for x0, x1 in spans):
            # Widen to the full extent of this empty band.
            left_edge = max((x1 for x0, x1 in spans if x1 <= x), default=0.0)
            right_edge = min((x0 for x0, x1 in spans if x0 >= x), default=width)
            gap = right_edge - left_edge
            if best is None or gap > best[0]:
                best = (gap, (left_edge + right_edge) / 2)
            x = right_edge + step
            continue
        x += step

    if best is None or best[0] < width * _COLUMN_GAP_RATIO:
        return None

    centre = best[1]
    left_chars = sum(len(str(b[4])) for b in blocks if (b[0] + b[2]) / 2 < centre)
    right_chars = sum(len(str(b[4])) for b in blocks if (b[0] + b[2]) / 2 >= centre)
    total = left_chars + right_chars or 1

    # Both sides must carry real content. A lone page number on the right is not
    # a column, and treating it as one would move it to the end of the document.
    if min(left_chars, right_chars) / total < _COLUMN_MIN_SHARE:
        return None
    return centre


def _extract_pdfplumber(path: pathlib.Path) -> tuple[str, int]:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
        return "\n".join(pages), len(pdf.pages)


def _looks_usable(text: str) -> bool:
    return (
        len(text.strip()) >= config.MIN_CHARS_FOR_FAST_PATH
        and normalizer.alpha_ratio(text) >= config.MIN_ALPHA_RATIO
    )


# ─────────────────────────────────────────────────────────────────────────────
# Invisible text
# ─────────────────────────────────────────────────────────────────────────────

def _luma(packed: int) -> float:
    """Perceived brightness of a PyMuPDF packed sRGB colour, 0 (black) to 1 (white)."""
    r = (packed >> 16) & 0xFF
    g = (packed >> 8) & 0xFF
    b = packed & 0xFF
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def find_hidden(path: pathlib.Path) -> list[HiddenSpan]:
    """Text a human reader cannot see but a parser reads perfectly.

    The oldest ATS attack there is: paste the job description into the footer in
    white-on-white, or at one point, and let the keyword matcher find it. We read
    the span attributes rather than the flattened text, so the trick is visible to
    us exactly because it is invisible to everyone else.

    Best-effort by design — a PDF can hide text in ways this does not model (a
    white rectangle drawn over black text, a clipping path). Silence from this
    function is not a clean bill of health, and nothing downstream treats it as one.
    """
    found: list[HiddenSpan] = []
    try:
        with pymupdf.open(path) as doc:
            for page_no, page in enumerate(doc, start=1):
                data = page.get_text("dict")
                for block in data.get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = (span.get("text") or "").strip()
                            if len(text) < 12:      # too short to be a keyword dump
                                continue
                            size = float(span.get("size", 12.0))
                            luma = _luma(int(span.get("color", 0)))

                            if luma >= config.HIDDEN_TEXT_MIN_LUMA:
                                found.append(HiddenSpan(
                                    text=text, reason="invisible-colour",
                                    detail=f"rendered at {luma:.0%} brightness on a white page",
                                    page=page_no,
                                ))
                            elif size < config.HIDDEN_TEXT_MIN_SIZE:
                                found.append(HiddenSpan(
                                    text=text, reason="sub-legible-size",
                                    detail=f"rendered at {size:.1f}pt",
                                    page=page_no,
                                ))
    except Exception:                               # noqa: BLE001
        # A file we cannot introspect is not a file we get to accuse.
        return []
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Section segmentation
# ─────────────────────────────────────────────────────────────────────────────

# Decoration people wrap headings in: rules, bullets, box drawing, arrows.
_DECORATION = "─━—–-=_~*•▪◦‣·|/\\<>#+ \t"
# Trailing parentheticals and dates: "EXPERIENCE (2021-2024)", "SKILLS | Technical"
_HEADER_TAIL_RE = re.compile(r"\s*[\(\[|].*$|\s*\d{4}\s*[-–—]\s*(\d{4}|present).*$", re.IGNORECASE)


def _header_candidate(line: str) -> tuple[str, int] | None:
    """Reduce a line to the heading it might be, plus where the content resumes.

    Returns (probe, offset_into_line_where_body_starts) or None.

    Handles the three shapes a strict `^Word$` regex misses, all of which are
    ordinary in real resumes:
        "──── EXPERIENCE ────"   decoration on both sides
        "SKILLS: Python, Java"   heading and body on one line
        "EXPERIENCE (2021-24)"   a trailing parenthetical
    """
    raw = line.strip()
    if not raw:
        return None

    # "Heading: body" — the heading is only the part before the colon, and the
    # section must start after it or the body is lost with the header line.
    body_at = len(line)
    head = raw
    if ":" in raw:
        before, _, after = raw.partition(":")
        if before.strip() and len(before.strip()) <= _HEADER_MAX_LEN:
            head = before
            if after.strip():
                body_at = line.index(":") + 1

    head = head.strip(_DECORATION)
    head = _HEADER_TAIL_RE.sub("", head).strip(_DECORATION)

    if not head or len(head) > _HEADER_MAX_LEN:
        return None
    # A heading is words, not a sentence and not a bullet of prose.
    if len(head.split()) > 4 or not re.match(r"^[A-Za-z][A-Za-z0-9 /&'’-]*$", head):
        return None
    return head, body_at


def _match_section(probe: str) -> str | None:
    """Canonical section name for a heading, or None."""
    lowered = probe.lower().strip()
    best_name, best_score = None, 0.0
    for canonical, synonyms in SECTION_SYNONYMS.items():
        for syn in synonyms:
            score = fuzz.ratio(lowered, syn)
            if score > best_score:
                best_name, best_score = canonical, score
    return best_name if best_score >= config.SECTION_FUZZ_THRESHOLD else None


def segment(display: str) -> dict[str, tuple[int, int]]:
    """Locate canonical sections as (start, end) spans over the display text.

    Headers are matched fuzzily, so EXPERIENCE / Work History / Employment all
    collapse to one canonical name. A resume with no detectable headers falls
    back to inferring them from content shape — degraded, not broken.
    """
    hits: list[tuple[int, int, str]] = []   # (start, end_of_header, canonical)
    offset = 0

    for line in display.split("\n"):
        line_start = display.find(line, offset) if line else offset
        if line_start < 0:
            line_start = offset
        offset = line_start + len(line)

        candidate = _header_candidate(line)
        if candidate is None:
            continue
        probe, body_at = candidate

        name = _match_section(probe)
        if name:
            # For "Skills: Python, Java" the section opens mid-line, so the body
            # on that same line still belongs to the section it announces.
            hits.append((line_start, line_start + body_at, name))

    if not hits:
        return _infer_sections(display)

    sections: dict[str, tuple[int, int]] = {}
    for idx, (start, header_end, name) in enumerate(hits):
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(display)
        # Later duplicates of a heading extend the first occurrence rather than
        # overwriting it, so "Projects" appearing twice does not lose the first block.
        if name in sections:
            sections[name] = (sections[name][0], max(sections[name][1], end))
        else:
            sections[name] = (header_end, end)
    return sections


# ─────────────────────────────────────────────────────────────────────────────
# Inference for unstructured resumes
# ─────────────────────────────────────────────────────────────────────────────

# Date spans as they actually appear: "Jun 2025 - Aug 2025", "01/2024-06/2024",
# "2022 – Present", "Summer 2024". Written permissively because an unstructured
# resume is exactly the case where dates are the only structure left.
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_SEASON = r"(?:summer|winter|spring|fall|autumn)"
_DATE_POINT = rf"(?:(?:{_MONTH}|{_SEASON})\s*)?(?:\d{{1,2}}[/.-])?\d{{4}}"
_DATE_RANGE_RE = re.compile(
    rf"\b{_DATE_POINT}\s*(?:[-–—]{{1,2}}|\bto\b)\s*(?:{_DATE_POINT}|present|current|now|ongoing)\b",
    re.IGNORECASE,
)
_DEGREE_RE = re.compile(
    r"\b(b\.?\s?tech|b\.?\s?e\.?|b\.?\s?sc|b\.?\s?c\.?a|bachelor|m\.?\s?tech|m\.?\s?sc|"
    r"m\.?\s?c\.?a|master|mba|ph\.?\s?d|diploma|12th|10th|cgpa|gpa|percentage|"
    r"university|college|institute|vidyalaya|school|final year|pre-?final year|"
    r"undergraduate|graduat\w+|coursework|semester)\b",
    re.IGNORECASE,
)
_ROLE_RE = re.compile(
    r"\b(intern|interned|internship|engineer|developer|analyst|consultant|associate|"
    r"freelance|contractor|trainee|manager|lead|worked at|employed)\b",
    re.IGNORECASE,
)
_PROJECT_RE = re.compile(
    r"\b(built|building|developed|developing|created|designed|implemented|shipped|"
    r"project|projects|application|applications|app|platform|system|clone|portfolio|"
    r"website|bot|pipeline|dashboard|wrote|deployed)\b",
    re.IGNORECASE,
)
_TOOL_LIST_RE = re.compile(r"(?:[A-Za-z0-9+#.]{2,}\s*[,/|]\s*){3,}[A-Za-z0-9+#.]{2,}")


def _infer_sections(display: str) -> dict[str, tuple[int, int]]:
    """Guess sections from content shape when a resume declares none.

    Plenty of real resumes — especially the ones generated by a builder, or
    written as one continuous block — carry no headings at all. Without this the
    whole document scores as UNKNOWN, and the context model loses its main
    signal: it can no longer tell a bullet in a job from a tag in a list.

    Deliberately coarse. It only claims EXPERIENCE, EDUCATION, SKILLS and
    PROJECTS, only from unambiguous shapes, and a line matching nothing stays
    unlabelled rather than being forced into the nearest bucket.
    """
    lines: list[tuple[int, int, str]] = []
    offset = 0
    for line in display.split("\n"):
        start = display.find(line, offset) if line else offset
        if start < 0:
            start = offset
        offset = start + len(line)
        lines.append((start, offset, line))

    labelled: list[tuple[int, int, str]] = []
    for start, end, line in lines:
        probe = line.strip()
        if len(probe) < 12:
            continue

        if _TOOL_LIST_RE.search(probe) and not _ROLE_RE.search(probe):
            labelled.append((start, end, "SKILLS"))
        elif _DEGREE_RE.search(probe):
            labelled.append((start, end, "EDUCATION"))
        elif _DATE_RANGE_RE.search(probe) and _ROLE_RE.search(probe):
            labelled.append((start, end, "EXPERIENCE"))
        elif _PROJECT_RE.search(probe):
            labelled.append((start, end, "PROJECTS"))

    if not labelled:
        return {}

    # Group into CONTIGUOUS runs, then keep each label's longest run.
    #
    # Taking min-to-max per label instead would make every span overlap every
    # other — EDUCATION reaching from the header to the last line — and
    # `_section_for` returns the first span containing a position, so the
    # attribution would come down to dict order rather than the document. One
    # unbroken run per label is a claim the text actually supports.
    labelled.sort(key=lambda t: t[0])
    runs: list[tuple[int, int, str]] = []
    for start, end, name in labelled:
        if runs and runs[-1][2] == name:
            runs[-1] = (runs[-1][0], end, name)
        else:
            runs.append((start, end, name))

    best: dict[str, tuple[int, int]] = {}
    for start, end, name in runs:
        if name not in best or (end - start) > (best[name][1] - best[name][0]):
            best[name] = (start, end)

    # Two labels is the minimum worth acting on; one span covering the whole
    # document tells the context model nothing it did not already assume.
    return best if len(best) >= 2 else {}


# ─────────────────────────────────────────────────────────────────────────────
# Quality scoring
# ─────────────────────────────────────────────────────────────────────────────

def _quality(text: str, sections: dict, chunks: list[Chunk], engine: str) -> float:
    """0..1 confidence that we read this document properly. Surfaced in the UI."""
    if not text.strip():
        return 0.0

    chars = len(text.strip())
    volume = min(chars / 1200.0, 1.0)          # a full resume is ~1200-4000 chars
    structure = min(len(sections) / 4.0, 1.0)  # 4+ detected sections is healthy
    density = min(len(chunks) / 15.0, 1.0)
    legibility = normalizer.alpha_ratio(text)

    score = 0.40 * volume + 0.20 * structure + 0.20 * density + 0.20 * legibility
    if engine == "pdfplumber":
        score *= 0.95                          # needed the fallback; slightly less certain
    return round(min(max(score, 0.0), 1.0), 3)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract(path: str | pathlib.Path, doc_id: str | None = None,
            anonymise: bool = True) -> ParsedDoc:
    """Ingest one PDF. Never raises.

    `anonymise=False` is for the job description, which must reach the bias
    detector intact — the gendered pronouns and school filters it hunts for are
    the very strings redaction removes.
    """
    path = pathlib.Path(path)
    doc_id = doc_id or path.stem
    warnings: list[str] = []
    raw, pages, engine = "", 0, "none"

    # --- Fast path ---
    try:
        raw, pages = _extract_pymupdf(path)
        engine = "pymupdf"
    except Exception as exc:                    # noqa: BLE001
        warnings.append(f"pymupdf failed: {type(exc).__name__}")

    # --- Column repair ---
    # Raw reading order interleaves a two-column layout, which puts the skills
    # rail through the middle of the experience prose and leaves every chunk
    # spanning two unrelated topics. Only replaces the text when a genuine
    # gutter was found, so a single-column page is untouched.
    if raw.strip():
        try:
            columned, col_pages, found_columns = _extract_columns(path)
            if found_columns and len(columned.strip()) >= len(raw.strip()) * 0.9:
                raw, pages, engine = columned, col_pages, "pymupdf-columns"
                warnings.append("multi-column layout detected; columns read in order")
        except Exception as exc:                # noqa: BLE001
            warnings.append(f"column pass failed: {type(exc).__name__}")

    # --- Layout-aware fallback ---
    if not _looks_usable(raw):
        if engine == "pymupdf":
            warnings.append(
                f"fast path yielded {len(raw.strip())} chars "
                f"(alpha ratio {normalizer.alpha_ratio(raw):.2f}); retrying with pdfplumber"
            )
        try:
            alt, alt_pages = _extract_pdfplumber(path)
            if len(alt.strip()) > len(raw.strip()):
                raw, pages, engine = alt, alt_pages, "pdfplumber"
        except Exception as exc:                # noqa: BLE001
            warnings.append(f"pdfplumber failed: {type(exc).__name__}")

    display = normalizer.repair_text(raw)

    if not display.strip():
        warnings.append("no extractable text — likely a scanned image. Manual review required.")
        return ParsedDoc(
            doc_id=doc_id, name=_infer_name(doc_id, ""), filename=path.name,
            text="", engine=engine, pages=pages, chars=0, quality=0.0, warnings=warnings,
        )

    name = _infer_name(doc_id, display)

    # --- Blind screening, before anything is matched -------------------------
    # Sections are found twice on purpose: once on the original so the
    # EDUCATION-only rules know where they are, then again on the redacted text
    # because the placeholders shift every offset after them. Chunk spans must
    # index the text the engine actually reads, so that second pass is the real one.
    hidden = find_hidden(path)
    if anonymise and config.REDACT_BEFORE_SCORING:
        redaction = blind.redact(display, name=name, sections=segment(display))
        engine_text = redaction.text
    else:
        redaction = blind.RedactionReport(text=display)
        engine_text = display

    sections = segment(engine_text)
    if not sections:
        warnings.append("no section headers detected; using whole-document chunking")

    chunks = normalizer.chunk_text(engine_text, sections)
    if not chunks:
        warnings.append("no chunks above the minimum length; document may be near-empty")

    contexts = context.annotate(chunks, engine_text) if config.CONTEXT_WEIGHTING_ENABLED else []

    quality = _quality(engine_text, sections, chunks, engine)
    if quality < 0.5:
        warnings.append(f"low parse quality ({quality:.2f})")

    if hidden:
        warnings.append(
            f"{len(hidden)} invisible text {'span' if len(hidden) == 1 else 'spans'} "
            f"found in the PDF — possible ATS manipulation"
        )

    return ParsedDoc(
        doc_id=doc_id,
        name=name,
        filename=path.name,
        text=engine_text,
        raw_text=display,
        chunks=chunks,
        chunk_contexts=contexts,
        sections=sections,
        redaction=redaction,
        hidden=hidden,
        engine=engine,
        pages=pages,
        chars=len(engine_text),
        quality=quality,
        warnings=warnings,
    )


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_NAME_LINE_RE = re.compile(r"^[A-Z][a-zA-Z.'-]+(?: [A-Z][a-zA-Z.'-]+){1,3}$")


def _infer_name(doc_id: str, display: str) -> str:
    """Best-effort candidate name: the first line that looks like a person's name."""
    for line in display.split("\n")[:6]:
        probe = line.strip()
        if _NAME_LINE_RE.match(probe) and not _EMAIL_RE.search(probe):
            lowered = probe.lower()
            if not any(w in lowered for w in ("resume", "curriculum", "vitae", "profile")):
                return probe

    # Fall back to the filename: "c01_aarav_mehta" -> "Aarav Mehta"
    stem = re.sub(r"^c?\d+[_-]", "", doc_id)
    return re.sub(r"[_-]+", " ", stem).title() or doc_id


def extract_many(paths: list[str | pathlib.Path]) -> list[ParsedDoc]:
    """Ingest a batch. One bad file never takes down the rest."""
    return [extract(p, doc_id=pathlib.Path(p).stem) for p in sorted(paths, key=str)]
