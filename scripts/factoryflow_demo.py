"""Load the deterministic FactoryFlow demo into a running Core service."""
from __future__ import annotations

import argparse
import json

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", default="http://127.0.0.1:8100")
    args = parser.parse_args()
    response = httpx.post(f"{args.core.rstrip('/')}/factoryflow/demo", timeout=20)
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
