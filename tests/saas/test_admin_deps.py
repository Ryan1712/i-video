import pytest
from fastapi import HTTPException

from saas.admin_deps import require_admin
from saas.models import User


def test_require_admin_allows_admin():
    admin = User(email="a@x.com", password_hash="h", role="admin")
    assert require_admin(admin) is admin


def test_require_admin_rejects_non_admin():
    user = User(email="u@x.com", password_hash="h", role="user")
    with pytest.raises(HTTPException) as exc_info:
        require_admin(user)
    assert exc_info.value.status_code == 403
