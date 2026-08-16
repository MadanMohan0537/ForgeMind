from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from services.core import llm, prompts
from shared.schemas import ExperimentPlan, Hypothesis, HypothesisSet, RunMetrics


class TinyResult(BaseModel):
    value: str


def _hypothesis(hypothesis_id: str, supporting: list[int]) -> Hypothesis:
    return Hypothesis(
        id=hypothesis_id,
        title=f"Cause {hypothesis_id}",
        explanation="A testable cause.",
        confidence=0.5,
        supporting_event_ids=supporting,
    )


def _set(*hypotheses: Hypothesis) -> HypothesisSet:
    return HypothesisSet(run_id="source", summary="competing causes", hypotheses=list(hypotheses))


def test_ollama_mode_disables_reasoning(monkeypatch):
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"value":"ok"}'))],
                usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2),
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr(llm, "THINK_MODE", "ollama")
    monkeypatch.setattr(llm, "_client", fake_client)
    monkeypatch.setattr(llm, "MODEL", "nemotron-3.5-lightning:latest")
    monkeypatch.setattr(llm, "FAST_MODEL", "nemotron-3.5-lightning:latest")

    result = llm.chat_json("system", "user", TinyResult, max_tokens=20)

    assert result.value == "ok"
    assert captured["reasoning_effort"] == "none"
    assert captured["extra_body"]["think"] is False


def test_action_prompt_defines_computed_missing_counts():
    assert "detected black_wheel=1 and missing black_wheel=1" in prompts.ACTION_SYSTEM
    assert "MUST be ADD_PART" in prompts.ACTION_SYSTEM


def test_analysis_prompts_forbid_known_causal_misreads():
    assert "QC_APPROVED after RECOVERY_VERIFIED" in prompts.ANALYST_SYSTEM
    assert "Do not force station diversity" in prompts.ANALYST_SYSTEM
    assert "Never put recovery before inspection" in prompts.PLANNER_EXPERIMENT_SYSTEM


def test_hypothesis_grounding_filters_invalid_and_duplicate_citations(monkeypatch):
    model_result = _set(
        _hypothesis("H1", [1, 999, 1]),
        _hypothesis("H2", [2, 2]),
        _hypothesis("H3", [999]),
    )
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: model_result)

    result = llm.generate_hypotheses("run-7", [], RunMetrics(run_id="run-7"), {1, 2})

    assert result.run_id == "run-7"
    assert [h.id for h in result.hypotheses] == ["H1", "H2"]
    assert result.hypotheses[0].supporting_event_ids == [1]
    assert result.hypotheses[1].supporting_event_ids == [2]


def test_hypothesis_grounding_rejects_fewer_than_two_supported_causes(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: _set(
        _hypothesis("H1", [1]), _hypothesis("H2", [999])))

    with pytest.raises(llm.LLMError, match="fewer than two"):
        llm.generate_hypotheses("run-7", [], RunMetrics(run_id="run-7"), {1})


def test_experiment_must_be_allowlisted_and_reference_a_real_hypothesis(monkeypatch):
    hypotheses = _set(_hypothesis("H1", [1]), _hypothesis("H2", [2]))
    valid = ExperimentPlan(
        change=prompts.ALLOWED_EXPERIMENTS[0],
        keep_unchanged=["Bob", "Charlie"],
        reason="Discriminate causes.",
        tests_hypothesis_id="H1",
        expected_observation="Fewer missing parts.",
        metric_to_watch="incomplete_kits_detected",
    )
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: valid)
    assert llm.plan_experiment(hypotheses, RunMetrics(run_id="run-7")) == valid

    invalid_change = valid.model_copy(update={"change": "remove reinspection"})
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: invalid_change)
    with pytest.raises(llm.LLMError, match="outside the allowlist"):
        llm.plan_experiment(hypotheses, RunMetrics(run_id="run-7"))

    invalid_reference = valid.model_copy(update={"tests_hypothesis_id": "H99"})
    monkeypatch.setattr(llm, "chat_json", lambda *args, **kwargs: invalid_reference)
    with pytest.raises(llm.LLMError, match="unknown hypothesis"):
        llm.plan_experiment(hypotheses, RunMetrics(run_id="run-7"))
