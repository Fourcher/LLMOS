#!/usr/bin/env python3
"""The provenance of a build: which source produced the images in dist/.

`source_hash()` is a content digest of everything that goes into an image (the `src/` tree — the OS, the
installer and the live-ISO scripts), taken from the working tree so it reflects uncommitted edits too. The
build records it in dist/RELEASE.json; tools/check-fresh.py compares it to the current source to tell whether
dist/ is up to date. dist/setup/ and tools/ are deliberately excluded: they ship or test as-is and do not go
into the image, so changing them does not make the images stale.
"""
import hashlib
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "src"          # the only tree baked into an image


def _git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True).stdout


def source_files():
    """Every file under src/ that is part of the source: tracked files plus new, non-ignored ones."""
    tracked = _git("ls-files", SRC).split("\n")
    untracked = _git("ls-files", "--others", "--exclude-standard", SRC).split("\n")
    return sorted(f for f in set(tracked) | set(untracked) if f)


def source_hash():
    """A stable SHA-256 over the names and contents of the source files (working-tree contents)."""
    h = hashlib.sha256()
    for f in source_files():
        h.update(f.encode("utf-8") + b"\0")
        try:
            with open(os.path.join(ROOT, f), "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
        except OSError:
            h.update(b"<unreadable>")
        h.update(b"\0")
    return h.hexdigest()


def source_hash_at(commit):
    """The same digest as source_hash(), over src/ as committed at `commit` (not the working tree)."""
    names = sorted(f for f in _git("ls-tree", "-r", "--name-only", commit, "--", SRC).split("\n") if f)
    h = hashlib.sha256()
    for f in names:
        h.update(f.encode("utf-8") + b"\0")
        p = subprocess.run(["git", "-C", ROOT, "show", f"{commit}:./{f}"], capture_output=True)
        h.update(p.stdout if p.returncode == 0 else b"<unreadable>")
        h.update(b"\0")
    return h.hexdigest()


def source_commit():
    """The short HEAD commit, with -dirty when src/ has uncommitted changes."""
    rev = _git("rev-parse", "--short", "HEAD").strip() or "unknown"
    dirty = _git("status", "--porcelain", SRC).strip()
    return rev + ("-dirty" if dirty else "")


if __name__ == "__main__":
    print("commit:", source_commit())
    print("source_hash:", source_hash())
    print("files:", len(source_files()))
