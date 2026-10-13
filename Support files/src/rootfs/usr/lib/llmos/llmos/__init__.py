"""LLM OS: an operating system you talk to."""
VERSION = "1.8.1"
RELEASE_FILE = "/etc/llmos-release"


def release(path=RELEASE_FILE):
    """The build stamp the image build (MEDIUM=disk) and the ISO build (MEDIUM=live) write: VERSION, BUILD
    (date), ARCH, MEDIUM. A system without one (an image from before 1.4.0) reports this package's version."""
    rel = {}
    try:
        for line in open(path):
            k, _, v = line.strip().partition("=")
            if k:
                rel[k] = v
    except OSError:
        pass
    rel.setdefault("VERSION", VERSION)
    return rel


def version_line(rel=None):
    """'LLM OS 1.4.0 (build 2026-10-04, aarch64)', with ', live' when running from the live medium."""
    rel = release() if rel is None else rel
    if not rel.get("BUILD"):
        return f"LLM OS {rel['VERSION']}"
    return f"LLM OS {rel['VERSION']} (build {rel['BUILD']}, {rel.get('ARCH', '')}{', live' if rel.get('MEDIUM') == 'live' else ''})"
