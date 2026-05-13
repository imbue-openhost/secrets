"""Smoke tests against a real containerized secrets app."""

import httpx
from openhost_test_harness import OpenhostStack


def test_index_renders(stack: OpenhostStack) -> None:
    r = httpx.get(f"{stack.url}/")
    assert r.status_code == 200
    assert "Secrets" in r.text


def test_set_and_list_secret(stack: OpenhostStack) -> None:
    set_resp = httpx.post(
        f"{stack.url}/api/secrets",
        json={"key": "TEST_KEY", "value": "test_value", "description": "smoke"},
    )
    assert set_resp.status_code == 201, set_resp.text
    assert set_resp.json() == {"ok": True}

    list_resp = httpx.get(f"{stack.url}/api/secrets")
    assert list_resp.status_code == 200
    keys = [row["key"] for row in list_resp.json()]
    assert "TEST_KEY" in keys


def test_export_round_trips_through_import(stack: OpenhostStack) -> None:
    """Values with shell metacharacters must survive an export -> import round trip."""
    tricky = "needs 'quotes' & $shell stuff"
    httpx.post(f"{stack.url}/api/secrets", json={"key": "TRICKY", "value": tricky})

    exported = httpx.get(f"{stack.url}/api/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/plain")
    assert "secrets.env" in exported.headers.get("content-disposition", "")
    assert "export TRICKY=" in exported.text

    httpx.delete(f"{stack.url}/api/secrets/TRICKY")
    httpx.post(f"{stack.url}/api/import", json={"content": exported.text})

    listed = httpx.get(f"{stack.url}/api/secrets").json()
    assert any(row["key"] == "TRICKY" for row in listed)


def test_v2_service_requires_grant(stack: OpenhostStack) -> None:
    """Direct service call without grants should be rejected."""
    r = httpx.post(
        f"{stack.app_url}/_service_v2/get",
        json={"keys": ["ANY_KEY"]},
    )
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "permission_required"
    assert body["required_grant"] == {"grant": {"key": "ANY_KEY"}}


def test_v2_service_with_grant(stack: OpenhostStack) -> None:
    httpx.post(
        f"{stack.url}/api/secrets",
        json={"key": "GRANTED_KEY", "value": "shh"},
    )

    r = httpx.post(
        f"{stack.app_url}/_service_v2/get",
        json={"keys": ["GRANTED_KEY"]},
        headers={"X-OpenHost-Permissions": '[{"grant":{"key":"GRANTED_KEY"}}]'},
    )
    assert r.status_code == 201  # Litestar @post default; may want to pin to 200 later
    assert r.json() == {"secrets": {"GRANTED_KEY": "shh"}}
