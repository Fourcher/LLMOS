#!/usr/bin/env python3
"""Stand-in for macOS /usr/libexec/authopen, for tests of LLM OS Setup's writer.

`fake-authopen.py -stdoutpipe -o FLAGS PATH` opens PATH with FLAGS as the current user (no password) and sends
the descriptor over stdout, which must be a socket, with SCM_RIGHTS -- what the real authopen does once the
person has typed their password. FAKE_AUTHOPEN=cancel exits like a cancelled prompt (no descriptor, nothing on
stderr); FAKE_AUTHOPEN=denied exits like macOS refusing the open.
"""
import os
import socket
import struct
import sys

args = sys.argv[1:]
if len(args) != 4 or args[0] != "-stdoutpipe" or args[1] != "-o":
    sys.stderr.write("usage: fake-authopen.py -stdoutpipe -o FLAGS PATH\n")
    sys.exit(2)
mode = os.environ.get("FAKE_AUTHOPEN", "")
if mode == "cancel":
    sys.exit(1)
if mode == "denied":
    sys.stderr.write(f"authopen: unable to open {args[3]}: Operation not permitted\n")
    sys.exit(1)
fd = os.open(args[3], int(args[2]))
out = socket.socket(fileno=1)
out.sendmsg([b"\0"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack("i", fd))])
