from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] is True
    assert body["playable_count"] == 0
    assert body["fixtures_loaded"] is False
    assert "claude" not in body
