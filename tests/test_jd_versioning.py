# tests/test_jd_versioning.py
#
# Deterministic tests for JD Refresh / Requirement Versioning (Phase 20).
# No LLM, no network, no data/raw dependency — all writes target tmp_path.

import json

import pytest

from src.engine.jd_versioning.diff import diff_versions
from src.engine.jd_versioning.models import (
    JDVersion,
    compute_raw_text_hash,
    create_jd_version,
    default_jd_id,
)
from src.engine.jd_versioning.store import (
    PrivateJDMisroutingError,
    list_versions,
    next_version_number,
    save_jd_version,
)
from src.schemas.canonical_payload import (
    JDEntities,
    SeniorityLevel,
    SkillCategory,
    SkillEntry,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _sk(name):
    return SkillEntry(raw_name=name, canonical_name=name, category=SkillCategory.TECHNICAL)


def _jd(
    *, required=None, preferred=None, responsibilities=None,
    seniority=SeniorityLevel.MID, years=2.0, role_title="Data Engineer",
):
    return JDEntities(
        role_title=role_title,
        required_skills=[_sk(s) for s in (required or [])],
        preferred_skills=[_sk(s) for s in (preferred or [])],
        responsibilities=responsibilities or [],
        required_seniority=seniority,
        required_experience_years=years,
    )


def _version(jd_entities, *, raw_text="job description text", source_type="generated",
             jd_id=None, version_number=1):
    return create_jd_version(
        raw_text=raw_text, jd_entities=jd_entities, source_type=source_type,
        jd_id=jd_id, version_number=version_number,
    )


# ---------------------------------------------------------------------------
# Model creation / identity
# ---------------------------------------------------------------------------

def test_jd_version_creation():
    v = _version(_jd(required=["Python", "SQL"]))
    assert len(v.raw_text_hash) == 64
    assert v.entities.required_skills == ["Python", "SQL"]
    assert v.version_id and v.version_number == 1
    assert "Python" in v.required_depth  # Phase-19 reuse populated required depth


def test_hash_identity_is_normalized():
    assert compute_raw_text_hash("Python and SQL") == compute_raw_text_hash("python   AND  sql")
    assert compute_raw_text_hash("Python") != compute_raw_text_hash("Python SQL")


def test_default_jd_id_generation():
    v = _version(_jd(role_title="Senior ML Engineer"), raw_text="abc")
    assert v.jd_id == default_jd_id("Senior ML Engineer", v.raw_text_hash)
    assert v.jd_id.startswith("senior-ml-engineer-")


def test_operator_jd_id_override():
    v = _version(_jd(role_title="Whatever"), jd_id="ROLE-2026-Q2")
    assert v.jd_id == "ROLE-2026-Q2"


# ---------------------------------------------------------------------------
# Diff — skills
# ---------------------------------------------------------------------------

def test_added_removed_required_skills():
    old = _version(_jd(required=["Python", "SQL"]))
    new = _version(_jd(required=["Python", "Docker"]))
    d = diff_versions(old, new)
    assert d.added_required_skills == ["Docker"]
    assert d.removed_required_skills == ["SQL"]


def test_added_removed_preferred_skills():
    old = _version(_jd(required=["Python"], preferred=["AWS"]))
    new = _version(_jd(required=["Python"], preferred=["GCP"]))
    d = diff_versions(old, new)
    assert d.added_preferred_skills == ["GCP"]
    assert d.removed_preferred_skills == ["AWS"]


# ---------------------------------------------------------------------------
# Diff — seniority / role / experience / responsibilities
# ---------------------------------------------------------------------------

def test_seniority_change_and_more_senior_flag():
    old = _version(_jd(required=["Python"], seniority=SeniorityLevel.MID))
    new = _version(_jd(required=["Python"], seniority=SeniorityLevel.SENIOR))
    d = diff_versions(old, new)
    assert d.seniority_changed is True
    assert d.became_more_senior is True


def test_role_title_change():
    old = _version(_jd(required=["Python"], role_title="Data Analyst"))
    new = _version(_jd(required=["Python"], role_title="Data Scientist"))
    d = diff_versions(old, new)
    assert d.role_title_changed is True
    assert d.old_role_title == "Data Analyst" and d.new_role_title == "Data Scientist"


def test_responsibilities_add_remove():
    old = _version(_jd(required=["Python"], responsibilities=["Build dashboards"]))
    new = _version(_jd(required=["Python"], responsibilities=["Build pipelines"]))
    d = diff_versions(old, new)
    assert d.responsibilities_added == ["Build pipelines"]
    assert d.responsibilities_removed == ["Build dashboards"]


def test_required_experience_change():
    old = _version(_jd(required=["Python"], years=2.0))
    new = _version(_jd(required=["Python"], years=5.0))
    d = diff_versions(old, new)
    assert d.required_experience_changed is True
    assert d.old_required_experience_years == 2.0 and d.new_required_experience_years == 5.0


# ---------------------------------------------------------------------------
# Diff — required depth
# ---------------------------------------------------------------------------

def test_required_depth_change_and_deployment_heavy():
    old = _version(_jd(
        required=["Python"], responsibilities=["Data analysis with Python and pandas"],
    ))
    new = _version(_jd(
        required=["Python"], responsibilities=["Deploy and monitor Python models"],
    ))
    d = diff_versions(old, new)
    changed = {c.skill: (c.old_depth, c.new_depth) for c in d.required_depth_changed}
    assert "Python" in changed
    assert changed["Python"] == ("Applied", "Deployment")
    assert "Python" in d.newly_required_depth_gaps
    assert d.became_more_deployment_heavy is True


def test_no_depth_change_not_deployment_heavy():
    old = _version(_jd(required=["Python"], responsibilities=["Data analysis with Python"]))
    new = _version(_jd(required=["Python"], responsibilities=["Data analysis with Python"]))
    d = diff_versions(old, new)
    assert d.newly_required_depth_gaps == []
    assert d.became_more_deployment_heavy is False


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_deterministic_diff():
    old = _version(_jd(required=["Python", "SQL"], responsibilities=["analysis with Python"]))
    new = _version(_jd(required=["Python", "Docker"], seniority=SeniorityLevel.SENIOR,
                       responsibilities=["Deploy Python models"]))
    from dataclasses import asdict
    assert asdict(diff_versions(old, new)) == asdict(diff_versions(old, new))


# ---------------------------------------------------------------------------
# Store — routing + privacy
# ---------------------------------------------------------------------------

def test_demo_safe_version_saves_to_raw(tmp_path):
    v = _version(_jd(required=["Python"]), source_type="generated")
    path = save_jd_version(v, base_dir=tmp_path)
    assert "raw" in path.parts and "private" not in path.parts
    assert not (tmp_path / "private").exists()
    assert len(list_versions(v.jd_id, private=False, base_dir=tmp_path)) == 1


def test_private_version_saves_only_to_private(tmp_path):
    v = _version(_jd(required=["Python"]), source_type="recruiter")  # private source
    path = save_jd_version(v, base_dir=tmp_path)
    assert "private" in path.parts
    assert "raw" not in path.parts
    assert not (tmp_path / "raw").exists()


def test_store_rejects_private_to_raw_misrouting(tmp_path):
    v = _version(_jd(required=["Python"]), source_type="recruiter")  # private
    with pytest.raises(PrivateJDMisroutingError):
        save_jd_version(v, base_dir=tmp_path, to_private=False)
    # Nothing leaked into the raw tree.
    assert not (tmp_path / "raw").exists()


def test_next_version_number_increments(tmp_path):
    v1 = _version(_jd(required=["Python"]), source_type="generated",
                  jd_id="role-x", version_number=1)
    save_jd_version(v1, base_dir=tmp_path)
    assert next_version_number("role-x", private=False, base_dir=tmp_path) == 2


def test_saved_snapshot_roundtrips(tmp_path):
    v = _version(_jd(required=["Python", "SQL"]), source_type="generated", jd_id="role-y")
    save_jd_version(v, base_dir=tmp_path)
    loaded = list_versions("role-y", private=False, base_dir=tmp_path)
    assert loaded and loaded[0].entities.required_skills == ["Python", "SQL"]
    # Snapshot JSON is well-formed.
    snap = tmp_path / "raw" / "role-y" / f"{v.version_id}.json"
    assert json.loads(snap.read_text(encoding="utf-8"))["jd_id"] == "role-y"


# ---------------------------------------------------------------------------
# No scoring coupling
# ---------------------------------------------------------------------------

def test_modules_do_not_import_scoring():
    import src.engine.jd_versioning.diff as diff_mod
    import src.engine.jd_versioning.store as store_mod
    import src.engine.jd_versioning.models as models_mod
    for mod in (diff_mod, store_mod, models_mod):
        assert not hasattr(mod, "scoring")
        assert not hasattr(mod, "DimensionalAnalysis")
