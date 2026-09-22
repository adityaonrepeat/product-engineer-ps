from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from memory_ledger.api import create_app


def candidate_payload(
    *,
    message_id: str = "message-001",
    value: str = "Pune",
    excerpt: str = "I live in Pune.",
) -> dict[str, object]:
    return {
        "source": {
            "message_id": message_id,
            "conversation_id": "conversation-001",
            "excerpt": excerpt,
            "occurred_at": "2026-01-01T14:30:00+05:30",
        },
        "fact": {
            "key": "location.current_city",
            "value": value,
            "text": f"User currently lives in {value}",
            "tags": ["location", "city", "home", "live"],
        },
    }


def test_store_inspect_and_duplicate_status_codes(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "api.db")) as client:
        created = client.post("/v1/memories", json=candidate_payload())
        duplicate = client.post("/v1/memories", json=candidate_payload())
        inspected = client.get(f"/v1/memories/{created.json()['memory']['id']}")

    assert created.status_code == 201
    assert duplicate.status_code == 200
    assert created.json() == duplicate.json() | {"created": True}
    assert created.json()["memory"]["source_occurred_at"] == "2026-01-01T09:00:00Z"
    assert inspected.status_code == 200
    assert len(inspected.json()["history"]) == 1


def test_correction_conflict_retrieval_and_deletion(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "api.db")) as client:
        pune = client.post("/v1/memories", json=candidate_payload()).json()["memory"]
        mumbai_response = client.post(
            f"/v1/memories/{pune['id']}/corrections",
            json=candidate_payload(
                message_id="message-002",
                value="Mumbai",
                excerpt="I moved to Mumbai.",
            ),
        )
        invalid_correction = client.post(
            f"/v1/memories/{pune['id']}/corrections",
            json=candidate_payload(message_id="message-003", value="Delhi"),
        )
        mumbai = mumbai_response.json()["memory"]
        pending = client.post(
            f"/v1/memories/{mumbai['id']}/conflicts",
            json=candidate_payload(message_id="message-004", value="Bangalore"),
        )
        retrieved = client.post(
            "/v1/retrievals",
            json={"query": "where do I live city", "limit": 5},
        )
        deleted = client.delete(f"/v1/memories/{mumbai['id']}")
        after_deletion = client.post(
            "/v1/retrievals",
            json={"query": "where do I live city", "limit": 5},
        )

    assert mumbai_response.status_code == 201
    assert invalid_correction.status_code == 409
    assert pending.status_code == 201
    assert pending.json()["memory"]["state"] == "pending_review"
    assert [result["memory"]["value"] for result in retrieved.json()["results"]] == ["Mumbai"]
    assert retrieved.json()["results"][0]["evidence"]["score"] > 0
    assert deleted.json()["state"] == "deleted"
    assert after_deletion.json()["results"] == []


def test_domain_errors_and_validation_are_http_responses(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "api.db")) as client:
        missing = client.get("/v1/memories/00000000-0000-0000-0000-000000000000")
        invalid = client.post(
            "/v1/memories",
            json=candidate_payload() | {"fact": {"key": "", "value": "Pune", "text": ""}},
        )

    assert missing.status_code == 404
    assert invalid.status_code == 422
