# tests/test_dataset_registry.py
#
# Deterministic dataset-registry tests. No LLM, no network, no data files read.

from src.engine.dataset_registry import (
    DATASET_SOURCES,
    demo_safe_sources,
    is_private_path,
    label_for_path,
    source_for_path,
)

_EXPECTED_KEYS = {
    "resumes_generated", "resumes_linkedin", "resumes_kaggle", "resumes_private",
    "jd_generated_international", "jd_public_international", "jd_public_local",
    "jd_private_company",
}


def test_registry_has_all_expected_sources():
    keys = {s.key for s in DATASET_SOURCES}
    assert keys == _EXPECTED_KEYS


def test_private_sources_are_not_demo_safe():
    for s in DATASET_SOURCES:
        if "private" in s.path:
            assert s.demo_safe is False
            assert s.sensitivity == "high"


def test_generated_sources_are_demo_safe():
    gen = {s.key: s for s in DATASET_SOURCES}
    assert gen["resumes_generated"].demo_safe is True
    assert gen["jd_generated_international"].demo_safe is True


def test_public_and_sensitive_categorization():
    by_key = {s.key: s for s in DATASET_SOURCES}
    # LinkedIn + Kaggle resume sets are sensitive and not demo-safe.
    assert by_key["resumes_linkedin"].demo_safe is False
    assert by_key["resumes_kaggle"].demo_safe is False
    # Public scraped JDs are demo-safe (job postings, not personal CVs).
    assert by_key["jd_public_international"].demo_safe is True
    assert by_key["jd_public_local"].demo_safe is True


def test_source_for_path_matches_specific_folders():
    assert source_for_path("data/raw/resumes/generated_samples/cv1.pdf").key == "resumes_generated"
    assert source_for_path("data/raw/resumes/linkedin_profiles/cv1.pdf").key == "resumes_linkedin"
    assert source_for_path(
        "data/raw/resumes/public_datasets/kaggle/x.pdf").key == "resumes_kaggle"
    assert source_for_path("data/private/real_resumes/cv_orig1.pdf").key == "resumes_private"
    assert source_for_path(
        "data/raw/job_descriptions/public_scraped/local/jd.json").key == "jd_public_local"
    assert source_for_path("nowhere/random.pdf") is None


def test_label_for_path():
    assert label_for_path("data/raw/resumes/generated_samples/c.pdf") == "Generated CV"
    assert label_for_path("data/raw/job_descriptions/public_scraped/local/j.json") == "Public JD · Local"
    assert label_for_path("unknown/x.pdf") == "Unknown source"


def test_is_private_path():
    assert is_private_path("data/private/real_resumes/cv.pdf") is True
    assert is_private_path("data/uploads/candidate_pool/files/x.pdf") is True
    assert is_private_path("data/raw/resumes/generated_samples/cv.pdf") is False


def test_demo_safe_sources_exclude_private():
    safe = demo_safe_sources()
    assert all(s.demo_safe for s in safe)
    assert all("private" not in s.path for s in safe)
    assert {s.key for s in demo_safe_sources("resume")} == {"resumes_generated"}
