"""Tests for per-job stale reconciliation limits."""

from app.jobs.stale_config import stale_after_seconds_for


class _JobWithLimit:
    max_running_seconds = 600


class _JobNoReconcile:
    max_running_seconds = 0


class _JobDefault:
    max_running_seconds = None


def test_stale_after_seconds_uses_job_class_limit(monkeypatch):
    monkeypatch.setattr("app.jobs.stale_config.get_job_class", lambda _t: _JobWithLimit)
    assert stale_after_seconds_for("any") == 600


def test_stale_after_seconds_disabled_when_zero(monkeypatch):
    monkeypatch.setattr("app.jobs.stale_config.get_job_class", lambda _t: _JobNoReconcile)
    assert stale_after_seconds_for("any") is None


def test_stale_after_seconds_falls_back_to_global(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("app.jobs.stale_config.get_job_class", lambda _t: _JobDefault)
    monkeypatch.setattr(
        "app.jobs.stale_config.global_settings",
        SimpleNamespace(jobs_stale_after_seconds=7200),
    )
    assert stale_after_seconds_for("any") == 7200
