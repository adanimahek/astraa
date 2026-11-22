"""Seed (or remove) the synthetic e-challan demonstration data in MongoDB.

Usage (from the backend folder):
    python scripts/seed_demo_data.py          # upsert demo owners, vehicles and owner logins
    python scripts/seed_demo_data.py --remove # delete only records tagged demo=True

Uses the same MONGODB_URI / DB_NAME as the API (backend/.env).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enforcement import demo_data, registry  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    registry.ensure_indexes()
    result = demo_data.remove() if args.remove else demo_data.seed()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
