"""
FastAPI application.

Parsing and embedding happen exactly ONCE per upload and are cached in memory.
Every later request — re-weighting, chat, bias, diff — reads the cached evidence
matrix. The recruiter's weight slider never reaches this server at all; it
recomputes in the browser from the sub-scores shipped in /api/analyze.
"""
from __future__ import annotations

import pathlib
import shutil
import tempfile
import time
from dataclasses import asdict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend import config, models
from backend.core import bias_detector, chat, engine as engine_mod, explainer, fusion, parser, skills

app = FastAPI(title="InterLoom Shortlisting Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:4173", "http://127.0.0.1:4173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_DIR = config.ROOT / "fixtures" / "synthetic"
REAL_JD_DIR = config.ROOT / "data" / "jd"
REAL_RESUME_DIR = config.ROOT / "data" / "resumes"


# ─────────────────────────────────────────────────────────────────────────────
# Session cache
# ─────────────────────────────────────────────────────────────────────────────

class Session:
    """One analysed pool. Built once, read many times."""

    def __init__(self) -> None:
        self.jd: parser.ParsedDoc | None = None
        self.docs: list[parser.ParsedDoc] = []
        self.skills: list[skills.Skill] = []
        self.primitives: list[fusion.Primitives] = []
        self.bias: bias_detector.BiasReport | None = None
        self.backend_name: str = ""
        self.elapsed_ms: int = 0

    @property
    def ready(self) -> bool:
        return bool(self.primitives)

    def candidates(self, alpha: float, gate: bool) -> list[fusion.Candidate]:
        return fusion.score(self.primitives, alpha=alpha, gate=gate)


SESSION = Session()

# The embedding model is loaded once per process, not once per request. A cold
# SentenceTransformer costs ~90s; paying that on every upload would be fatal in a demo.
_ENGINE = engine_mod.Engine()


# ─────────────────────────────────────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────────────────────────────────────

def _analyse(jd_path: pathlib.Path, resume_paths: list[pathlib.Path], alpha: float, gate: bool):
    t0 = time.perf_counter()

    jd = parser.extract(jd_path)
    if not jd.text.strip():
        raise HTTPException(422, "The job description could not be read. "
                                 "It may be a scanned image with no text layer.")

    skill_set = skills.extract_skills(jd.text)
    if not skill_set:
        raise HTTPException(422, "No skills could be extracted from that job description.")

    docs = parser.extract_many(resume_paths)
    subs = _ENGINE.build(docs, jd.text, skill_set)
    primitives = fusion.prepare(subs, skill_set)

    SESSION.jd = jd
    SESSION.docs = docs
    SESSION.skills = skill_set
    SESSION.primitives = primitives
    SESSION.backend_name = _ENGINE.backend_name
    SESSION.bias = bias_detector.detect(
        jd.text, primitives, skill_set,
        {d.name: d.text for d in docs}, alpha=alpha,
    )
    SESSION.elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return _payload(alpha, gate)


def _payload(alpha: float, gate: bool) -> models.AnalyzeResponse:
    cands = SESSION.candidates(alpha, gate)
    texts = {d.doc_id: d.text for d in SESSION.docs}
    explanations = {e.doc_id: e for e in explainer.explain_top(cands, n=len(cands))}

    gaz_clusters = sorted({s.cluster for s in SESSION.skills})

    out_cands = []
    for c in cands:
        exp = explanations.get(c.doc_id)
        out_cands.append(models.CandidateOut(
            doc_id=c.doc_id, name=c.name, filename=c.filename,
            score=c.score, rank=c.rank, k_score=c.k_score, m_score=c.m_score,
            gate=c.gate, rank_lexical=c.rank_lexical, rank_semantic=c.rank_semantic,
            rank_delta=c.rank_delta, rrf=c.rrf, flag=c.flag,
            primitives=models.PrimitivesOut(**{
                k: v for k, v in asdict(c.primitives).items()
                if k not in ("doc_id", "name", "filename")
            }),
            explanation=models.ExplanationOut(
                headline=exp.headline, bullets=exp.bullets,
                matched=exp.matched, inferred=exp.inferred,
                weak=exp.weak, missing=exp.missing,
            ) if exp else None,
            resume_text=texts.get(c.doc_id, ""),
        ))

    title = SESSION.jd.text.split("\n")[1].strip() if SESSION.jd and "\n" in SESSION.jd.text else "Role"

    return models.AnalyzeResponse(
        meta=models.MetaOut(
            alpha=alpha, gate=gate, pool_size=len(cands),
            semantic_backend=SESSION.backend_name, device=config.DEVICE,
            elapsed_ms=SESSION.elapsed_ms,
            tau_lo=config.TAU_LO, tau_hi=config.TAU_HI,
            k_weight_bm25=config.K_WEIGHT_BM25, m_weight_docsim=config.M_WEIGHT_DOCSIM,
            gate_floor=config.GATE_FLOOR, gate_span=config.GATE_SPAN,
            parse_warnings=sum(1 for d in SESSION.docs if d.warnings),
        ),
        job=models.JobOut(
            title=title,
            text=SESSION.jd.text if SESSION.jd else "",
            skills=[models.SkillOut(
                id=s.id, label=s.label, tier=s.tier, weight=s.weight,
                cluster=s.cluster, source=s.source, evidence=s.evidence,
            ) for s in SESSION.skills],
            clusters=gaz_clusters,
            bias=models.BiasOut(**asdict(SESSION.bias)) if SESSION.bias else None,
        ),
        candidates=out_cands,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=models.HealthOut)
def health() -> models.HealthOut:
    return models.HealthOut(
        status="ok",
        semantic_backend=SESSION.backend_name or config.SEMANTIC_BACKEND,
        device=config.DEVICE,
        model=config.EMBED_MODEL,
        has_session=SESSION.ready,
        pool_size=len(SESSION.primitives),
    )


@app.post("/api/analyze", response_model=models.AnalyzeResponse)
async def analyze(
    jd: UploadFile = File(...),
    resumes: list[UploadFile] = File(...),
    alpha: float = Form(config.DEFAULT_ALPHA),
    gate: bool = Form(config.GATE_ENABLED_DEFAULT),
) -> models.AnalyzeResponse:
    """Full pipeline: parse -> extract skills -> embed -> fuse -> explain."""
    if not resumes:
        raise HTTPException(400, "Upload at least one resume.")

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="interloom_"))
    try:
        jd_path = tmp / (jd.filename or "jd.pdf")
        jd_path.write_bytes(await jd.read())

        paths = []
        for item in resumes:
            dest = tmp / (item.filename or f"resume_{len(paths)}.pdf")
            dest.write_bytes(await item.read())
            paths.append(dest)

        return _analyse(jd_path, paths, alpha, gate)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.post("/api/analyze/sample", response_model=models.AnalyzeResponse)
def analyze_sample(
    alpha: float = config.DEFAULT_ALPHA,
    gate: bool = config.GATE_ENABLED_DEFAULT,
) -> models.AnalyzeResponse:
    """Analyse whichever corpus is on disk.

    Prefers the real corpus in data/ when present, otherwise falls back to the
    synthetic fixture set. Lets the UI open in a working state with one click.
    """
    real_jd = sorted(REAL_JD_DIR.glob("*.pdf"))
    real_resumes = sorted(REAL_RESUME_DIR.glob("*.pdf"))

    if real_jd and real_resumes:
        return _analyse(real_jd[0], real_resumes, alpha, gate)

    jd_path = SAMPLE_DIR / "jd_technova.pdf"
    if not jd_path.exists():
        raise HTTPException(
            404,
            "No corpus found. Drop the real PDFs into data/jd and data/resumes, "
            "or run: python scripts/make_synthetic_corpus.py",
        )
    resumes = sorted(p for p in SAMPLE_DIR.glob("*.pdf") if not p.name.startswith("jd_"))
    return _analyse(jd_path, resumes, alpha, gate)


@app.get("/api/rank", response_model=models.AnalyzeResponse)
def rank(alpha: float = config.DEFAULT_ALPHA, gate: bool = config.GATE_ENABLED_DEFAULT):
    """Re-rank the cached pool at a different alpha.

    The UI does not need this — it recomputes locally — but it exists so the
    slider's client-side arithmetic can be checked against the server, which is
    exactly what scripts/check_parity.py does.
    """
    if not SESSION.ready:
        raise HTTPException(409, "Nothing analysed yet. POST /api/analyze first.")
    return _payload(alpha, gate)


@app.post("/api/chat", response_model=models.ChatResponseOut)
def ask(req: models.ChatRequest,
        alpha: float = config.DEFAULT_ALPHA,
        gate: bool = config.GATE_ENABLED_DEFAULT) -> models.ChatResponseOut:
    """Deterministic recruiter QA. No LLM is consulted anywhere in this path."""
    if not SESSION.ready:
        raise HTTPException(409, "Nothing analysed yet. POST /api/analyze first.")
    if not req.query.strip():
        raise HTTPException(400, "Empty query.")

    resp = chat.answer(req.query, SESSION.candidates(alpha, gate), SESSION.skills)
    return models.ChatResponseOut(
        intent=resp.intent, answer=resp.answer, refs=resp.refs, data=resp.data
    )


@app.get("/api/bias", response_model=models.BiasOut)
def bias() -> models.BiasOut:
    if not SESSION.ready or SESSION.bias is None:
        raise HTTPException(409, "Nothing analysed yet. POST /api/analyze first.")
    return models.BiasOut(**asdict(SESSION.bias))
