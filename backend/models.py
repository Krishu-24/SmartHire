"""
The API contract.

Written first and frozen, because four people build against it in parallel and
the frontend's client-side rescore depends on every sub-score being present in
the payload. If a field here changes, frontend/src/lib/rescore.js changes with it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Evidence
# ─────────────────────────────────────────────────────────────────────────────

class SkillCellOut(BaseModel):
    skill_id: str
    label: str
    tier: str                       # REQUIRED | PREFERRED
    weight: float
    cluster: str
    lex: float                      # 0.0 | 0.8 fuzzy | 1.0 exact/alias
    lex_kind: str                   # exact | alias | fuzzy | none
    sem_raw: float                  # raw cosine
    sem_cal: float                  # g(sem_raw)
    coverage: float                 # max(lex, sem_cal)
    status: str                     # MATCHED | INFERRED | WEAK | MISSING
    evidence: str = ""              # the resume sentence behind this cell
    start: int = -1                 # char span into CandidateOut.resume_text
    end: int = -1


class PrimitivesOut(BaseModel):
    """Alpha-independent sub-scores. The client recomputes ranking from these alone."""
    bm25_raw: float
    bm25_norm: float
    docsim_raw: float
    docsim_norm: float
    lex_cov: float
    sem_cov: float
    req_coverage: float
    gap_density: float
    inferred_req_ratio: float
    quality: float
    n_chunks: int
    warnings: list[str] = Field(default_factory=list)
    cells: list[SkillCellOut] = Field(default_factory=list)


class ExplanationOut(BaseModel):
    headline: str
    bullets: list[str] = Field(default_factory=list)
    matched: list[dict] = Field(default_factory=list)
    inferred: list[dict] = Field(default_factory=list)
    weak: list[dict] = Field(default_factory=list)
    missing: list[dict] = Field(default_factory=list)


class CandidateOut(BaseModel):
    doc_id: str
    name: str
    filename: str
    score: float
    rank: int
    k_score: float
    m_score: float
    gate: float
    rank_lexical: int
    rank_semantic: int
    rank_delta: int
    rrf: float
    flag: str                       # HIDDEN_GEM | SURFACE_MATCH | CONSENSUS
    primitives: PrimitivesOut
    explanation: ExplanationOut | None = None
    resume_text: str = ""           # display text; evidence spans index this


# ─────────────────────────────────────────────────────────────────────────────
# Job description
# ─────────────────────────────────────────────────────────────────────────────

class SkillOut(BaseModel):
    id: str
    label: str
    tier: str
    weight: float
    cluster: str
    source: str                     # gazetteer | mined
    evidence: str = ""


class BiasFindingOut(BaseModel):
    category: str
    label: str
    severity: str                   # critical | high | medium | low
    matched_text: str
    start: int
    end: int
    line: str
    suggestion: str
    why: str
    impact: str = ""
    impact_count: int = 0


class BiasOut(BaseModel):
    score: int                      # 0-100 inclusivity
    summary: str
    is_junior_role: bool
    findings: list[BiasFindingOut] = Field(default_factory=list)


class JobOut(BaseModel):
    title: str
    text: str
    skills: list[SkillOut] = Field(default_factory=list)
    clusters: list[str] = Field(default_factory=list)
    bias: BiasOut | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Envelope
# ─────────────────────────────────────────────────────────────────────────────

class MetaOut(BaseModel):
    alpha: float
    gate: bool
    pool_size: int
    semantic_backend: str
    device: str
    elapsed_ms: int
    tau_lo: float
    tau_hi: float
    k_weight_bm25: float
    m_weight_docsim: float
    gate_floor: float
    gate_span: float
    parse_warnings: int


class AnalyzeResponse(BaseModel):
    meta: MetaOut
    job: JobOut
    candidates: list[CandidateOut] = Field(default_factory=list)


class ChatRequest(BaseModel):
    query: str


class ChatResponseOut(BaseModel):
    intent: str
    answer: str
    refs: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)


class HealthOut(BaseModel):
    status: str
    semantic_backend: str
    device: str
    model: str
    has_session: bool
    pool_size: int
