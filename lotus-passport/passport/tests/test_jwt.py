"""Tests for JWT issuance with the unified `passport_user_id` claim."""
import pytest

from passport.jwt import decode_access, issue_tokens
from passport.models import PassportUser


@pytest.mark.django_db
def test_issue_tokens_carries_passport_user_id():
    user = PassportUser.objects.create(email="neo@matrix.io", nickname="Neo")
    tokens = issue_tokens(user)

    assert "access" in tokens and "refresh" in tokens
    assert tokens["passport_user_id"] == str(user.passport_id)
    assert tokens["token_type"] == "Bearer"


@pytest.mark.django_db
def test_access_token_payload_is_verifiable():
    user = PassportUser.objects.create(email="trinity@matrix.io", nickname="Trinity")
    tokens = issue_tokens(user)
    payload = decode_access(tokens["access"])

    assert payload["passport_user_id"] == str(user.passport_id)
    assert payload["email"] == "trinity@matrix.io"
    assert payload["nickname"] == "Trinity"


@pytest.mark.django_db
def test_distinct_users_get_distinct_ids():
    a = PassportUser.objects.create(email="a@x.com")
    b = PassportUser.objects.create(email="b@x.com")
    assert issue_tokens(a)["passport_user_id"] != issue_tokens(b)["passport_user_id"]
