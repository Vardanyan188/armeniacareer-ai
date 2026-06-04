# src/evaluation/parsing_eval.py
#
# Offline evaluation harness for the deterministic parsing utilities.
# Runs section detection, language detection, parsing-quality banding, and date
# range parsing over a fixture set and reports aggregate metrics.
#
# Deterministic, no LLM, no network.

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from src.preprocessing.date_normalizer import parse_date_range
from src.preprocessing.language_utils import detect_languages
from src.preprocessing.parsing_quality import assess_parsing_quality
from src.preprocessing.section_detector import detected_section_labels

PathLike = Union[str, Path]

_DEFAULT_CASES_DIR = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "cv_parsing_cases"
)


@dataclass
class EvalReport:
    n_cases: int = 0
    n_date_cases: int = 0
    section_recall: float = 0.0
    band_accuracy: float = 0.0
    language_accuracy: float = 0.0
    date_parse_rate: float = 0.0
    per_case: List[dict] = field(default_factory=list)
    date_results: List[dict] = field(default_factory=list)


def _recall(detected: List[str], expected: List[str]) -> float:
    if not expected:
        return 1.0
    hits = sum(1 for s in expected if s in detected)
    return hits / len(expected)


def run_parsing_eval(cases_dir: Optional[PathLike] = None) -> EvalReport:
    """Runs the parsing evaluation over `cases_dir` (defaults to the fixture set)."""
    base = Path(cases_dir) if cases_dir is not None else _DEFAULT_CASES_DIR
    spec = json.loads((base / "expectations.json").read_text(encoding="utf-8"))

    cases = spec.get("cases", [])
    per_case: List[dict] = []
    recall_sum = 0.0
    band_hits = 0
    lang_hits = 0

    for case in cases:
        text = (base / case["file"]).read_text(encoding="utf-8")
        ext = Path(case["file"]).suffix
        detected_sections = detected_section_labels(text)
        report = assess_parsing_quality(text, source_ext=ext)
        detected_languages = detect_languages(text)

        expected_sections = case.get("expected_sections", [])
        expected_languages = case.get("expected_languages", [])
        expected_band = case.get("expected_band")

        rec = _recall(detected_sections, expected_sections)
        band_ok = (report.extraction_quality_band == expected_band)
        lang_ok = all(l in detected_languages for l in expected_languages)

        recall_sum += rec
        band_hits += int(band_ok)
        lang_hits += int(lang_ok)

        per_case.append({
            "file": case["file"],
            "section_recall": round(rec, 3),
            "detected_sections": detected_sections,
            "band": report.extraction_quality_band,
            "band_ok": band_ok,
            "detected_languages": detected_languages,
            "language_ok": lang_ok,
        })

    date_cases = spec.get("date_cases", [])
    date_results: List[dict] = []
    date_hits = 0
    for dc in date_cases:
        rng = parse_date_range(dc["input"])
        start_ok = rng.start is not None and rng.start.year == dc["start_year"]
        current_ok = rng.is_current == dc["is_current"]
        ok = start_ok and current_ok
        date_hits += int(ok)
        date_results.append({
            "input": dc["input"],
            "start_year": rng.start.year if rng.start else None,
            "is_current": rng.is_current,
            "ok": ok,
        })

    n = len(cases)
    nd = len(date_cases)
    return EvalReport(
        n_cases=n,
        n_date_cases=nd,
        section_recall=round(recall_sum / n, 3) if n else 0.0,
        band_accuracy=round(band_hits / n, 3) if n else 0.0,
        language_accuracy=round(lang_hits / n, 3) if n else 0.0,
        date_parse_rate=round(date_hits / nd, 3) if nd else 0.0,
        per_case=per_case,
        date_results=date_results,
    )


def main() -> None:  # pragma: no cover - manual/CLI use
    report = run_parsing_eval()
    print("ArmeniaCareer AI — parsing evaluation")
    print("=" * 50)
    print(f"Cases: {report.n_cases} | Date cases: {report.n_date_cases}")
    print(f"Section recall : {report.section_recall}")
    print(f"Band accuracy  : {report.band_accuracy}")
    print(f"Language acc.  : {report.language_accuracy}")
    print(f"Date parse rate: {report.date_parse_rate}")
    print("-" * 50)
    for row in report.per_case:
        print(f"  {row['file']:<22} recall={row['section_recall']} "
              f"band={row['band']}({'ok' if row['band_ok'] else 'x'}) "
              f"langs={row['detected_languages']}")
    for row in report.date_results:
        print(f"  {row['input']:<28} -> {row['start_year']} "
              f"current={row['is_current']} {'ok' if row['ok'] else 'x'}")


if __name__ == "__main__":
    main()
