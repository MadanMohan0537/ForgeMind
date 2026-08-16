import json
from urllib import error as urlerror

import pytest

from services.perception import verify


class FakeResponse:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def configure(monkeypatch):
    monkeypatch.setenv("VLM_URL", "http://127.0.0.1:8001/v1/")
    monkeypatch.setenv("VLM_MODEL", "cosmos")


def test_available_reads_current_environment(monkeypatch):
    monkeypatch.delenv("VLM_URL", raising=False)
    monkeypatch.delenv("VLM_MODEL", raising=False)
    assert not verify.available()
    configure(monkeypatch)
    assert verify.available()


def test_video_request_uses_openai_multimodal_shape(tmp_path, monkeypatch):
    configure(monkeypatch)
    clip = tmp_path / "sample.mp4"
    clip.write_bytes(b"video")
    captured = {}

    def fake_open(req, timeout):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data)
        captured["timeout"] = timeout
        return FakeResponse({"choices": [{"message": {"content": "No, the zone is clear."}}]})

    monkeypatch.setattr(verify.urlrequest, "urlopen", fake_open)
    result = verify.vss_ask_video(str(clip), "Is there a hand?", timeout=4)

    assert captured["url"] == "http://127.0.0.1:8001/v1/chat/completions"
    assert captured["payload"]["model"] == "cosmos"
    assert captured["payload"]["temperature"] == 0
    media = captured["payload"]["messages"][0]["content"][1]
    assert media["type"] == "video_url"
    assert media["video_url"]["url"].startswith("data:video/mp4;base64,")
    assert captured["timeout"] == 4
    assert result["answer"].startswith("No")


def test_vlm_verify_parses_component_counts(tmp_path, monkeypatch):
    configure(monkeypatch)
    image = tmp_path / "evidence.jpg"
    image.write_bytes(b"image")
    answer = '```json\n{"detected":{"red_body":1,"black_wheel":2,"blue_roof":1},"notes":"visible"}\n```'
    monkeypatch.setattr(
        verify.urlrequest,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse({"choices": [{"message": {"content": answer}}]}),
    )

    result = verify.vlm_verify(str(image))

    assert result["detected"] == {"red_body": 1, "black_wheel": 2, "blue_roof": 1}
    assert result["notes"] == "visible"


def test_missing_configuration_is_clear(tmp_path, monkeypatch):
    monkeypatch.delenv("VLM_URL", raising=False)
    monkeypatch.delenv("VLM_MODEL", raising=False)
    clip = tmp_path / "sample.mp4"
    clip.write_bytes(b"video")
    with pytest.raises(verify.VLMUnavailable, match="must both be set"):
        verify.vss_ask_video(str(clip), "question")


def test_unreadable_media_is_wrapped(monkeypatch, tmp_path):
    configure(monkeypatch)
    with pytest.raises(verify.VLMUnavailable, match="not readable"):
        verify.vss_ask_video(str(tmp_path / "missing.mp4"), "question")


def test_backend_failure_is_wrapped(tmp_path, monkeypatch):
    configure(monkeypatch)
    clip = tmp_path / "sample.mp4"
    clip.write_bytes(b"video")

    def fail(*_args, **_kwargs):
        raise urlerror.URLError("offline")

    monkeypatch.setattr(verify.urlrequest, "urlopen", fail)
    with pytest.raises(verify.VLMUnavailable, match="offline"):
        verify.vss_ask_video(str(clip), "question")


def test_alert_registry_raises_only_yes(monkeypatch):
    answers = iter([{"answer": "Yes, a kit is visible."}, {"answer": "No hand."}])
    monkeypatch.setattr(verify, "vss_ask_video", lambda *_args, **_kwargs: next(answers))
    assert [item["alert"] for item in verify.check_alerts("clip.mp4")] == [verify.ALERTS[0]]
