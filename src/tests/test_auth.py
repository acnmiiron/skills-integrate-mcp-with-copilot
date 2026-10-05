import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.app import app, activities


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-signing-secret-that-is-at-least-32-chars")
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "administrator-password")
    monkeypatch.setenv("STAFF_DATABASE_PATH", str(tmp_path / "staff.sqlite3"))
    activities["Chess Club"]["participants"] = ["michael@mergington.edu"]
    activities["Programming Class"]["participants"] = ["emma@mergington.edu"]
    with TestClient(app) as test_client:
        yield test_client


def login(client, username, password):
    response = client.post(
        "/auth/token",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_public_signup_and_staff_only_unregister(client):
    response = client.post(
        "/activities/Chess Club/signup",
        params={"email": "student@mergington.edu"},
    )
    assert response.status_code == 200

    response = client.delete(
        "/activities/Chess Club/unregister",
        params={"email": "student@mergington.edu"},
    )
    assert response.status_code == 401


def test_admin_manages_organizers_and_passwords_are_hashed(client, tmp_path):
    admin_headers = login(client, "admin", "administrator-password")
    created = client.post(
        "/staff/organizers",
        headers=admin_headers,
        json={
            "username": "chess-coach",
            "password": "organizer-password",
            "assignments": ["Chess Club"],
        },
    )
    assert created.status_code == 201
    assert created.json()["assignments"] == ["Chess Club"]

    with sqlite3.connect(tmp_path / "staff.sqlite3") as connection:
        password_hash = connection.execute(
            "SELECT password_hash FROM staff_users WHERE username = 'chess-coach'"
        ).fetchone()[0]
    assert password_hash != "organizer-password"
    assert ":" in password_hash

    organizer_headers = login(client, "chess-coach", "organizer-password")
    allowed = client.delete(
        "/activities/Chess Club/unregister",
        params={"email": "michael@mergington.edu"},
        headers=organizer_headers,
    )
    assert allowed.status_code == 200

    forbidden = client.delete(
        "/activities/Programming Class/unregister",
        params={"email": "emma@mergington.edu"},
        headers=organizer_headers,
    )
    assert forbidden.status_code == 403

    updated = client.patch(
        "/staff/organizers/chess-coach",
        headers=admin_headers,
        json={"assignments": ["Programming Class"]},
    )
    assert updated.status_code == 200
    assert updated.json()["assignments"] == ["Programming Class"]

    deactivated = client.delete(
        "/staff/organizers/chess-coach",
        headers=admin_headers,
    )
    assert deactivated.status_code == 200
    assert client.get("/auth/me", headers=organizer_headers).status_code == 401


def test_organizer_cannot_manage_staff_accounts(client):
    admin_headers = login(client, "admin", "administrator-password")
    created = client.post(
        "/staff/organizers",
        headers=admin_headers,
        json={
            "username": "activity-coach",
            "password": "organizer-password",
            "assignments": [],
        },
    )
    assert created.status_code == 201

    organizer_headers = login(client, "activity-coach", "organizer-password")
    assert client.get(
        "/staff/organizers",
        headers=organizer_headers,
    ).status_code == 403
    assert client.post(
        "/staff/organizers",
        headers=organizer_headers,
        json={
            "username": "another-coach",
            "password": "another-organizer-password",
            "assignments": [],
        },
    ).status_code == 403


def test_assignments_must_reference_existing_activities(client):
    admin_headers = login(client, "admin", "administrator-password")
    response = client.post(
        "/staff/organizers",
        headers=admin_headers,
        json={
            "username": "invalid-coach",
            "password": "organizer-password",
            "assignments": ["Not an activity"],
        },
    )
    assert response.status_code == 400


def test_invalid_staff_credentials_are_rejected(client):
    response = client.post(
        "/auth/token",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert response.status_code == 401
