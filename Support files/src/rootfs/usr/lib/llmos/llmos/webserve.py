"""The local website ("start a web server here", "preview this page"): a folder served to this computer only.
Unlike a bare `python3 -m http.server` it answers only requests addressed to 127.0.0.1/localhost (another site in
the browser cannot reach it through a rebound DNS name), never serves hidden files or folders (.llmos, .ssh ...),
and never follows a symlink out of the folder.
Run as: python3 -m llmos.webserve <port> <folder>."""
import os
import sys
import urllib.parse

_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def handler(folder):
    from http.server import SimpleHTTPRequestHandler
    top = os.path.realpath(folder).rstrip("/") or "/"

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=folder, **k)

        def _ok(self):
            host = (self.headers.get("Host") or "").strip().lower()
            name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
            if name not in _HOSTS:
                return False
            path = urllib.parse.unquote(self.path.split("?", 1)[0].split("#", 1)[0])
            return not any(part.startswith(".") for part in path.split("/") if part)

        def translate_path(self, path):
            p = super().translate_path(path)
            real = os.path.realpath(p)
            if real != top and not real.startswith(top + "/"):
                return os.path.join(top, ".nonexistent-outside")
            return p

        def list_directory(self, path):
            # hidden entries are not listed either
            import html
            import io
            try:
                names = sorted((n for n in os.listdir(path) if not n.startswith(".")), key=str.lower)
            except OSError:
                self.send_error(404)
                return None
            shown = html.escape(urllib.parse.unquote(self.path.split("?", 1)[0]))
            rows = "".join(
                f'<li><a href="{urllib.parse.quote(n)}{"/" if os.path.isdir(os.path.join(path, n)) else ""}">'
                f'{html.escape(n)}{"/" if os.path.isdir(os.path.join(path, n)) else ""}</a></li>' for n in names)
            body = (f"<!doctype html><meta charset=utf-8><title>{shown}</title><h2>{shown}</h2><ul>{rows}</ul>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return io.BytesIO(body)

        def do_GET(self):
            if not self._ok():
                self.send_error(404)
                return
            super().do_GET()

        def do_HEAD(self):
            if not self._ok():
                self.send_error(404)
                return
            super().do_HEAD()

        def log_message(self, *a):
            pass

    return H


def serve(port, folder):
    from http.server import ThreadingHTTPServer
    ThreadingHTTPServer(("127.0.0.1", port), handler(folder)).serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]), sys.argv[2])
