"""Tests for admin authentication, the admin API, and access control."""

from __future__ import annotations

import json

from tests.test_public import payload, png_bytes, submit


def login(client, username="tester", password="test-password-123"):
    return client.post(
        "/api/v1/admin/login", json={"username": username, "password": password}
    )


def test_admin_api_requires_login(client):
    response = client.get("/api/v1/admin/feedback")
    assert response.status_code == 401


def test_login_succeeds_and_sets_cookie(client):
    response = login(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["username"] == "tester"
    assert body["csrfToken"]
    assert "of_admin_session" in response.cookies


def test_login_with_wrong_password_fails(client):
    response = login(client, password="wrong")
    assert response.status_code == 401


def test_login_with_unknown_user_fails(client):
    response = login(client, username="nobody")
    assert response.status_code == 401


def test_session_endpoint_reports_current_user(client, admin_login):
    response = client.get("/api/v1/admin/session")
    assert response.status_code == 200
    assert response.json()["username"] == "tester"


def test_list_feedback_requires_login(client, app_row):
    assert client.get("/api/v1/admin/feedback").status_code == 401


def test_list_feedback_after_login(client, app_row, admin_login):
    submit(client, payload(submissionId="admin-list-1234"))
    response = client.get("/api/v1/admin/feedback")
    assert response.status_code == 200
    body = response.json()
    assert any(item["id"] > 0 for item in body)


def test_feedback_list_filters_by_app(client, app_row, admin_login):
    submit(client, payload(submissionId="filter-app-1234", appId="localpixt"))
    response = client.get("/api/v1/admin/feedback", params={"appId": "localpixt"})
    assert response.status_code == 200
    assert all(item["app_id"] == "localpixt" for item in response.json())


def test_status_update_requires_csrf(client, app_row, admin_login):
    created = submit(client, payload(submissionId="csrf-status-1234")).json()
    response = client.patch(
        f"/api/v1/admin/feedback/{created['feedback_id']}", json={"status": "RESOLVED"}
    )
    assert response.status_code == 403


def test_status_update_with_csrf(client, app_row, admin_login):
    created = submit(client, payload(submissionId="csrf-ok-1234")).json()
    response = client.patch(
        f"/api/v1/admin/feedback/{created['feedback_id']}",
        json={"status": "RESOLVED"},
        headers={"X-CSRF-Token": admin_login},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "RESOLVED"


def test_status_update_rejects_unknown_status(client, app_row, admin_login):
    created = submit(client, payload(submissionId="csrf-bad-1234")).json()
    response = client.patch(
        f"/api/v1/admin/feedback/{created['feedback_id']}",
        json={"status": "NONSENSE"},
        headers={"X-CSRF-Token": admin_login},
    )
    assert response.status_code == 422


def test_add_note_with_csrf(client, app_row, admin_login):
    created = submit(client, payload(submissionId="note-12345678")).json()
    response = client.post(
        f"/api/v1/admin/feedback/{created['feedback_id']}/notes",
        json={"content": "内部备注内容"},
        headers={"X-CSRF-Token": admin_login},
    )
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "内部备注内容"


def test_add_note_requires_csrf(client, app_row, admin_login):
    created = submit(client, payload(submissionId="note-nocsrf-1234")).json()
    response = client.post(
        f"/api/v1/admin/feedback/{created['feedback_id']}/notes",
        json={"content": "x"},
    )
    assert response.status_code == 403


def test_attachment_download_requires_login(client, app_row, admin_login):
    created = submit(
        client,
        payload(submissionId="att-admin-1234"),
        files=[("attachments", ("shot.png", png_bytes(), "image/png"))],
    ).json()

    detail = client.get(f"/api/v1/admin/feedback/{created['feedback_id']}").json()
    attachment_id = detail["attachments"][0]["id"]

    # Logged in: the bytes come back.
    response = client.get(f"/api/v1/admin/attachments/{attachment_id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_attachment_download_blocked_when_anonymous(client, app_row, admin_login):
    created = submit(
        client,
        payload(submissionId="att-anon-1234"),
        files=[("attachments", ("shot.png", png_bytes(), "image/png"))],
    ).json()
    detail = client.get(f"/api/v1/admin/feedback/{created['feedback_id']}").json()
    attachment_id = detail["attachments"][0]["id"]

    client.post("/api/v1/admin/logout")
    response = client.get(f"/api/v1/admin/attachments/{attachment_id}")
    assert response.status_code == 401


def test_status_history_is_recorded(client, app_row, admin_login):
    created = submit(client, payload(submissionId="history-1234567")).json()
    client.patch(
        f"/api/v1/admin/feedback/{created['feedback_id']}",
        json={"status": "IN_PROGRESS"},
        headers={"X-CSRF-Token": admin_login},
    )
    detail = client.get(f"/api/v1/admin/feedback/{created['feedback_id']}").json()
    assert any(h["new_status"] == "IN_PROGRESS" for h in detail["status_history"])


def test_admin_page_requires_login(client):
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert "/admin/login" in response.headers["location"]


def test_admin_page_renders_after_login(client, admin_login):
    response = client.get("/admin")
    assert response.status_code == 200
    assert "OpenFeedback" in response.text


def test_logout_invalidates_session(client, admin_login):
    assert client.get("/api/v1/admin/session").status_code == 200
    client.post("/api/v1/admin/logout")
    assert client.get("/api/v1/admin/session").status_code == 401


def test_submission_id_is_visible_to_admins(client, app_row, admin_login):
    """后台必须能看到 submission_id。

    它是去重的依据：客户端离线补发时带同一个 submissionId，
    服务端据此返回原记录而不新建。看不到它就无法判断
    「这两条是不是同一次提交的重复」。
    """
    created = submit(client, payload(submissionId="visible-sub-id-1234")).json()
    feedback_id = created["feedback_id"]

    listing = client.get("/api/v1/admin/feedback").json()
    assert any(
        item["id"] == feedback_id and item["submission_id"] == "visible-sub-id-1234"
        for item in listing
    )

    detail = client.get(f"/api/v1/admin/feedback/{feedback_id}").json()
    assert detail["submission_id"] == "visible-sub-id-1234"


def test_admin_detail_page_shows_submission_id(client, app_row, admin_login):
    """详情页也要显示，否则浏览器里排查不了重复提交。"""
    created = submit(client, payload(submissionId="visible-in-page-1234")).json()
    response = client.get(f"/admin/feedback/{created['feedback_id']}")
    assert response.status_code == 200
    assert "visible-in-page-1234" in response.text
