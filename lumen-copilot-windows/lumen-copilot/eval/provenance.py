"""Fingerprint executable source so stale browser evidence is never mixed with a new version."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def source_hash():
    paths = [p for folder in ("backend", "frontend") for p in (ROOT / folder).rglob("*")
             if p.is_file() and p.suffix in (".py", ".js", ".html", ".css") and "vendor" not in p.parts]
    paths += [ROOT / "run.py", ROOT / "requirements.txt"]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode()); digest.update(path.read_bytes())
    return digest.hexdigest()
