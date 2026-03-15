from app.main import _build_session_cookie_value, _hash_password, _parse_session_cookie, _verify_password


def test_hash_and_verify_password_roundtrip():
    password_hash = _hash_password("Atmaca@53")
    assert password_hash.startswith("pbkdf2_sha256$")
    assert _verify_password("Atmaca@53", password_hash)


def test_verify_password_rejects_invalid_secret():
    password_hash = _hash_password("Atmaca@53")
    assert not _verify_password("wrong-password", password_hash)


def test_session_cookie_signature_roundtrip():
    cookie_value = _build_session_cookie_value("token-123")
    assert _parse_session_cookie(cookie_value) == "token-123"
    assert _parse_session_cookie("token-123.invalid") is None
