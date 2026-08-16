"""Nemotron client. Works against any OpenAI-compatible endpoint (vLLM, NIM, Ollama, NemoClaw inference).

Env:
  LLM_BASE_URL   default http://127.0.0.1:8000/v1
  LLM_MODEL      default "super"   (whatever --served-model-name you used)
  LLM_FAST_MODEL optional; if set, the per-kit action loop uses this model (e.g. "lightning")
  LLM_FAST_BASE_URL optional; if Lightning is served on another port (e.g. http://127.0.0.1:8002/v1)
  LLM_API_KEY    default "none"
  LLM_THINK_MODE "kwarg" (chat_template_kwargs.enable_thinking) | "tag" (/think, /no_think in system prompt)
                 | "ollama" (native think=false and reasoning_effort=none) | "off"
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from shared.schemas import (ActionProposal, ExperimentPlan, HypothesisSet, RunMetrics, VerificationVerdict, WorldState)
from services.core import prompts as P

T = TypeVar("T", bound=BaseModel)

BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
MODEL = os.environ.get("LLM_MODEL", "super")
FAST_MODEL = os.environ.get("LLM_FAST_MODEL", MODEL)
THINK_MODE = os.environ.get("LLM_THINK_MODE", "kwarg")

_client = OpenAI(base_url=BASE_URL, api_key=os.environ.get("LLM_API_KEY", "none"), timeout=120)
FAST_BASE_URL = os.environ.get("LLM_FAST_BASE_URL", BASE_URL)
_fast_client = _client if FAST_BASE_URL == BASE_URL else OpenAI(base_url=FAST_BASE_URL, api_key=os.environ.get("LLM_API_KEY", "none"), timeout=60)
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


class LLMError(RuntimeError):
    pass


def reconfigure(base_url: str | None = None, model: str | None = None,
                fast_model: str | None = None, fast_base_url: str | None = None) -> dict:
    """Repoint this client at a different endpoint or model at runtime.

    Added by Part 2 so core can switch Super -> Lightning without a restart (core calls
    this from POST /admin/llm); the module-level configuration above is otherwise fixed at
    import. Additive only — nothing else in this file changed. P3 owns this module, so
    move or rename this freely, just tell core.

    Args:
        base_url: OpenAI-compatible endpoint for the main model.
        model: served model name for analysis calls.
        fast_model: served model name for the per-kit action loop.
        fast_base_url: endpoint for the fast model, if it is served separately.

    Returns:
        The configuration now in effect.
    """
    global BASE_URL, MODEL, FAST_MODEL, FAST_BASE_URL, _client, _fast_client
    api_key = os.environ.get("LLM_API_KEY", "none")
    if base_url is not None:
        BASE_URL = base_url
        _client = OpenAI(base_url=BASE_URL, api_key=api_key, timeout=120)
    if model is not None:
        MODEL = model
    if fast_model is not None:
        FAST_MODEL = fast_model
    if fast_base_url is not None:
        FAST_BASE_URL = fast_base_url
    # Rebuild the fast client whenever either endpoint moved, so the two stay consistent.
    _fast_client = _client if FAST_BASE_URL == BASE_URL else OpenAI(
        base_url=FAST_BASE_URL, api_key=api_key, timeout=60)
    return {"base_url": BASE_URL, "model": MODEL, "fast_model": FAST_MODEL, "fast_base_url": FAST_BASE_URL}


def _extract_json(text: str) -> dict:
    text = _THINK_RE.sub("", text).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise LLMError(f"no JSON in model output: {text[:200]!r}")
        return json.loads(m.group(0))


def chat_json(system: str, user: str, schema: Type[T], *, model: str | None = None,
              thinking: bool = False, temperature: float = 0.2, max_tokens: int = 2000,
              timeout: float | None = None) -> T:
    """Call the model and return a validated pydantic object. Tries json_schema, then guided_json, then free-form."""
    model = model or MODEL
    sys_prompt = system
    extra: dict = {}
    if THINK_MODE == "kwarg":
        extra["chat_template_kwargs"] = {"enable_thinking": thinking}
    elif THINK_MODE == "tag":
        sys_prompt = ("/think\n" if thinking else "/no_think\n") + system
    elif THINK_MODE == "ollama":
        # Ollama exposes reasoning separately and may exhaust max_tokens before
        # writing the schema-constrained answer into message.content. Its native
        # think flag plus reasoning_effort=none keeps this path deterministic.
        extra["think"] = False
    js = schema.model_json_schema()
    attempts = [
        {"response_format": {"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": js}}},
        {"extra_body": {"guided_json": js}},
        {},
    ]
    last_err: Exception | None = None
    for a in attempts:
        kwargs = dict(model=model, temperature=temperature, max_tokens=max_tokens,
                      messages=[{"role": "system", "content": sys_prompt},
                                {"role": "user", "content": user + "\n\nReturn ONLY JSON matching this schema:\n" + json.dumps(js)}])
        if THINK_MODE == "ollama":
            kwargs["reasoning_effort"] = "none"
        body = dict(extra)
        if "extra_body" in a:
            body.update(a["extra_body"])
        if body:
            kwargs["extra_body"] = body
        if "response_format" in a:
            kwargs["response_format"] = a["response_format"]
        try:
            t0 = time.time()
            client = _fast_client if model == FAST_MODEL and FAST_MODEL != MODEL else _client
            resp = client.chat.completions.create(timeout=timeout, **kwargs)  # type: ignore[arg-type]
            text = resp.choices[0].message.content or ""
            obj = schema.model_validate(_extract_json(text))
            _log(model, schema.__name__, time.time() - t0, resp)
            return obj
        except Exception as e:  # noqa: BLE001 - we want to fall through to the next strategy
            last_err = e
            continue
    raise LLMError(f"all structured-output strategies failed: {last_err}")


def _log(model: str, name: str, dt: float, resp) -> None:
    try:
        u = resp.usage
        print(f"[llm] {model} {name} {dt:.1f}s prompt={u.prompt_tokens} completion={u.completion_tokens}", flush=True)
    except Exception:  # noqa: BLE001
        print(f"[llm] {model} {name} {dt:.1f}s", flush=True)


# --------------------------------------------------------------------------- #
# Task-level helpers (what the orchestrator/agent call)
# --------------------------------------------------------------------------- #
def generate_hypotheses(run_id: str, events, metrics: RunMetrics, valid_ids: set[int]) -> HypothesisSet:
    user = f"RUN {run_id}\nMETRICS (computed by code):\n{metrics.model_dump_json(indent=1)}\n\nEVENT LOG:\n{P.event_digest(events)}"
    hs = chat_json(P.ANALYST_SYSTEM, user, HypothesisSet, thinking=True, max_tokens=3000)
    hs.run_id = run_id
    # Grounding is a code-enforced contract: invalid citations and duplicate IDs do
    # not survive, and an unsupported hypothesis is never submitted as evidence.
    grounded = []
    seen_hypothesis_ids: set[str] = set()
    for h in hs.hypotheses:
        h.supporting_event_ids = list(dict.fromkeys(i for i in h.supporting_event_ids if i in valid_ids))
        h.contradicting_event_ids = list(dict.fromkeys(i for i in h.contradicting_event_ids if i in valid_ids))
        if h.supporting_event_ids and h.id not in seen_hypothesis_ids:
            grounded.append(h)
            seen_hypothesis_ids.add(h.id)
    hs.hypotheses = grounded
    if len(hs.hypotheses) < 2:
        raise LLMError("model returned fewer than two distinct, source-grounded hypotheses")
    return hs


def plan_experiment(hyps: HypothesisSet, metrics: RunMetrics) -> ExperimentPlan:
    user = f"HYPOTHESES:\n{hyps.model_dump_json(indent=1)}\n\nMETRICS:\n{metrics.model_dump_json(indent=1)}"
    plan = chat_json(P.PLANNER_EXPERIMENT_SYSTEM, user, ExperimentPlan, thinking=True, max_tokens=1200)
    if plan.change not in P.ALLOWED_EXPERIMENTS:
        raise LLMError(f"experiment change is outside the allowlist: {plan.change!r}")
    valid_hypothesis_ids = {h.id for h in hyps.hypotheses}
    if plan.tests_hypothesis_id not in valid_hypothesis_ids:
        raise LLMError(f"experiment references unknown hypothesis: {plan.tests_hypothesis_id!r}")
    return plan


def propose_action(world: WorldState, timeout: float = 15.0) -> ActionProposal:
    user = "KIT OBSERVATION:\n" + world.model_dump_json(indent=1)
    p = chat_json(P.ACTION_SYSTEM, user, ActionProposal, model=FAST_MODEL, thinking=False,
                  temperature=0.0, max_tokens=300, timeout=timeout)
    p.kit_id = world.kit_id
    p.proposed_by = f"llm:{FAST_MODEL}"
    return p


def verify_hypothesis(h: dict, experiment: dict, before: RunMetrics, after: RunMetrics) -> VerificationVerdict:
    user = (f"HYPOTHESIS:\n{json.dumps(h, indent=1)}\n\nEXPERIMENT RUN:\n{json.dumps(experiment, indent=1)}\n\n"
            f"BEFORE:\n{before.model_dump_json(indent=1)}\n\nAFTER:\n{after.model_dump_json(indent=1)}")
    v = chat_json(P.VERIFIER_SYSTEM, user, VerificationVerdict, thinking=True, max_tokens=800)
    v.hypothesis_id = h.get("id", v.hypothesis_id)
    return v


def health() -> dict:
    try:
        models = _client.models.list()
        return {"ok": True, "base_url": BASE_URL, "models": [m.id for m in models.data]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "base_url": BASE_URL, "error": str(e)}
