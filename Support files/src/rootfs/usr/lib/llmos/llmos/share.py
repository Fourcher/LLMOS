"""Sharing one folder with the other computers on the same network ("share this folder with my other computer"):
a read-only web page of the folder, at an address with a random code in it, reachable only from local network
addresses. The firewall opens its one port only while a share is on; "stop sharing" closes both.
Run as its own process: python3 -m llmos.share <folder> <code> <port>."""
import html
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import urllib.parse

from . import config

PORT = 8090
_STATE = "share.json"


def lan_ips():
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return re.findall(r"inet (\d+\.\d+\.\d+\.\d+)/", out)


def current():
    """{'folder', 'code', 'port', 'pid'} of the share that is on, or None."""
    try:
        with open(config.data(_STATE), encoding="utf-8") as f:
            st = json.load(f)
        os.kill(int(st["pid"]), 0)
        return st
    except (OSError, ValueError, KeyError, TypeError):
        return None


def urls(st):
    return [f"http://{ip}:{st['port']}/{st['code']}/" for ip in lan_ips()]


def start(folder):
    """(ok, state or error words)."""
    from . import system
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        return False, f"{folder} is not a folder"
    stop()
    code = secrets.token_urlsafe(6)
    env = dict(os.environ, PYTHONPATH="/usr/lib/llmos")
    p = subprocess.Popen([sys.executable, "-m", "llmos.share", folder, code, str(PORT)], env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    st = {"folder": folder, "code": code, "port": PORT, "pid": p.pid}
    with open(config.data(_STATE), "w", encoding="utf-8") as f:
        json.dump(st, f)
    system.apply_firewall()           # the share's port opens (local network only)
    return True, st


def stop():
    from . import system
    st = current()
    if st:
        try:
            os.kill(int(st["pid"]), signal.SIGTERM)
        except OSError:
            pass
    try:
        os.remove(config.data(_STATE))
    except OSError:
        pass
    if st:
        system.apply_firewall()       # and closes again
    return st


def _serve(folder, code, port):
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import ipaddress

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=folder, **k)

        def _ok(self):
            try:
                ip = ipaddress.ip_address(self.client_address[0])
            except ValueError:
                return False
            if not (ip.is_private or ip.is_loopback or ip.is_link_local):
                return False
            return self.path.startswith(f"/{code}/")

        def translate_path(self, path):       # the code is part of every address, not a folder
            return super().translate_path(path[len(code) + 1:] if path.startswith(f"/{code}/") else "/nonexistent-")

        def do_GET(self):
            if not self._ok():
                self.send_error(404)
                return
            # no hidden files, nothing outside the folder (SimpleHTTPRequestHandler already keeps paths inside it)
            if any(part.startswith(".") for part in urllib.parse.unquote(self.path.split("?")[0]).split("/") if part):
                self.send_error(404)
                return
            super().do_GET()

        def do_HEAD(self):
            if not self._ok():
                self.send_error(404)
                return
            super().do_HEAD()

        def list_directory(self, path):
            try:
                names = sorted((n for n in os.listdir(path) if not n.startswith(".")), key=str.lower)
            except OSError:
                self.send_error(404)
                return None
            rel = urllib.parse.unquote(self.path.split("?")[0])[len(code) + 1:]
            rows = "".join(f'<li><a href="{urllib.parse.quote(n)}{"/" if os.path.isdir(os.path.join(path, n)) else ""}">'
                           f'{html.escape(n)}{"/" if os.path.isdir(os.path.join(path, n)) else ""}</a></li>' for n in names)
            body = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                    f"<title>{html.escape(os.path.basename(folder))}</title>"
                    f"<body style='font:16px system-ui;margin:24px'><h2>{html.escape(os.path.basename(folder) + rel)}</h2>"
                    f"<p style='color:#666'>Shared from LLM OS. Click a file to open or save it.</p><ul>{rows}</ul>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None

        def log_message(self, *a):
            pass

    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__":
    _serve(sys.argv[1], sys.argv[2], int(sys.argv[3]))
