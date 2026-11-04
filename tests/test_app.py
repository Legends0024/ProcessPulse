import pytest

from app import create_app


@pytest.fixture()
def client():
    app = create_app("testing")
    with app.test_client() as test_client:
        yield test_client, app.config["AGENT_TOKEN"]


def metric_payload():
    return {
        "device": {"device_id": "test-device", "name": "Test Device"},
        "metrics": {
            "cpu_percent": 25.0,
            "memory_percent": 40.0,
            "disk_percent": 50.0,
            "process_count": 10,
            "uptime_seconds": 100,
            "processes": [],
            "gpu": {
                "available": False,
                "name": None,
                "utilization_percent": None,
                "memory_percent": None,
            },
        },
    }


def test_dashboard_and_static_assets(client):
    test_client, _ = client
    assert test_client.get("/").status_code == 200
    assert test_client.get("/static/js/dashboard.js").status_code == 200
    assert test_client.get("/static/assets/favicon.svg").status_code == 200


def test_metrics_requires_token_and_persists(client):
    test_client, token = client
    payload = metric_payload()

    assert test_client.post("/api/metrics", json=payload).status_code == 401
    response = test_client.post(
        "/api/metrics",
        json=payload,
        headers={"X-Agent-Token": token},
    )
    assert response.status_code == 201

    latest = test_client.get("/api/latest")
    assert latest.status_code == 200
    assert latest.get_json()["analysis"]["label"] in {"pending", "normal", "warning", "critical"}
    assert latest.get_json()["metric"]["gpu"]["available"] is False


def test_metrics_reject_invalid_values(client):
    test_client, token = client
    payload = metric_payload()
    payload["metrics"]["cpu_percent"] = 101

    response = test_client.post(
        "/api/metrics",
        json=payload,
        headers={"X-Agent-Token": token},
    )
    assert response.status_code == 400


def test_critical_process_termination_is_rejected(client):
    test_client, _ = client
    response = test_client.post(
        "/api/processes/1/terminate",
        json={"name": "explorer.exe"},
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert response.status_code == 403


def test_missing_process_termination_is_rejected(client):
    test_client, _ = client
    response = test_client.post(
        "/api/processes/999999999/terminate",
        json={"name": "not-running.exe"},
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert response.status_code == 404


def test_resource_patterns_wait_for_history(client):
    test_client, _ = client
    response = test_client.get("/api/patterns")
    assert response.status_code == 200
    assert response.get_json()["status"] == "insufficient_data"


def test_device_registration_issues_unique_credential(client):
    test_client, _ = client
    response = test_client.post(
        "/api/devices/register",
        json={"device_id": "registered-device", "name": "Registered PC"},
        headers={"X-Registration-Token": "test-registration-token"},
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["device_token"]
    assert "token_hash" not in body

    duplicate = test_client.post(
        "/api/devices/register",
        json={"device_id": "registered-device", "name": "Registered PC"},
        headers={"X-Registration-Token": "test-registration-token"},
    )
    assert duplicate.status_code == 409


def test_device_token_authentication_and_revocation(client):
    test_client, _ = client
    registration = test_client.post(
        "/api/devices/register",
        json={"device_id": "revocable-device", "name": "Revocable PC"},
        headers={"X-Registration-Token": "test-registration-token"},
    )
    token = registration.get_json()["device_token"]
    payload = metric_payload()
    payload["device"]["device_id"] = "revocable-device"

    accepted = test_client.post(
        "/api/metrics",
        json=payload,
        headers={"X-Device-Token": token},
    )
    assert accepted.status_code == 201

    revoked = test_client.post(
        "/api/devices/revocable-device/revoke",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert revoked.status_code == 200
    rejected = test_client.post(
        "/api/metrics",
        json=payload,
        headers={"X-Device-Token": token},
    )
    assert rejected.status_code == 401


def test_device_status_reports_offline_after_heartbeat_timeout(client):
    test_client, _ = client
    app = test_client.application
    registration = test_client.post(
        "/api/devices/register",
        json={"device_id": "offline-device", "name": "Offline PC"},
        headers={"X-Registration-Token": "test-registration-token"},
    )
    assert registration.status_code == 201
    with app.app_context():
        from backend.models import Device
        from datetime import datetime, timedelta

        device = Device.query.filter_by(device_id="offline-device").first()
        device.last_seen = datetime.utcnow() - timedelta(seconds=app.config["HEARTBEAT_TIMEOUT_SECONDS"] + 1)
        from backend.models import db
        db.session.commit()
    device = test_client.get("/api/devices/offline-device").get_json()
    assert device["status"] == "offline"
    assert device["is_online"] is False
