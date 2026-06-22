import pytest
from fastapi.testclient import TestClient

from saas.db import Base, get_db
from saas.main import app


@pytest.fixture
def client(db_session_factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_signup_creates_user_and_returns_token(client):
    response = client.post("/auth/signup", json={"email": "new@example.com", "password": "pw12345"})

    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_signup_rejects_duplicate_email(client):
    client.post("/auth/signup", json={"email": "dup@example.com", "password": "pw12345"})
    response = client.post("/auth/signup", json={"email": "dup@example.com", "password": "other"})

    assert response.status_code == 400


def test_login_returns_token_for_correct_credentials(client):
    client.post("/auth/signup", json={"email": "login@example.com", "password": "correct-pw"})

    response = client.post("/auth/login", json={"email": "login@example.com", "password": "correct-pw"})

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_rejects_wrong_password(client):
    client.post("/auth/signup", json={"email": "login2@example.com", "password": "correct-pw"})

    response = client.post("/auth/login", json={"email": "login2@example.com", "password": "wrong-pw"})

    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post("/auth/login", json={"email": "ghost@example.com", "password": "x"})

    assert response.status_code == 401


def test_admin_login_is_audited(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    from fastapi.testclient import TestClient

    from saas.audit import log_action  # noqa: F401  (imported for readability of intent)
    from saas.db import get_db
    from saas.main import app
    from saas.models import AuditLog, User
    from saas.security import hash_password

    app.dependency_overrides[get_db] = lambda: db_session
    admin = User(email="adminlogin@x.com", password_hash=hash_password("pw"), role="admin")
    db_session.add(admin)
    db_session.commit()
    client = TestClient(app)

    response = client.post("/auth/login", json={"email": "adminlogin@x.com", "password": "pw"})

    assert response.status_code == 200
    entry = db_session.query(AuditLog).filter_by(action="admin.login").one()
    assert entry.actor_user_id == admin.id
    app.dependency_overrides.clear()
