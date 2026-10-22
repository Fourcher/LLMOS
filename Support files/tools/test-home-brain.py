#!/usr/bin/env python3
"""The home brain (llm "home" provider, tools/brain.py): another computer of the owner's lends its model over their own
network. Used while it answers, silently replaced by the model here when it doesn't; not blocked by the internet being
off (it isn't the internet); offered the short word-gated tool list like the local model; named honestly.
Run: python3 tools/test-home-brain.py (no VM)"""
import os, sys, socket, tempfile, threading
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", tempfile.mkdtemp(prefix="llmos-test-"))
os.environ.setdefault("LLMOS_ETC", tempfile.mkdtemp(prefix="llmos-etc-"))
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import agent, config, llm, i18n  # noqa: E402

fails = 0


def check(c, w):
    global fails
    print(("  ok   " if c else "  FAIL ") + w)
    if not c:
        fails += 1


class Ctx:
    headless = False

    def __init__(self):
        self.said = []

    def status(self, t):
        self.said.append(t)


srv = socket.socket()
srv.bind(("127.0.0.1", 0))
srv.listen(8)
port = srv.getsockname()[1]
def _answer():
    while True:
        cl = srv.accept()[0]
        cl.recv(1000)
        cl.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\"}")
        cl.close()


threading.Thread(target=_answer, daemon=True).start()
dead = socket.socket()                         # a forward with nothing behind it: accepts, then hangs up
dead.bind(("127.0.0.1", 0))
dead.listen(8)
threading.Thread(target=lambda: [dead.accept()[0].close() for _ in iter(int, 1)], daemon=True).start()

config.save_cloud({"provider": "home", "url": f"http://127.0.0.1:{port}/v1", "model": "huihui-ornith-1.5-9b", "key": "k",
                   "label": "Huihui Ornith 1.5 9B on Mac"})
config.settings.set("brain", "cloud")
check(llm.cloud_is_home(), "a home account is recognised")
check(llm.cloud_label() == "Huihui Ornith 1.5 9B on Mac", "it is named by its label")
llm._HOME_UP[:] = [0, False]
c = Ctx()
check(agent.route_for(c, "write me a letter") == "cloud", "while it answers, requests go to it")
config.settings.set("internet", "no")
llm._HOME_UP[:] = [0, False]
check(agent.route_for(c, "write me a letter") == "cloud", "the internet being off does not block it (it is not the internet)")
check(agent._escalation_target(c, "local") == ("cloud", None), "a timid refusal here escalates to it")
config.settings.set("internet", "yes")

config.save_cloud(dict(config.cloud(), url=f"http://127.0.0.1:{dead.getsockname()[1]}/v1"))
llm._HOME_UP[:] = [0, False]
check(agent.route_for(Ctx(), "write me a letter") == "local", "a forward that accepts but has no model behind it counts as down")
config.save_cloud(dict(config.cloud(), url="http://127.0.0.1:1/v1"))
llm._HOME_UP[:] = [0, False]
c = Ctx()
check(agent.route_for(c, "write me a letter") == "local", "when it doesn't answer, the model here does")
check(c.said == [], f"... without a word about it: {c.said}")
check(agent._escalation_target(c, "local") != ("cloud", None), "no escalation to a computer that isn't answering")

check(i18n.t("d_home_using", model="X") == "asking X on your other computer", "status says 'your other computer', not 'online'")
class Said(Ctx):
    def brain(self, on, label):
        self.badge = (on, label)
cs = Said()
config.save_cloud(dict(config.cloud(), label="Ministral 3B on Jordans-Mac-Mini"))
agent._going_online(cs, False)
check(cs.said == ["asking Ministral 3B on your other computer"], f"the step names the computer once: {cs.said}")
js = open(os.path.join(_ROOT, "usr/share/llmos/desk/desk.js"), encoding="utf-8").read()
check('m.home ? (m.label || "")' in js, "the answer's badge has no 'online' for a home computer")
src = open(os.path.join(_ROOT, "usr/lib/llmos/llmos/agent.py"), encoding="utf-8").read()
check('where == "cloud" and not llm.cloud_is_home()' in src, "the home model gets the short word-gated tool list")
dsk = open(os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py"), encoding="utf-8").read()
check("None of it goes online." in dsk, "the privacy answer says a home brain is not online")

config.save_cloud({"provider": "anthropic", "model": "claude-opus-5-5", "key": "sk-ant-x"})
check(not llm.cloud_is_home(), "an online account is not 'home'")
config.settings.set("internet", "no")
check(agent.route_for(Ctx(), "write me a letter") == "local", "an online account still stops when the internet is off")
# tools/brain.py's laptop set-up script fills in and compiles (a stray % once crashed the supervisor)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain  # noqa: E402
script = (brain.SETUP.replace("@PORT@", "8090").replace("@MODEL@", repr("huihui-ornith-1.5-9b"))
          .replace("@KEY@", repr("k%s'\"")).replace("@LABEL@", repr("Huihui 9B on Mac")))
try:
    compile(script, "setup", "exec")
    check("@" not in script, "brain.py's laptop set-up script fills in and compiles, quotes and % in the key included")
except SyntaxError as e:
    check(False, f"brain.py's set-up script: {e}")
if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
