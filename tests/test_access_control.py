# tests/test_access_control.py
#
# Verifies the candidate / recruiter / shared view separation.
# In-memory only: no agents, no LLM, no data/raw access.

import json

from src.engine.access_control import (
    get_candidate_view,
    get_recruiter_view,
    get_shared_view,
)

from tests._payload_factory import MOTIVATION_TEXT, RED_FLAG_TEXT, make_payload


def _dump(view: dict) -> str:
    """Serialise a view (which may contain pydantic objects) to a JSON string."""
    def _default(o):
        if hasattr(o, "model_dump"):
            return o.model_dump()
        return str(o)
    return json.dumps(view, default=_default, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Candidate view
# ---------------------------------------------------------------------------

def test_candidate_view_contains_coaching_fields():
    view = get_candidate_view(make_payload())
    assert "candidate_perspective" in view
    assert "composite_score_percentage" in view
    assert "dimensional_scores" in view
    assert len(view["dimensional_scores"]) == 7
    assert "matched_skills" in view and "missing_critical" in view


def test_candidate_view_hides_recruiter_only_data():
    view = get_candidate_view(make_payload())
    # No recruiter perspective object, hire recommendation, verification points,
    # red flags, or raw bias details.
    assert "recruiter_perspective" not in view
    assert "hire_recommendation" not in view
    assert "verification_points" not in view
    assert "evaluation_integrity_risk" not in view

    blob = _dump(view)
    assert RED_FLAG_TEXT not in blob          # red flags not leaked
    assert "must_ask" not in blob             # verification points not leaked


# ---------------------------------------------------------------------------
# Recruiter view
# ---------------------------------------------------------------------------

def test_recruiter_view_contains_analytical_fields():
    view = get_recruiter_view(make_payload())
    assert "recruiter_perspective" in view
    assert "dimensional_analysis" in view
    assert "evaluation_integrity_risk" in view
    assert "hard_floor_applied" in view


def test_recruiter_view_hides_candidate_coaching():
    view = get_recruiter_view(make_payload())
    assert "candidate_perspective" not in view
    blob = _dump(view)
    assert MOTIVATION_TEXT not in blob        # motivational framing not leaked


# ---------------------------------------------------------------------------
# Shared view
# ---------------------------------------------------------------------------

def test_shared_view_is_neutral():
    view = get_shared_view(make_payload())
    assert "dimensional_analysis" in view
    assert "skills_ontology_summary" in view
    assert "semantic_analysis_summary" in view
    assert "governance_status" in view

    # No perspectives, no hire recommendation, no raw bias signal.
    assert "candidate_perspective" not in view
    assert "recruiter_perspective" not in view
    blob = _dump(view)
    assert MOTIVATION_TEXT not in blob
    assert RED_FLAG_TEXT not in blob


def test_shared_skills_summary_shape():
    view = get_shared_view(make_payload())
    summary = view["skills_ontology_summary"]
    assert summary["total_required_skills"] == 4
    assert summary["matched_count"] == 2
    assert summary["coverage_ratio"] == 0.5
