#!/usr/bin/env python3
"""Host-side test of the connector subsystem (llmos/mcp.py + tools): add a real stdio MCP server
(tools/fake-mcp-server.py), handshake, list its tools, register them beside the built-in tools, call them,
and check risk mapping, enable/disable/remove, and that a broken connector never breaks the OS.
Run: python3 tools/test-connectors.py (no network)."""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import mcp, tools  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake-mcp-server.py")
CMD = f'"{sys.executable}" "{SERVER}"'      # quoted: the path may contain spaces

print("add + probe")
try:
    mcp.add("weather", "http", url="not-a-url")
    check(False, "an http connector with a bad URL is refused")
except mcp.McpError:
    check(True, "an http connector with a bad URL is refused")
spec = mcp.add("demo", "stdio", command=CMD)
check(mcp.get("demo") is not None, "the connector is stored")
ok, toolz = mcp.probe(spec)
check(ok and {t["name"] for t in toolz} == {"echo", "add"}, f"probe starts it and lists its tools: {ok}")

print("register into the tool list")
res = tools.sync_connectors()
check(res.get("demo") == 2, f"sync reports 2 tools: {res}")
names = {s["function"]["name"] for s in tools.schemas()}
check("demo__echo" in names and "demo__add" in names, "connector tools appear in the agent's schema list")
check(tools.REGISTRY["demo__echo"].risk == "read", "a readOnlyHint tool maps to READ")
check(tools.REGISTRY["demo__add"].risk == "change", "a tool with no hint maps to CHANGE")
check(tools.REGISTRY["demo__echo"].schema()["function"]["description"].startswith("[connector: demo]"), "the description is namespaced")

print("call a connector tool")
check(mcp.call("demo", "echo", {"text": "hi"}) == "echo: hi", "echo works through mcp.call")
check(mcp.call("demo", "add", {"a": 2, "b": 3}) == "5", "add works and flattens the text content")
# the registered tool fn is what the agent runs via execute()
out = tools.REGISTRY["demo__echo"].fn({"text": "again"}, None)
check(out == "echo: again", "the registered tool fn routes to the connector")
check(mcp.call("demo", "nope", {}).startswith("error from the connector"), "an unknown tool returns the connector's error")

print("disable / enable / remove")
mcp.set_enabled("demo", False)
tools.sync_connectors()
check("demo__echo" not in tools.REGISTRY, "disabling drops the tools from the registry")
mcp.set_enabled("demo", True)
tools.sync_connectors()
check("demo__echo" in tools.REGISTRY, "enabling brings them back")
check(mcp.remove("demo") and mcp.get("demo") is None, "remove uninstalls the connector")
tools.sync_connectors()
check("demo__echo" not in tools.REGISTRY, "its tools are gone after removal")

print("a broken connector does not break the OS")
mcp.add("broken", "stdio", command=f"{sys.executable} -c \"import sys;sys.exit(1)\"")
res = tools.sync_connectors()
check(isinstance(res.get("broken"), str) and res["broken"].startswith("error"), f"a failing connector is reported, not fatal: {res.get('broken')}")
check(isinstance(tools.schemas(), list), "schemas() still works with a broken connector present")
mcp.remove("broken")

print("a connector that stalls half-way through a line cannot hang the request")
import time  # noqa: E402
mcp.add("slow", "stdio", command=f'"{sys.executable}" "{SERVER}" --stall')
c = mcp._client(mcp.get("slow"))
t0 = time.time()
try:
    c.call_tool("stall", {}, timeout=2)
    stalled = "answered"
except mcp.McpError as e:
    stalled = str(e)
took = time.time() - t0
check("timed out" in stalled and took < 6, f"the call gives up at its deadline ({took:.1f} s): {stalled}")
check(mcp.call("slow", "echo", {"text": "back"}) == "echo: back", "the connector is started afresh and answers the next call")
mcp.remove("slow")

mcp.shutdown()
print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
