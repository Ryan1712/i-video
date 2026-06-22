from saas.audit import log_action
from saas.models import AuditLog, User


def test_log_action_writes_audit_row(db_session):
    admin = User(email="admin@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()

    entry = log_action(
        db_session, actor=admin, action="plan.create", target_type="plan", target_id=7,
        before=None, after={"name": "Pro", "price_cents": 199000},
    )

    assert entry.id is not None
    fetched = db_session.query(AuditLog).one()
    assert fetched.actor_user_id == admin.id
    assert fetched.actor_role == "admin"
    assert fetched.action == "plan.create"
    assert fetched.target_type == "plan"
    assert fetched.target_id == 7
    assert fetched.before_data is None
    assert fetched.after_data == {"name": "Pro", "price_cents": 199000}


def test_log_action_records_ip_address(db_session):
    admin = User(email="admin2@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()

    entry = log_action(
        db_session, actor=admin, action="admin.login", target_type="user", target_id=admin.id,
        ip_address="127.0.0.1",
    )

    assert entry.ip_address == "127.0.0.1"
