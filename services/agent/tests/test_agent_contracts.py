from services.agent import agent_loop


def test_denial_report_has_explicit_sandbox_provenance(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            captured["checked"] = True

    class Http:
        def post(self, url, json):
            captured.update(url=url, body=json)
            return Response()

    monkeypatch.setattr(agent_loop, "http", Http())
    agent_loop.report_denial("blocked action", "blocked by policy")

    assert captured["checked"] is True
    assert captured["body"]["reporter"] == "openshell"
    assert captured["body"]["attempted"] == "blocked action"
