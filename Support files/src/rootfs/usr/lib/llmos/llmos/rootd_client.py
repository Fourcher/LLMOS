"""rootd_client: how the desk asks rootd to do one privileged verb.

call(verb, **args) -> str. As root (os.geteuid() == 0) the verb runs in this process through rootd.VERBS, with the
same checks, so a root desk behaves as it does today. Otherwise the request goes to rootd's socket: one JSON request,
one JSON reply. Stdlib only. Not called by anything yet.
"""
import json
import os
import socket

from . import rootd

SOCK = "/run/llmos-rootd/root.sock"
TIMEOUT = 30.0
MAX_REPLY = 1024 * 1024
NOT_RUNNING = "the system helper is not running"


class RootdError(Exception):
    pass


def _encode(verb, args):
    try:
        return json.dumps({"verb": verb, "args": args}).encode("utf-8")
    except (TypeError, ValueError):
        raise RootdError("bad args: not JSON-serialisable")


def _in_process(verb, args):
    fn = rootd.VERBS.get(verb)
    if fn is None:
        raise RootdError("unknown verb")
    try:
        return fn(args)
    except ValueError as e:
        raise RootdError(str(e))
    except Exception as e:  # noqa: BLE001 - same rule as rootd: no traceback to the caller
        raise RootdError(f"failed: {type(e).__name__}")


def _over_socket(payload, timeout):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.settimeout(timeout)
        try:
            s.connect(SOCK)
        except OSError:
            raise RootdError(NOT_RUNNING)
        try:
            s.sendall(payload)
            s.shutdown(socket.SHUT_WR)
            data = b""
            while True:
                part = s.recv(65536)
                if not part:
                    break
                data += part
                if len(data) > MAX_REPLY:
                    raise RootdError("reply too large")
        except socket.timeout:
            raise RootdError("the system helper did not answer")
        except OSError:
            raise RootdError("the system helper failed the request")
    finally:
        s.close()
    return data


def _parse(data):
    try:
        reply = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise RootdError("bad reply")
    if not isinstance(reply, dict) or not isinstance(reply.get("ok"), bool):
        raise RootdError("bad reply")
    if reply["ok"]:
        out = reply.get("out")
        if not isinstance(out, str):
            raise RootdError("bad reply")
        return out
    err = reply.get("error")
    raise RootdError(err if isinstance(err, str) else "failed")


def call(verb, _timeout=None, **args):
    """_timeout (seconds, default TIMEOUT) is the socket wait for rootd's reply. It is not sent as an arg.
    The in-process (root) path runs the verb directly and ignores it."""
    payload = _encode(verb, args)
    if os.geteuid() == 0:
        return _in_process(verb, args)
    timeout = TIMEOUT if _timeout is None else _timeout
    return _parse(_over_socket(payload, timeout))
