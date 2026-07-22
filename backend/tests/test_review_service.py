"""Unit tests for the human review service layer (#23).

Pure tests (no DB)
------------------
Tests for ``_apply_observation_fields`` cover the setattr loop in isolation:
  - known fields are applied to the Observation instance
  - unknown fields are silently ignored
  - None values for known fields are written through (nullable columns accept them)

DB-backed tests (accept / reject / flag)
-----------------------------------------
These require a live PostgreSQL session and are skipped in unit-test runs.
See the skip markers below for what each test would exercise.
"""
import pytest

from app.services.m4_annotation.review_service import _apply_observation_fields


# ---------------------------------------------------------------------------
# Minimal stub that mimics an Observation instance for pure unit tests.
# We do NOT import the real ORM model here to keep these tests DB-free.
# ---------------------------------------------------------------------------

class _ObsStub:
    """Stub with a subset of real Observation column names."""
    surface_confirmed: str | None = None
    native_step: str | None = None
    capture_context: str | None = None
    mapped_journey_stage: str | None = None


# ---------------------------------------------------------------------------
# Pure tests for _apply_observation_fields
# ---------------------------------------------------------------------------

class TestApplyObservationFields:
    def test_known_fields_are_applied(self):
        obs = _ObsStub()
        _apply_observation_fields(obs, {
            "surface_confirmed": "checkout",
            "native_step": "step_3",
        })
        assert obs.surface_confirmed == "checkout"
        assert obs.native_step == "step_3"

    def test_unknown_fields_are_ignored(self):
        obs = _ObsStub()
        # "nonexistent_field" and "another_bogus_key" have no matching attribute.
        _apply_observation_fields(obs, {
            "surface_confirmed": "settings",
            "nonexistent_field": "should_be_ignored",
            "another_bogus_key": 12345,
        })
        assert obs.surface_confirmed == "settings"
        assert not hasattr(obs, "nonexistent_field")
        assert not hasattr(obs, "another_bogus_key")

    def test_none_values_are_written_for_known_fields(self):
        obs = _ObsStub()
        obs.surface_confirmed = "old_value"
        _apply_observation_fields(obs, {"surface_confirmed": None})
        # Explicit None should overwrite the old value.
        assert obs.surface_confirmed is None

    def test_empty_dict_leaves_obs_unchanged(self):
        obs = _ObsStub()
        obs.surface_confirmed = "dashboard"
        _apply_observation_fields(obs, {})
        assert obs.surface_confirmed == "dashboard"

    def test_multiple_known_fields_applied_together(self):
        obs = _ObsStub()
        _apply_observation_fields(obs, {
            "surface_confirmed": "onboarding",
            "capture_context": "screenshot",
            "mapped_journey_stage": "activation",
        })
        assert obs.surface_confirmed == "onboarding"
        assert obs.capture_context == "screenshot"
        assert obs.mapped_journey_stage == "activation"

    def test_mix_of_known_and_unknown_fields(self):
        obs = _ObsStub()
        _apply_observation_fields(obs, {
            "native_step": "step_1",
            "totally_fake_column": "ignored",
            "capture_context": "video",
        })
        assert obs.native_step == "step_1"
        assert obs.capture_context == "video"
        assert not hasattr(obs, "totally_fake_column")


# ---------------------------------------------------------------------------
# DB-backed tests (skipped — require PostgreSQL)
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason=(
        "DB integration test: requires a live PostgreSQL session with the "
        "ux-benchmarks schema (assets, observations tables).  Run manually "
        "against a test DB; not suitable for the unit-test suite."
    )
)
def test_accept_asset_creates_observation_and_recomputes():
    """
    Given a persisted Asset,
    when accept_asset is called with observation_fields containing known keys,
    then an Observation row is inserted with those fields set,
          accepted_by / accepted_at are stamped correctly,
          recompute_coverage is triggered for the same (cell, competitor),
          and the returned Observation has a valid UUID id.
    """
    raise NotImplementedError("Implement with a test DB fixture")


@pytest.mark.skip(
    reason=(
        "DB integration test: requires a live PostgreSQL session.  "
        "See test_accept_asset_creates_observation_and_recomputes."
    )
)
def test_accept_asset_raises_not_found_for_missing_id():
    """
    Given a UUID that does not correspond to any Asset row,
    when accept_asset is called,
    then AppError(code='NOT_FOUND', status_code=404) is raised.
    """
    raise NotImplementedError("Implement with a test DB fixture")


@pytest.mark.skip(
    reason=(
        "DB integration test: requires a live PostgreSQL session.  "
        "See test_accept_asset_creates_observation_and_recomputes."
    )
)
def test_reject_asset_sets_is_superseded():
    """
    Given a persisted Asset with is_superseded=False,
    when reject_asset is called,
    then asset.is_superseded is True after commit,
         the asset row is retained (not deleted),
         and get_shortlist no longer returns that asset.
    """
    raise NotImplementedError("Implement with a test DB fixture")


@pytest.mark.skip(
    reason=(
        "DB integration test: requires a live PostgreSQL session.  "
        "See test_accept_asset_creates_observation_and_recomputes."
    )
)
def test_flag_asset_sets_is_superseded_and_logs_warning():
    """
    Given a persisted Asset,
    when flag_asset is called with a note,
    then asset.is_superseded is True after commit,
         a WARNING log entry containing the note is emitted,
         and the returned asset is the refreshed ORM object.
    """
    raise NotImplementedError("Implement with a test DB fixture")


@pytest.mark.skip(
    reason=(
        "DB integration test: requires a live PostgreSQL session.  "
        "See test_accept_asset_creates_observation_and_recomputes."
    )
)
def test_get_shortlist_excludes_superseded_assets():
    """
    Given two Assets for the same (cell, competitor) where one is superseded,
    when get_shortlist is called,
    then only the non-superseded asset is returned.
    """
    raise NotImplementedError("Implement with a test DB fixture")
