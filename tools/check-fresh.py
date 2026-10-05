#!/usr/bin/env python3
"""Is dist/ built from the current OS source? Compares the source digest recorded in dist/RELEASE.json (what
the images were built from) with the source as it is now. Prints FRESH or STALE and, when stale, the src/
files that changed since the build. Exits non-zero when stale or unbuilt, so it can gate a commit or release.

    python3 tools/check-fresh.py

Only src/ affects the images; changes under dist/setup/ or tools/ do not make the images stale.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buildstamp  # noqa: E402

ROOT = buildstamp.ROOT
REL = os.path.join(ROOT, "dist", "RELEASE.json")


def main():
    try:
        rel = json.load(open(REL))
    except OSError:
        print("STALE: no dist/RELEASE.json — nothing has been built yet. Run tools/release.sh.")
        return 2
    built = rel.get("source_hash")
    now = buildstamp.source_hash()
    imgs = ", ".join(i["file"] for i in rel.get("images", []))
    if not built:
        print("UNKNOWN: this RELEASE.json predates source stamping; rebuild with tools/release.sh to start tracking.")
        return 2
    if built == now:
        print(f"FRESH: dist/ was built from the current OS source ({rel.get('source_commit', '?')}, v{rel.get('version', '?')}).")
        print(f"  images: {imgs}")
        return 0
    print(f"STALE: the OS source changed since dist/ was built (built from {rel.get('source_commit', '?')}).")
    changed = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "src"], capture_output=True, text=True).stdout.strip()
    # also show committed changes to src/ since the recorded commit, if that commit is known
    commit = (rel.get("source_commit") or "").replace("-dirty", "")
    committed = ""
    if commit:
        committed = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", commit, "HEAD", "--", "src"],
                                   capture_output=True, text=True).stdout.strip()
    for label, body in (("committed since the build", committed), ("uncommitted now", changed)):
        if body:
            print(f"  {label}:")
            for line in body.splitlines()[:40]:
                print(f"    {line}")
    print("  -> rebuild with: tools/release.sh")
    return 1


if __name__ == "__main__":
    sys.exit(main())
