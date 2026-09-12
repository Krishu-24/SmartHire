"""
Central tuning surface for the shortlisting engine.

Every magic number in the scoring pipeline lives here so calibration is one file,
not a scavenger hunt. Values below are the Phase 1 defaults; recalibrate TAU_LO /
TAU_HI against the real corpus if the score-spread test fails.
"""
from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"


# ─── Device ──────────────────────────────────────────────────────────────────
# Hardware decision (Phase 2): pure local on Apple Silicon. CPU is the default
# because 18 resumes is far below the batch size where a GPU pays for itself,
# and CPU avoids every MPS dtype quirk. Opt in with INTERLOOM_DEVICE=mps.
DEVICE = os.environ.get("INTERLOOM_DEVICE", "cpu")


# ─── Semantic backend ────────────────────────────────────────────────────────
# "minilm"     — sentence-transformers all-MiniLM-L6-v2 (default)
# "tfidf_svd"  — scikit-learn TF-IDF + TruncatedSVD, the offline fallback.
#                Degraded quality, but the pipeline survives a dead venue wifi.
SEMANTIC_BACKEND = os.environ.get("INTERLOOM_SEMANTIC", "minilm")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SVD_DIMS = 256


# ─── Channel K: lexical ──────────────────────────────────────────────────────
BM25_K1 = 1.5
BM25_B = 0.75

LEX_EXACT_SCORE = 1.0      # exact or alias match
LEX_FUZZY_SCORE = 0.8      # RapidFuzz match — deliberately below exact
LEX_FUZZY_THRESHOLD = 88   # token_set_ratio cutoff for typo tolerance

# K = this * norm(BM25) + (1-this) * LexCoverage
#
# Requirement-aware coverage leads; corpus-level bag-of-words supports. BM25
# rewards verbosity and raw term overlap — on this corpus the messy run-on resume
# scores the pool maximum on BM25 while covering fewer requirements than three
# candidates above it. The task is "does this person meet these requirements",
# not "does this document resemble that document", so coverage gets the majority.
K_WEIGHT_BM25 = 0.40


# ─── Channel M: semantic ─────────────────────────────────────────────────────
DOCSIM_TOP_K = 3           # top-k chunk pooling, NOT mean-pool (see docs/MATH.md)

# Cosine calibration. MiniLM similarities live in a compressed band, so we
# linearly rescale [TAU_LO, TAU_HI] -> [0, 1] before the value reaches the score.
#
# Calibrated against the corpus, not guessed. Measured distribution of raw cosine
# across 306 (skill x candidate) pairs, split by whether the lexical channel agreed:
#
#     lexically MATCHED (n=131)   p10 0.268   p50 0.447   p90 0.670
#     lexically ABSENT  (n=175)   p10 0.068   p50 0.218   p90 0.370
#
# The populations separate cleanly but overlap between ~0.25 and ~0.50, so the
# band is set to span exactly that discriminative region. TAU_LO sits just below
# the median of the absent population (anything lower really is nothing); TAU_HI
# sits in the upper half of the matched population (anything higher is strong
# evidence regardless of wording).
#
# Re-derive these against the real corpus with: python scripts/calibrate.py
TAU_LO = 0.20
TAU_HI = 0.55

# M = this * norm(DocSim) + (1-this) * SemCoverage
#
# Deliberately low, and this is the most important tuning decision in the file.
# Whole-document similarity is partly a proxy for lexical overlap: a resume that
# is a bare list of skill names embeds very close to a JD that lists skill names.
# On this corpus the planted keyword-stuffer scores docsim_norm = 1.000, the pool
# maximum, while per-skill SemCoverage correctly rates her 0.306.
#
# Leaving DocSim at parity would let the semantic channel be fooled by exactly
# the candidate it exists to catch. It still contributes real document-level
# context, so it stays — but SemCoverage, which is requirement-aware, leads.
M_WEIGHT_DOCSIM = 0.25


# ─── Per-skill evidence thresholds ───────────────────────────────────────────
# Applied to the CALIBRATED semantic value g(sem), not the raw cosine.
STATUS_INFERRED_MIN = 0.55  # not named, but demonstrably practised
STATUS_WEAK_MIN = 0.25      # adjacent experience only


# ─── Fusion ──────────────────────────────────────────────────────────────────
DEFAULT_ALPHA = 0.5         # 1.0 = pure keyword, 0.0 = pure semantic
NORM_LO_PCT = 5             # robust pool normalisation anchors. True min/max would
NORM_HI_PCT = 95            # let one broken resume compress the whole pool.

GATE_ENABLED_DEFAULT = False
GATE_FLOOR = 0.60           # gate re-ranks, never annihilates
GATE_SPAN = 0.40            # Gate = FLOOR + SPAN * required_coverage

RRF_K = 60

# Cross-channel disagreement flags.
#
# Rank delta alone proved too noisy at this pool size: on 18 candidates a swing of
# 4 places is often just churn in the middle of the pack, and it flagged the typo
# candidate as a hidden gem while missing the real one. The real signal is in the
# evidence matrix, not in pool position — so the primary triggers are evidence-based
# and rank delta is kept as a corroborating trigger at a wider threshold.
RRF_FLAG_DELTA = 6          # |rank_lex - rank_sem| that alone justifies a flag

# HIDDEN GEM: a meaningful share of REQUIRED skills are present semantically but
# never stated literally — right experience, wrong vocabulary. This is the
# "Express and MongoDB" candidate the problem statement describes.
HIDDEN_GEM_INFERRED_RATIO = 0.15

# ...but only for candidates who actually clear the bar. A hidden gem is someone
# who meets the requirements and is merely hard to SEE lexically. A candidate who
# does not meet them isn't hidden, they're just not a fit, and labelling them a
# gem in a recruiter's UI is actively misleading.
HIDDEN_GEM_MIN_COVERAGE = 0.60

# SURFACE MATCH: lexical coverage far outruns semantic coverage — the resume
# names the skills but shows no work behind them.
SURFACE_LEX_SEM_GAP = 0.40


# ─── Requirement tiers ───────────────────────────────────────────────────────
WEIGHT_REQUIRED = 1.0
WEIGHT_PREFERRED = 0.5


# ─── Parsing ─────────────────────────────────────────────────────────────────
MIN_CHARS_FOR_FAST_PATH = 200   # below this, retry with the layout-aware engine
MIN_ALPHA_RATIO = 0.5           # below this, the "text" is probably extraction noise
SECTION_FUZZ_THRESHOLD = 85     # RapidFuzz cutoff for section header matching
MIN_CHUNK_CHARS = 25            # shorter fragments carry no usable signal


# ─── Data files ──────────────────────────────────────────────────────────────
GAZETTEER_PATH = DATA / "skill_gazetteer.json"
ALIAS_PATH = DATA / "alias_map.json"
BIAS_LEXICON_PATH = DATA / "bias_lexicon.json"
