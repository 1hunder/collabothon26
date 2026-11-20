import uuid

from fastapi import APIRouter
from fastapi.testclient import TestClient

from financequest.api.deps import SessionId
from financequest.api.main import create_app


def _client() -> TestClient:
    app = create_app()
    r = APIRouter()

    @r.get("/whoami")
    def whoami(sid: SessionId) -> dict[str, str]:
        return {"session_id": str(sid)}

    app.include_router(r)
    return TestClient(app)


def test_issue_session(client: TestClient) -> None:
    r = client.post("/session")
    assert r.status_code == 201
    uuid.UUID(r.json()["session_id"])


def test_validate_session(test_db_url: str) -> None:
    c = _client()
    sid = c.post("/session").json()["session_id"]
    assert c.get("/whoami", headers={"X-Session-Id": sid}).json() == {"session_id": sid}
    assert c.get("/whoami").status_code == 401
    assert c.get("/whoami", headers={"X-Session-Id": "nope"}).status_code == 401
    assert c.get("/whoami", headers={"X-Session-Id": str(uuid.uuid4())}).status_code == 401
