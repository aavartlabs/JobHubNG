import pytest
import requests

from jobhub_poc import config
from jobhub_poc.alerts.contacts import load_contacts
from jobhub_poc.auth_admin_client import AuthServiceError

USERS_URL = f"{config.AUTH_SERVICE_URL}/internal/admin/users"


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ADMIN_API_KEY", "k")


def test_contacts_are_keyed_by_user_id_with_verification_flags(requests_mock):
    requests_mock.get(USERS_URL, json={"users": [
        {"id": "u1", "email": "a@x.com", "emailVerified": True, "phoneNumber": "+15550000001", "phoneNumberVerified": True},
        {"id": "u2", "email": "b@x.com", "emailVerified": False, "phoneNumber": None, "phoneNumberVerified": False},
    ]})
    contacts = load_contacts()
    assert requests_mock.last_request.headers["x-admin-api-key"] == "k"
    assert contacts["u1"].email == "a@x.com" and contacts["u1"].email_verified
    assert contacts["u1"].phone == "+15550000001" and contacts["u1"].phone_verified
    assert not contacts["u2"].email_verified and contacts["u2"].phone is None


def test_unreachable_auth_service_raises(requests_mock):
    requests_mock.get(USERS_URL, exc=requests.exceptions.ConnectionError)
    with pytest.raises(AuthServiceError):
        load_contacts()


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ADMIN_API_KEY", "")
    with pytest.raises(AuthServiceError):
        load_contacts()
