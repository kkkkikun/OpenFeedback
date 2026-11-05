"""Tests for the public submission endpoint."""

from __future__ import annotations

import io
import json

import pytest


def png_bytes() -> bytes:
    """A minimal valid PNG."""
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def payload(**overrides) -> dict:
    base = {
        "appId": "localpixt",
        "submissionId": "sub-abcdef123456",
        "type": "bug",
        "title": "闪退了",
        "description": "打开设置页就闪退",
        "appVersion": "1.0.0",
    }
    base.update(overrides)
    return base


def submit(client, meta: dict, files=None):
    return client.post(
        "/api/v1/feedback",
        data={"payload": json.dumps(meta)},
        files=files or [],
    )


def test_health_is_public(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_submit_and_store(client, app_row):
    response = submit(client, payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["duplicate"] is False
    assert body["feedback_id"] > 0


def test_submit_requires_description(client, app_row):
    response = submit(client, payload(description="   "))
    assert response.status_code == 422


def test_submit_rejects_unknown_app(client, app_row):
    response = submit(client, payload(appId="does-not-exist"))
    assert response.status_code == 404


def test_submit_rejects_invalid_type(client, app_row):
    response = submit(client, payload(type="nonsense"))
    assert response.status_code == 422


def test_submit_rejects_oversized_description(client, app_row):
    response = submit(client, payload(description="x" * 9000))
    assert response.status_code == 422


def test_submit_rejects_bad_json(client, app_row):
    response = client.post("/api/v1/feedback", data={"payload": "{not json"})
    assert response.status_code == 400


def test_duplicate_submission_id_is_idempotent(client, app_row):
    first = submit(client, payload(submissionId="dup-12345678"))
    assert first.status_code == 200
    second = submit(client, payload(submissionId="dup-12345678"))
    assert second.status_code == 200
    body = second.json()
    assert body["duplicate"] is True
    assert body["feedback_id"] == first.json()["feedback_id"]


def test_legacy_oit_categories_are_accepted(client, app_row):
    """OIT-Net-Portal sends suggestion/issue/other today."""
    for legacy, expected in [("issue", "bug"), ("suggestion", "feature"), ("other", "other")]:
        response = submit(
            client, payload(submissionId=f"legacy-{legacy}-1234", type=legacy)
        )
        assert response.status_code == 200, response.text

    from sqlalchemy import select

    from app.db import session_scope
    from app.models import Feedback

    with session_scope() as session:
        rows = session.scalars(
            select(Feedback).where(Feedback.submission_id.like("legacy-%"))
        ).all()
        by_id = {row.submission_id: row.type for row in rows}
    assert by_id["legacy-issue-1234"] == "bug"
    assert by_id["legacy-suggestion-1234"] == "feature"


def test_attachments_are_stored(client, app_row):
    response = submit(
        client,
        payload(submissionId="att-12345678"),
        files=[("attachments", ("shot.png", png_bytes(), "image/png"))],
    )
    assert response.status_code == 200, response.text

    from sqlalchemy import select

    from app.db import session_scope
    from app.models import FeedbackAttachment

    with session_scope() as session:
        row = session.scalar(
            select(FeedbackAttachment).where(FeedbackAttachment.feedback_id == response.json()["feedback_id"])
        )
        assert row is not None
        assert row.mime_type == "image/png"
        assert row.sha256


def test_non_image_attachment_is_rejected(client, app_row):
    response = submit(
        client,
        payload(submissionId="bad-att-1234"),
        files=[("attachments", ("evil.png", b"#!/bin/sh\nrm -rf /", "image/png"))],
    )
    assert response.status_code == 422


def test_too_many_attachments_are_rejected(client, app_row):
    files = [
        ("attachments", (f"shot{i}.png", png_bytes(), "image/png")) for i in range(4)
    ]
    response = submit(client, payload(submissionId="many-att-1234"), files=files)
    assert response.status_code == 422


def test_disabled_app_is_rejected(client, app_row):
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import App

    with session_scope() as session:
        row = session.scalar(select(App).where(App.app_id == "localpixt"))
        row.enabled = False
    try:
        response = submit(client, payload(submissionId="disabled-123456"))
        assert response.status_code == 403
    finally:
        with session_scope() as session:
            row = session.scalar(select(App).where(App.app_id == "localpixt"))
            row.enabled = True


def test_rate_limit_blocks_excess_submissions(client, app_row):
    """The per-hour cap stops a runaway client."""
    from app.ratelimit import submission_limiter

    submission_limiter.reset()
    settings_cap = get_limit()
    accepted = 0
    for index in range(settings_cap + 3):
        response = submit(client, payload(submissionId=f"rl-{index:04d}-abcd"))
        if response.status_code == 200:
            accepted += 1
        else:
            assert response.status_code == 429
            break
    assert accepted == settings_cap
    submission_limiter.reset()


def get_limit() -> int:
    from app.config import get_settings

    return get_settings().submissions_per_hour
