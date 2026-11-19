"""Validate every PBIR JSON file in a .Report folder against Microsoft's published schemas.

Usage: python validate_pbir.py "<path to X.Report>"
Schemas are downloaded once from github.com/microsoft/json-schemas and cached in _tools/schemas/cache.
"""
import json
import sys
import urllib.request
from pathlib import Path

from jsonschema import Draft7Validator
from referencing import Registry, Resource

CACHE = Path(__file__).resolve().parent / "schemas" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
PREFIX = "https://developer.microsoft.com/json-schemas/"
RAW = "https://raw.githubusercontent.com/microsoft/json-schemas/main/"


def fetch(uri: str) -> dict:
    uri = uri.split("#")[0]
    f = CACHE / (uri.replace(PREFIX, "").replace("/", "_"))
    if not f.exists():
        with urllib.request.urlopen(uri.replace(PREFIX, RAW), timeout=60) as r:
            f.write_bytes(r.read())
    return json.loads(f.read_text(encoding="utf-8"))


def retrieve(uri: str):
    return Resource.from_contents(fetch(uri))


def main(report_dir: str) -> int:
    registry = Registry(retrieve=retrieve)
    errors = 0
    files = [p for p in Path(report_dir).rglob("*.json") if "StaticResources" not in p.parts]
    files.append(Path(report_dir) / "definition.pbir")
    for p in files:
        doc = json.loads(p.read_text(encoding="utf-8"))
        sch_uri = doc.get("$schema")
        if not sch_uri:
            continue
        schema = fetch(sch_uri)
        v = Draft7Validator(schema, registry=registry)
        errs = sorted(v.iter_errors(doc), key=lambda e: list(e.path))
        for e in errs[:5]:
            errors += 1
            print(f"FAIL {p.relative_to(report_dir)}: {'/'.join(map(str, e.path))}: {e.message[:300]}")
    print(f"checked {len(files)} files, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
