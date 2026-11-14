"""Open a pull request for a fix the laptop already installed, or an issue when the fix failed.

The token is a fine-grained GitHub PAT the owner saved on this computer. It is read from a file
(mode 0600) or from LLMOS_GITHUB_TOKEN. It is never written into the report, the queue, or a log line.

This module never calls GitHub's merge API. A report that cannot be sent is stored and tried again later.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import selfloop_ctl

API = "https://api.github.com"
REPO = "Fourcher/LLMOS"
_TOKEN = re.compile(r"(?:github_pat_[A-Za-z0-9_]{16,255}|ghp_[A-Za-z0-9]{16,255})")
_SECRET = re.compile(
    r"github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+|sk-[A-Za-z0-9]+|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----")
_REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REF = re.compile(r"^refs/heads/llmos-fix/[A-Za-z0-9._-]{1,60}$")
# The only GitHub calls this file makes. A merge URL is not on the list.
_ALLOWED = (
    ("GET", re.compile(r"^/repos/[^/]+/[^/]+/git/ref/heads/[A-Za-z0-9._/-]+$")),
    ("GET", re.compile(r"^/repos/[^/]+/[^/]+/git/commits/[0-9a-f]{40}$")),
    ("POST", re.compile(r"^/repos/[^/]+/[^/]+/git/blobs$")),
    ("POST", re.compile(r"^/repos/[^/]+/[^/]+/git/trees$")),
    ("POST", re.compile(r"^/repos/[^/]+/[^/]+/git/commits$")),
    ("POST", re.compile(r"^/repos/[^/]+/[^/]+/git/refs$")),
    ("POST", re.compile(r"^/repos/[^/]+/[^/]+/pulls$")),
    ("POST", re.compile(r"^/repos/[^/]+/[^/]+/issues$")),
)


class ReportError(RuntimeError):
    """The report was not sent. The caller queues it."""


def redact(text):
    return _SECRET.sub("[secret]", str(text or ""))


def repo_name():
    name = os.environ.get("LLMOS_GITHUB_REPO", REPO).strip() or REPO
    if not _REPO_NAME.fullmatch(name):
        return REPO
    return name


def base_branch():
    name = os.environ.get("LLMOS_GITHUB_BASE", "main").strip() or "main"
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,80}", name):
        return "main"
    if name in ("llmos-fix",) or name.startswith("llmos-fix/"):
        return "main"
    return name


def branch_for(item_id):
    """A new branch. Never main, and never a name the default branch could be."""
    cleaned = re.sub(r"[^a-z0-9.-]+", "-", str(item_id or "fix").lower()).strip("-.") or "fix"
    name = "llmos-fix/" + cleaned[:40]
    ref = "refs/heads/" + name
    if not _REF.fullmatch(ref) or name in ("main", "master"):
        raise ReportError("refusing to use that branch name")
    return name


def repo_path(name):
    """An installed program path as the path it has in the Fourcher/LLMOS checkout."""
    text = str(name or "")
    if text.startswith("./"):
        text = text[2:]
    text = text.lstrip("/")
    parts = text.split("/")
    if not text or ".." in parts or not text.startswith("usr/lib/llmos/"):
        return ""
    base = parts[-1]
    if base in ("selfloop_ctl.py", "ota.py"):
        return ""
    return "Support files/src/rootfs/" + text


def token_path():
    return os.path.join(selfloop_ctl.state_dir(), "github.token")


def read_token():
    """The saved token, or ''. GITHUB_TOKEN and GH_TOKEN are ignored so a dev shell cannot leak into a report."""
    env = os.environ.get("LLMOS_GITHUB_TOKEN", "").strip()
    if _TOKEN.fullmatch(env):
        return env
    paths = [token_path()]
    extra = os.environ.get("LLMOS_GITHUB_TOKEN_FILE", "/etc/llmos/github.token")
    if extra:
        paths.append(extra)
    for path in paths:
        try:
            text = open(path, encoding="utf-8").read().strip()
        except OSError:
            continue
        if _TOKEN.fullmatch(text):
            return text
    return ""


def save_token(text):
    """Write the token where only this user can read it. Raises ValueError when it does not look like a PAT."""
    token = str(text or "").strip()
    if not _TOKEN.fullmatch(token):
        raise ValueError("that doesn't look like a GitHub personal access token")
    path = token_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
    os.chmod(path, 0o600)
    return path


def reports_path():
    return os.path.join(selfloop_ctl.state_dir(), "reports.json")


def load_reports():
    try:
        data = json.load(open(reports_path(), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def save_reports(rows):
    os.makedirs(selfloop_ctl.state_dir(), mode=0o700, exist_ok=True)
    path = reports_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(list(rows)[:20], handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _queue(entry):
    rows = [row for row in load_reports() if str(row.get("id")) != str(entry.get("id")) or row.get("kind") != entry.get("kind")]
    rows.append(entry)
    save_reports(rows)
    return entry


def drop_pending(item_id, kind=""):
    rows = []
    for row in load_reports():
        if str(row.get("id")) == str(item_id) and (not kind or row.get("kind") == kind) and row.get("status") == "pending":
            continue
        rows.append(row)
    save_reports(rows)


def _check_call(method, url, payload):
    path = urllib.parse.urlsplit(url).path
    if "merge" in path.lower():
        raise ReportError("refusing to merge")
    allowed = False
    for allowed_method, rx in _ALLOWED:
        if method == allowed_method and rx.match(path):
            allowed = True
            break
    if not allowed:
        raise ReportError("refusing " + method + " " + path)
    if method == "POST" and path.endswith("/git/refs"):
        ref = str((payload or {}).get("ref") or "")
        if not _REF.fullmatch(ref):
            raise ReportError("refusing to write that branch")
    if method == "POST" and path.endswith("/pulls"):
        head = str((payload or {}).get("head") or "")
        if not head.startswith("llmos-fix/") or "merge" in (payload or {}):
            raise ReportError("refusing that pull request")


def _urllib(method, url, payload, token):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "llmos-bugfix")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    except (OSError, urllib.error.URLError) as exc:
        raise ReportError("network") from exc
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return status, body


def _call(method, path, token, payload=None, transport=None):
    url = API + path
    _check_call(method, url, payload)
    send = transport or _urllib
    try:
        status, body = send(method, url, payload, token)
    except ReportError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise ReportError("network") from exc
    if status is None or int(status) >= 400:
        raise ReportError("github " + str(status or "error"))
    return body if isinstance(body, dict) else {}


def _scrub(text, token):
    text = redact(text)
    if token and token in text:
        text = text.replace(token, "[secret]")
    return text


def pr_body(description, diff, tests, health, token=""):
    names = tests if isinstance(tests, str) else ", ".join(str(t) for t in (tests or [])) or "(none recorded)"
    text = (
        "## Bug\n"
        + _scrub(description, token).strip()
        + "\n\n## Diff\n```\n"
        + _scrub(diff, token).strip()
        + "\n```\n\n## Light tests\n"
        + _scrub(names, token)
        + "\n\n## Health check\n"
        + _scrub(health, token).strip()
        + "\n\nThis pull request was opened by the laptop after the owner approved the fix and the health check passed. "
        "It is not merged. The laptop ran only its light tests, not the full suite.\n"
    )
    return text[:60000]


def issue_body(description, detail, token=""):
    return (
        "## Bug\n"
        + _scrub(description, token).strip()
        + "\n\n## What happened\nThe fix was not installed.\n\n"
        + _scrub(detail, token).strip()
        + "\n\nFiled from the laptop because the fix did not pass. Nothing was merged.\n"
    )[:20000]


def _files(files, token):
    out = []
    for row in files or []:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        if not path.startswith("Support files/src/rootfs/usr/lib/llmos/") or ".." in path.split("/"):
            continue
        if os.path.basename(path) in ("selfloop_ctl.py", "ota.py"):
            continue
        content = str(row.get("content") or "")
        if token and token in content:
            content = content.replace(token, "[secret]")
        if len(content) > 100000:
            continue
        out.append({"path": path, "content": content})
    return out[:40]


def _push_pr(entry, token, transport=None):
    repo = repo_name()
    base = base_branch()
    ref = _call("GET", f"/repos/{repo}/git/ref/heads/{base}", token, transport=transport)
    parent = str((ref.get("object") or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", parent):
        raise ReportError("the base branch has no commit")
    commit = _call("GET", f"/repos/{repo}/git/commits/{parent}", token, transport=transport)
    tree_sha = str((commit.get("tree") or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
        raise ReportError("the base commit has no tree")
    tree = []
    for row in _files(entry.get("files"), token):
        blob = _call("POST", f"/repos/{repo}/git/blobs", token,
                     {"content": row["content"], "encoding": "utf-8"}, transport)
        sha = str(blob.get("sha") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ReportError("the blob was not stored")
        tree.append({"path": row["path"], "mode": "100644", "type": "blob", "sha": sha})
    if not tree:
        raise ReportError("there is no file to put in the pull request")
    made = _call("POST", f"/repos/{repo}/git/trees", token, {"base_tree": tree_sha, "tree": tree}, transport)
    new_tree = str(made.get("sha") or "")
    message = "Fix a bug the owner found on the laptop\n\n" + _scrub(entry.get("description") or "", token)[:200]
    made_commit = _call("POST", f"/repos/{repo}/git/commits", token,
                        {"message": message, "tree": new_tree, "parents": [parent]}, transport)
    commit_sha = str(made_commit.get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ReportError("the commit was not stored")
    branch = entry.get("branch") or branch_for(entry.get("id"))
    ref_name = "refs/heads/" + branch
    for n in range(1, 6):
        try:
            _call("POST", f"/repos/{repo}/git/refs", token, {"ref": ref_name, "sha": commit_sha}, transport)
            break
        except ReportError as exc:
            if "422" not in str(exc) or n == 5:
                raise
            ref_name = "refs/heads/" + branch + "-" + str(n + 1)
            if not _REF.fullmatch(ref_name):
                raise
    head = ref_name[len("refs/heads/"):]
    opened = _call("POST", f"/repos/{repo}/pulls", token, {
        "title": str(entry.get("title") or "Fix a bug found on the laptop")[:120],
        "head": head, "base": base, "body": entry.get("body") or "", "draft": False,
    }, transport)
    url = str(opened.get("html_url") or "")
    if "/pull/" not in url:
        raise ReportError("the pull request was not opened")
    return url


def _push_issue(entry, token, transport=None):
    repo = repo_name()
    opened = _call("POST", f"/repos/{repo}/issues", token, {
        "title": str(entry.get("title") or "Bug found on the laptop")[:120],
        "body": entry.get("body") or "",
    }, transport)
    url = str(opened.get("html_url") or "")
    if "/issues/" not in url:
        raise ReportError("the issue was not opened")
    return url


def _remember(entry):
    entry = dict(entry)
    entry["status"] = "pending"
    entry["attempts"] = int(entry.get("attempts") or 0)
    entry.setdefault("next", 0)
    _queue(entry)
    return entry


def submit_pr(payload, transport=None):
    """Open the pull request, or queue it when the token or the network is missing. Returns the sentence to say."""
    token = read_token()
    description = redact(payload.get("description") or "")
    title = ("Fix: " + (description or "a bug found on the laptop"))[:70]
    branch = branch_for(payload.get("item") or payload.get("id"))
    body = pr_body(description, payload.get("diff") or "(no diff was recorded)",
                   payload.get("tests"), payload.get("health") or "", token)
    entry = {
        "id": str(payload.get("item") or payload.get("id") or branch),
        "kind": "pr", "title": title, "body": body, "branch": branch,
        "description": description[:500], "files": _files(payload.get("files"), token),
        "attempts": 0, "next": 0, "status": "pending",
    }
    if not token:
        _remember(entry)
        return ("I don't have a GitHub token on this computer, so I saved the pull request and "
                "I'll try again when one is set. It is not merged.")
    try:
        url = _push_pr(entry, token, transport)
    except ReportError as exc:
        entry["attempts"] = 1
        entry["next"] = time.time() + 60
        _remember(entry)
        if "no file" in str(exc):
            return ("The fix is installed, but I couldn't pack the changed files into a pull request. "
                    "I saved the report and I'll try again later. It is not merged.")
        return "I couldn't reach GitHub, so I saved the pull request and I'll try again later. It is not merged."
    entry["status"] = "sent"
    entry["url"] = url
    rows = [row for row in load_reports() if not (str(row.get("id")) == entry["id"] and row.get("kind") == "pr")]
    rows.append(entry)
    save_reports(rows)
    return f"I opened a pull request: {url}. It is not merged."


def submit_issue(payload, transport=None):
    """File the failed fix as an issue, or queue that when it cannot be sent."""
    token = read_token()
    description = redact(payload.get("description") or "a bug on the laptop")
    entry = {
        "id": str(payload.get("item") or payload.get("id") or "issue"),
        "kind": "issue",
        "title": ("Bug: " + description)[:70],
        "body": issue_body(description, payload.get("detail") or "", token),
        "description": description[:500],
        "attempts": 0, "next": 0, "status": "pending",
    }
    if not token:
        _remember(entry)
        return ("I don't have a GitHub token on this computer, so I saved the issue and "
                "I'll try again when one is set.")
    try:
        url = _push_issue(entry, token, transport)
    except ReportError:
        entry["attempts"] = 1
        entry["next"] = time.time() + 60
        _remember(entry)
        return "I couldn't reach GitHub, so I saved the issue and I'll try again later."
    entry["status"] = "sent"
    entry["url"] = url
    rows = [row for row in load_reports() if not (str(row.get("id")) == entry["id"] and row.get("kind") == "issue")]
    rows.append(entry)
    save_reports(rows)
    return f"I opened an issue: {url}."


def retry(force=False, transport=None, now=None):
    """Send every saved report whose wait has passed. force=True tries them now."""
    now = time.time() if now is None else now
    token = read_token()
    if not token:
        pending = [row for row in load_reports() if row.get("status") == "pending"]
        if not pending:
            return "Nothing is waiting to send."
        return "I still don't have a GitHub token, so the saved report stays here."
    sent, waiting = [], []
    rows = load_reports()
    for row in rows:
        if row.get("status") != "pending":
            waiting.append(row)
            continue
        if not force and float(row.get("next") or 0) > now:
            waiting.append(row)
            continue
        try:
            if row.get("kind") == "issue":
                url = _push_issue(row, token, transport)
            else:
                url = _push_pr(row, token, transport)
        except ReportError:
            row = dict(row)
            row["attempts"] = int(row.get("attempts") or 0) + 1
            row["next"] = now + min(3600, 30 * (2 ** min(row["attempts"], 8)))
            waiting.append(row)
            continue
        row = dict(row, status="sent", url=url)
        waiting.append(row)
        sent.append(url)
    save_reports(waiting)
    if sent:
        return "I sent the saved report. " + " ".join(sent) + ". It is not merged."
    pending = [row for row in waiting if row.get("status") == "pending"]
    if pending:
        return "I still couldn't reach GitHub. The report stays saved."
    return "Nothing is waiting to send."
