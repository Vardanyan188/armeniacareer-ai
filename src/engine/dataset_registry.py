# src/engine/dataset_registry.py
#
# Deterministic registry of known local dataset sources (no LLM, no network).
#
# It describes WHERE each kind of CV/JD lives, how sensitive it is, and whether
# it is safe to show in Admin/Demo. The loader uses defensive path exclusion;
# the UI uses this registry to label files and to keep private data out of the
# demo selectors.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

PathLike = Union[str, Path]

# Sensitivity levels.
LOW = "low"
MEDIUM = "medium"
HIGH = "high"

# Path segments that must NEVER appear in demo listings.
PRIVATE_SEGMENTS = ("private", "uploads", "candidate_pool")


@dataclass(frozen=True)
class DatasetSource:
    key: str
    path: str            # repo-relative folder (posix)
    data_type: str       # "resume" | "job_description"
    sensitivity: str     # LOW | MEDIUM | HIGH
    demo_safe: bool
    label: str           # short UI label
    description: str


DATASET_SOURCES: List[DatasetSource] = [
    # ── Resumes ──────────────────────────────────────────────────────────────
    DatasetSource(
        key="resumes_generated",
        path="data/raw/resumes/generated_samples",
        data_type="resume", sensitivity=LOW, demo_safe=True,
        label="Generated CV",
        description="Generated/synthetic CVs — safe for demo.",
    ),
    DatasetSource(
        key="resumes_linkedin",
        path="data/raw/resumes/linkedin_profiles",
        data_type="resume", sensitivity=MEDIUM, demo_safe=False,
        label="LinkedIn/Profile",
        description="LinkedIn/profile-style CVs — may contain real people; internal only.",
    ),
    DatasetSource(
        key="resumes_kaggle",
        path="data/raw/resumes/public_datasets/kaggle",
        data_type="resume", sensitivity=MEDIUM, demo_safe=False,
        label="Kaggle/Public Dataset",
        description="Public Kaggle dataset CVs — review/sensitive; internal only.",
    ),
    DatasetSource(
        key="resumes_private",
        path="data/private/real_resumes",
        data_type="resume", sensitivity=HIGH, demo_safe=False,
        label="Private CV",
        description="Real human CVs — private, never shown in demo.",
    ),
    # ── Job descriptions ─────────────────────────────────────────────────────
    DatasetSource(
        key="jd_generated_international",
        path="data/raw/job_descriptions/generated_samples/international",
        data_type="job_description", sensitivity=LOW, demo_safe=True,
        label="Generated JD",
        description="Generated/mock job descriptions — safe for demo.",
    ),
    DatasetSource(
        key="jd_public_international",
        path="data/raw/job_descriptions/public_scraped/international",
        data_type="job_description", sensitivity=MEDIUM, demo_safe=True,
        label="Public JD · International",
        description="Public scraped international job postings.",
    ),
    DatasetSource(
        key="jd_public_local",
        path="data/raw/job_descriptions/public_scraped/local",
        data_type="job_description", sensitivity=MEDIUM, demo_safe=True,
        label="Public JD · Local",
        description="Public scraped local (Armenian market) job postings.",
    ),
    DatasetSource(
        key="jd_private_company",
        path="data/private/job_descriptions/company_private",
        data_type="job_description", sensitivity=HIGH, demo_safe=False,
        label="Private JD",
        description="Private/internal company job descriptions — never shown in demo.",
    ),
]

# Most-specific (longest path) first, for unambiguous matching.
_SORTED_SOURCES = sorted(DATASET_SOURCES, key=lambda s: len(s.path), reverse=True)


def _posix(path: PathLike) -> str:
    return str(path).replace("\\", "/").lower()


def source_for_path(path: PathLike) -> Optional[DatasetSource]:
    """Returns the dataset source whose folder contains `path`, or None."""
    p = _posix(path)
    for source in _SORTED_SOURCES:
        if source.path.lower() in p:
            return source
    return None


def label_for_path(path: PathLike) -> str:
    """Short UI label for a file path (e.g. 'Generated CV'), or 'Unknown source'."""
    source = source_for_path(path)
    return source.label if source else "Unknown source"


def is_private_path(path: PathLike) -> bool:
    """True if the path is under a private/uploads/candidate_pool location."""
    parts = {seg.lower() for seg in Path(path).parts}
    return bool(parts & set(PRIVATE_SEGMENTS))


def demo_safe_sources(data_type: Optional[str] = None) -> List[DatasetSource]:
    """Lists demo-safe sources, optionally filtered by data type."""
    return [
        s for s in DATASET_SOURCES
        if s.demo_safe and (data_type is None or s.data_type == data_type)
    ]
