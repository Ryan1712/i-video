from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import AuditLog, SiteSetting, User
from saas.security import create_access_token


def _admin_token(db_session):
    admin = User(email="settingsadmin@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()
    return admin, create_access_token(admin.id, "test-secret-test-secret")


def test_list_settings_empty_by_default(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    client = TestClient(app)

    response = client.get("/admin/settings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == []
    app.dependency_overrides.clear()


def test_set_setting_creates_and_audits(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    client = TestClient(app)

    response = client.put(
        "/admin/settings/messenger_page_id", json={"value": "1234567"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert db_session.query(SiteSetting).filter_by(key="messenger_page_id").one().value == "1234567"
    assert db_session.query(AuditLog).filter_by(action="setting.update").one() is not None
    app.dependency_overrides.clear()


def test_update_setting_overwrites_existing_value(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    db_session.add(SiteSetting(key="zalo_oa_id", value="old"))
    db_session.commit()
    client = TestClient(app)

    response = client.put(
        "/admin/settings/zalo_oa_id", json={"value": "new"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert db_session.query(SiteSetting).filter_by(key="zalo_oa_id").one().value == "new"
    app.dependency_overrides.clear()
