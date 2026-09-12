"""
Format independence: does layout change the score?

`fixtures/formats/` holds the SAME candidate written six ways — two columns, no
headings, ALL-CAPS rules, inline headings, continuous prose. Identical skills,
identical employer, identical projects. A shortlisting engine that ranks them
differently is measuring the resume template, not the person, and that is the
failure mode every candidate complains about and no ATS tests for.

This suite scores all six against one JD and asserts the spread stays small.

    python scripts/verify_formats.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _console  # noqa: F401  (configures stdout encoding on import)

from backend import config
from backend.core import assess, engine as engine_mod, fusion, parser, skills

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMATS = ROOT / "fixtures" / "formats"
JD = ROOT / "fixtures" / "synthetic" / "jd_technova.pdf"

# Two tiers, because there is a real residual and hiding it behind one loose
# threshold would be the wrong kind of green.
#
#   IDEAL  what format-independence should look like. Exceeding it is reported
#          as a WARN: not a regression, but not yet right either.
#   MAX    the hard ceiling. Crossing it means a layout change has moved a
#          candidate further than a genuine difference in ability would.
#
# The known residual is `prose`: a continuous narrative gives the semantic
# channel longer, richer chunks than a bulleted list of the same facts, so it
# scores a few points high. Shortening it would mean penalising context, which
# is the signal the channel exists to read — so it is measured and disclosed
# rather than tuned away.
IDEAL_SCORE_SPREAD = 8.0
MAX_SCORE_SPREAD = 13.0
IDEAL_RANK_SPREAD = 4
MAX_RANK_SPREAD = 8
MAX_COVERAGE_SPREAD = 0.12
MIN_SECTIONS = 3


def tiered(value: float, ideal: float, ceiling: float) -> str:
    """PASS under ideal, WARN between ideal and ceiling, FAIL above it."""
    if value <= ideal:
        return PASS
    return WARN if value <= ceiling else FAIL

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool | str, detail: str = "") -> None:
    status = ok if isinstance(ok, str) else (PASS if ok else FAIL)
    results.append((name, status, detail))
    icon = {PASS: "+", FAIL: "x", WARN: "!"}[status]
    print(f"  {icon} {name:<42} {status:<5} {detail}")


def main() -> int:
    if not FORMATS.exists() or not list(FORMATS.glob("*.pdf")):
        sys.exit("No format fixtures. Run: python scripts/make_format_fixtures.py")
    if not JD.exists():
        sys.exit("No JD. Run: python scripts/make_synthetic_corpus.py")

    print("SmartHire format-independence suite\n")

    paths = sorted(FORMATS.glob("*.pdf"))
    jd = parser.extract(JD, anonymise=False)
    skill_set = skills.extract_skills(jd.text)

    # The six layouts are scored INSIDE the real 18-candidate pool, not against
    # each other. Both channels normalise against the pool (P5/P95), so ranking
    # six near-identical documents on their own stretches sub-point differences
    # across the whole 0-100 range and reports an alarming spread that would
    # never occur in use. Mixed into real competition, the question becomes the
    # one that matters: does the template move you past another person?
    pool_paths = sorted(
        p for p in (ROOT / "fixtures" / "synthetic").glob("*.pdf")
        if not p.name.startswith("jd_")
    )
    docs = parser.extract_many(paths + pool_paths)
    primitives = fusion.prepare(
        engine_mod.Engine().build(docs, jd.text, skill_set), skill_set)
    fusion.adjust(primitives, assess.build(docs, skill_set, primitives).adjustments)
    cands = fusion.score(primitives, alpha=config.DEFAULT_ALPHA)

    format_ids = {p.stem for p in paths}
    by_id = {c.doc_id: c for c in cands}
    docs = [d for d in docs if d.doc_id in format_ids]
    cands = [c for c in cands if c.doc_id in format_ids]
    print(f"  scored inside the {len(primitives)}-candidate pool\n")
    print(f"  {'layout':<12} {'rank':>5} {'score':>7} {'required':>9} "
          f"{'sections':>9} {'chunks':>7}  engine")
    for doc in docs:
        c = by_id[doc.doc_id]
        print(f"  {doc.doc_id:<12} {c.rank:5} {c.score:7.1f} "
              f"{c.primitives.req_coverage:8.0%} {len(doc.sections):9} "
              f"{len(doc.chunks):7}  {doc.engine}")
    print()

    # --- 1. every layout is readable -----------------------------------------
    unreadable = [d.doc_id for d in docs if not d.text.strip()]
    record("1. every layout produced text", not unreadable,
           f"{len(docs) - len(unreadable)}/{len(docs)} readable"
           + (f", failed: {unreadable}" if unreadable else ""))

    # --- 2. sections found in every layout -----------------------------------
    thin = [(d.doc_id, len(d.sections)) for d in docs if len(d.sections) < MIN_SECTIONS]
    record(f"2. >= {MIN_SECTIONS} sections in every layout", not thin,
           f"min {min(len(d.sections) for d in docs)} sections"
           + (f", thin: {thin}" if thin else ""))

    # --- 3. the two-column layout was actually repaired ----------------------
    twocol = next((d for d in docs if d.doc_id == "twocolumn"), None)
    if twocol is None:
        record("3. two-column layout repaired", WARN, "no twocolumn fixture")
    else:
        record("3. two-column layout repaired", "columns" in twocol.engine,
               f"engine={twocol.engine}")

    # --- 4. score spread ------------------------------------------------------
    scores = [c.score for c in cands]
    spread = max(scores) - min(scores)
    hi = max(cands, key=lambda c: c.score)
    lo = min(cands, key=lambda c: c.score)
    record(f"4. score spread (ideal <= {IDEAL_SCORE_SPREAD:.0f})",
           tiered(spread, IDEAL_SCORE_SPREAD, MAX_SCORE_SPREAD),
           f"{spread:.1f} points ({lo.doc_id} {lo.score:.1f} -> {hi.doc_id} {hi.score:.1f})")

    # --- 4b. rank spread ------------------------------------------------------
    # The number a recruiter acts on. Six identical people should land together.
    ranks = [c.rank for c in cands]
    rank_spread = max(ranks) - min(ranks)
    record(f"4b. rank spread (ideal <= {IDEAL_RANK_SPREAD})",
           tiered(rank_spread, IDEAL_RANK_SPREAD, MAX_RANK_SPREAD),
           f"{rank_spread} places (#{min(ranks)} to #{max(ranks)} of {len(primitives)})")

    # --- 5. required coverage spread -----------------------------------------
    covs = [c.primitives.req_coverage for c in cands]
    cov_spread = max(covs) - min(covs)
    record(f"5. required coverage spread <= {MAX_COVERAGE_SPREAD:.0%}",
           cov_spread <= MAX_COVERAGE_SPREAD, f"{cov_spread:.1%}")

    # --- 6. the same skills were found in each ------------------------------
    # The real question behind all of this: does the engine see the same person?
    matched = {
        d.doc_id: {c.skill_id for c in by_id[d.doc_id].primitives.cells
                   if c.status in ("MATCHED", "INFERRED")}
        for d in docs
    }
    baseline = matched.get("classic", set())
    drift = {k: sorted(baseline ^ v) for k, v in matched.items() if v != baseline}
    record("6. same skills found in every layout", not drift,
           "identical skill sets" if not drift
           else f"{len(drift)} layouts differ: "
                + "; ".join(f"{k}: {v}" for k, v in list(drift.items())[:3]))

    failed = [r for r in results if r[1] == FAIL]
    warned = [r for r in results if r[1] == WARN]
    clean = len(results) - len(failed) - len(warned)

    print(f"\n{clean}/{len(results)} clean"
          + (f", {len(warned)} within tolerance" if warned else "")
          + (f", {len(failed)} failed" if failed else ""))

    if failed:
        print("\nFAILED:")
        for name, _, detail in failed:
            print(f"  - {name}: {detail}")
        return 1

    if warned:
        print("\nWithin tolerance, not yet ideal:")
        for name, _, detail in warned:
            print(f"  - {name}: {detail}")
        print("\n  Known cause: continuous prose gives the semantic channel longer,")
        print("  richer chunks than the same facts as bullets, so it scores a few")
        print("  points high. Disclosed rather than tuned away — suppressing it")
        print("  would mean penalising context, which is the signal that channel")
        print("  exists to read.")

    print("\nThe engine finds the same skills in every layout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
