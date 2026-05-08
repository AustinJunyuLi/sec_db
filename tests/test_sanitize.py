from linkflow_probe.sanitize import sanitize


def test_sanitize_redacts_secret_fields() -> None:
    payload = {
        "Authorization": "Bearer secret",
        "api_key": "sk-test",
        "nested": {"cookie": "abc", "safe": "ok"},
    }

    assert sanitize(payload) == {
        "Authorization": "[REDACTED]",
        "api_key": "[REDACTED]",
        "nested": {"cookie": "[REDACTED]", "safe": "ok"},
    }


def test_sanitize_redacts_bare_secret_like_string() -> None:
    assert sanitize("sk-test") == "[REDACTED]"


def test_sanitize_keeps_presence_booleans() -> None:
    assert sanitize({"LINKFLOW_API_KEY_present": True}) == {"LINKFLOW_API_KEY_present": True}
