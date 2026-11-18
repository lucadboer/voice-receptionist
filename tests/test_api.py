import pytest
from fastapi.testclient import TestClient

from api.server import app
from receptionist import config
from receptionist.tools import all_tools


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Never touch the real config.json.
    monkeypatch.setattr(config, "LIVE_PATH", tmp_path / "config.json")
    return TestClient(app)


def test_get_returns_default_config(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == config.load_config(config.DEFAULT_PATH).model_dump()


def test_put_then_get_round_trips(client, tmp_path):
    new = client.get("/api/config").json() | {"agent_name": "Sam", "enabled_tools": ["end_call"]}
    response = client.put("/api/config", json=new)
    assert response.status_code == 200
    assert response.json() == new
    assert client.get("/api/config").json() == new
    assert (tmp_path / "config.json").exists()


def test_unknown_voice_is_rejected(client, tmp_path):
    new = client.get("/api/config").json() | {"voice": "nobody"}
    response = client.put("/api/config", json=new)
    assert response.status_code == 422
    assert "unknown voice" in response.text
    assert not (tmp_path / "config.json").exists()


def test_unknown_tool_is_rejected(client, tmp_path):
    new = client.get("/api/config").json() | {"enabled_tools": ["end_call", "send_invoice"]}
    response = client.put("/api/config", json=new)
    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown tools: send_invoice"
    assert not (tmp_path / "config.json").exists()


def test_options_list_every_tool_and_voice(client):
    options = client.get("/api/options").json()
    assert [tool["name"] for tool in options["tools"]] == [tool.id for tool in all_tools()]
    assert all(tool["description"] for tool in options["tools"])
    assert [voice["id"] for voice in options["voices"]] == list(config.VOICES)
    assert options["call_rules"]
