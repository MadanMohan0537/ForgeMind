"""ForgeMind on open data: UCI AI4I 2020 Predictive Maintenance (CC BY 4.0, 10,000 rows).

Same idea as the tabletop line: deterministic code computes the numbers, Nemotron proposes competing,
TESTABLE hypotheses (as predicates over columns), and code checks each one against the data.

  python scripts/open_data_ai4i.py --download          # fetch + deterministic stats only (works before the LLM is up)
  python scripts/open_data_ai4i.py                     # + Nemotron hypotheses + code verdicts
  python scripts/open_data_ai4i.py --submit            # also push the result to core (/analysis/submit/ai4i_2020)
Outputs: data/open/ai4i2020.csv, runs/open_data_ai4i.json, runs/open_data_ai4i.md (paste into README/video)
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Literal

import httpx
import pandas as pd
from pydantic import BaseModel, Field

DATA = Path("data/open")
CSV = DATA / "ai4i2020.csv"
ZIP_URL = "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"
CORE = "http://127.0.0.1:8100"

FEATURES = ["Type", "Air temperature [K]", "Process temperature [K]", "Rotational speed [rpm]", "Torque [Nm]",
            "Tool wear [min]", "temp_diff", "power_W"]


class Predicate(BaseModel):
    feature: str = Field(description="one of the listed feature names, exactly")
    op: Literal[">", ">=", "<", "<=", "==", "!="]
    value: float | str


class DataHypothesis(BaseModel):
    id: str
    title: str
    explanation: str
    predicate: list[Predicate] = Field(description="AND of conditions describing the risky region")
    expected: Literal["higher", "lower"] = "higher"
    confidence: float = Field(ge=0, le=1)


class DataHypothesisSet(BaseModel):
    summary: str
    hypotheses: list[DataHypothesis]


def download() -> pd.DataFrame:
    DATA.mkdir(parents=True, exist_ok=True)
    if not CSV.exists():
        try:
            from ucimlrepo import fetch_ucirepo  # type: ignore
            ds = fetch_ucirepo(id=601)
            df = pd.concat([ds.data.features, ds.data.targets], axis=1)
            df.to_csv(CSV, index=False)
        except Exception:
            print(f"downloading {ZIP_URL}")
            z = zipfile.ZipFile(io.BytesIO(httpx.get(ZIP_URL, follow_redirects=True, timeout=60).content))
            name = next(n for n in z.namelist() if n.endswith(".csv"))
            CSV.write_bytes(z.read(name))
    df = pd.read_csv(CSV)
    df["temp_diff"] = df["Process temperature [K]"] - df["Air temperature [K]"]
    df["power_W"] = df["Torque [Nm]"] * df["Rotational speed [rpm]"] * 2 * 3.14159 / 60
    return df


def stats(df: pd.DataFrame) -> dict:
    y = df["Machine failure"]
    out = {"rows": int(len(df)), "failure_rate": round(float(y.mean()), 4),
           "failures_by_mode": {m: int(df[m].sum()) for m in ["TWF", "HDF", "PWF", "OSF", "RNF"] if m in df},
           "failure_rate_by_type": {t: round(float(g["Machine failure"].mean()), 4) for t, g in df.groupby("Type")}}
    for col in ["Tool wear [min]", "Torque [Nm]", "Rotational speed [rpm]", "temp_diff", "power_W"]:
        q = pd.qcut(df[col], 4, duplicates="drop")
        out[f"failure_rate_by_{col}_quartile"] = {str(k): round(float(v), 4) for k, v in df.groupby(q, observed=True)["Machine failure"].mean().items()}
    return out


def test_hypothesis(df: pd.DataFrame, h: DataHypothesis) -> dict:
    mask = pd.Series(True, index=df.index)
    for p in h.predicate:
        if p.feature not in df.columns:
            return {"id": h.id, "verdict": "invalid", "reason": f"unknown feature {p.feature}"}
        col = df[p.feature]
        v = p.value
        if col.dtype == object:
            v = str(v)
        m = {">": col > v, ">=": col >= v, "<": col < v, "<=": col <= v, "==": col == v, "!=": col != v}[p.op]
        mask &= m
    inside, outside = df[mask], df[~mask]
    if len(inside) < 30 or len(outside) < 30:
        return {"id": h.id, "verdict": "inconclusive", "n_inside": int(len(inside)), "n_outside": int(len(outside)),
                "reason": "too few rows on one side"}
    ri, ro = float(inside["Machine failure"].mean()), float(outside["Machine failure"].mean())
    lift = (ri / ro) if ro else float("inf")
    supported = (lift >= 1.5) if h.expected == "higher" else (lift <= 0.67)
    return {"id": h.id, "verdict": "supported" if supported else "not_supported", "n_inside": int(len(inside)),
            "n_outside": int(len(outside)), "failure_rate_inside": round(ri, 4), "failure_rate_outside": round(ro, 4),
            "lift": round(lift, 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="stats only, no LLM")
    ap.add_argument("--submit", action="store_true")
    a = ap.parse_args()
    df = download()
    st = stats(df)
    print(json.dumps(st, indent=1))
    result: dict = {"dataset": "UCI AI4I 2020 Predictive Maintenance (CC BY 4.0)", "stats": st}
    if not a.download:
        sys.path.insert(0, ".")
        from services.core.llm import chat_json  # noqa: E402
        system = ("You are a process scientist. Given deterministic statistics from a manufacturing dataset, propose 3-4 COMPETING, "
                  "TESTABLE hypotheses about when machine failure is more likely. Each hypothesis is a predicate over these exact "
                  f"feature names: {FEATURES}. Type values are 'L','M','H'. Use thresholds that appear plausible from the quartile "
                  "stats. Return ONLY JSON.")
        hs = chat_json(system, "STATS:\n" + json.dumps(st, indent=1), DataHypothesisSet, thinking=True, max_tokens=2500)
        verdicts = [test_hypothesis(df, h) for h in hs.hypotheses]
        result["hypotheses"] = hs.model_dump()
        result["verdicts"] = verdicts
        for h, v in zip(hs.hypotheses, verdicts):
            print(f"{h.id} {h.title}: {v}")
    Path("runs").mkdir(exist_ok=True)
    Path("runs/open_data_ai4i.json").write_text(json.dumps(result, indent=1))
    md = [f"# ForgeMind on open data: AI4I 2020\n", f"Rows: {st['rows']}, overall failure rate {st['failure_rate']}\n"]
    if "hypotheses" in result:
        md.append("| id | hypothesis | inside | outside | lift | verdict |\n|---|---|---|---|---|---|")
        for h, v in zip(result["hypotheses"]["hypotheses"], result["verdicts"]):
            md.append(f"| {h['id']} | {h['title']} | {v.get('failure_rate_inside','–')} | {v.get('failure_rate_outside','–')} | {v.get('lift','–')} | {v['verdict']} |")
    Path("runs/open_data_ai4i.md").write_text("\n".join(md))
    if a.submit:
        httpx.post(f"{CORE}/analysis/submit/ai4i_2020", json={"kind": "open_data", "data": result}, timeout=30)
    print("wrote runs/open_data_ai4i.json and .md")


if __name__ == "__main__":
    main()
