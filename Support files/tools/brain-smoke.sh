#!/bin/bash
# In-VM smoke test of the 1.3 features on the running arm64 test VM (booted with tools/boot-target.sh,
# code pushed with tools/push.sh, tools/fake-cloud.py --port 8099 running on the host): the first-run
# quiz and its online-model step, the brain setting, the "ask claude:" route and the online orb, the
# audit trail of what left the computer, routines (a repeated request replayed without the model), the
# settings panel's new sections and the three desk layouts. Every step is photographed
# (run/shot-brain-*.png). Leaves the VM running.  usage: tools/brain-smoke.sh
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
ctl() { tools/tsh "llmos desk-ctl $1" "${2:-60}"; }
say() { tools/tsh "llmos say \"$1\" | python3 -c 'import json,sys; s=json.load(sys.stdin); print(\"reply:\", s[\"reply\"][:240].replace(chr(10),\" \")); print(\"windows:\", [w[\"title\"] for w in s[\"windows\"]], \"dialogs:\", len(s[\"dialogs\"]))'" "${2:-300}"; }
state() { tools/tsh "llmos desk-state | python3 -c 'import json,sys; s=json.load(sys.stdin); print(\"screen\", s[\"screen\"], \"busy\", s[\"busy\"], \"dialogs\", [d[\"title\"] for d in s[\"dialogs\"]], [w[\"title\"] for w in s[\"windows\"]])'" 30; }
shot() { sleep "${2:-2}"; python3 tools/screendump.py run/tmon.sock "run/shot-brain-$1.png"; echo "[shot $1]"; }
audit() { tools/tsh "tail -n ${1:-4} /root/.llmos/audit.log | cut -c1-230" 30; }
# a request that raises a dialog: start it inside the VM (a subshell, so the console is free), photograph,
# answer, then show the reply
ask_dialog() { tools/tsh "( llmos say \"$1\" > /tmp/say.out 2>&1 & )" 10; sleep "${4:-5}"; shot "$3" 0; state; ctl "dialog $2"; sleep 6; tools/tsh 'cut -c1-300 /tmp/say.out' 30; }
restart_desk() { tools/tsh 'pkill -f "[l]lmos desk-app"; pkill -x labwc; pkill -x seatd; sleep 1; rm -f /run/seatd.sock /run/llmos/desk.sock; (setsid /usr/libexec/llmos-desk < /dev/null > /run/llmos/desk.log 2>&1 &); for i in $(seq 1 40); do [ -S /run/llmos/desk.sock ] && break; sleep 1; done; echo "desk socket: $([ -S /run/llmos/desk.sock ] && echo yes || echo no)"' 90; sleep 4; }

echo "### brain smoke $(date '+%H:%M:%S')"
echo "--- internet on first (a previous run may have left the firewall closed; loosening asks, so answer yes)"
ask_dialog "allow internet use" yes internet-on 4
echo "--- fetch the staged JSON and helpers from the host, make it a first run again"
tools/tsh 'cd /tmp && for f in cloud.json quiz.json quiz2.json brain-prep.py brain-check.py; do wget -qO $f.new http://10.0.2.2:8765/run/$f && mv $f.new $f || echo "fetch failed: $f"; done; python3 /tmp/brain-prep.py' 60
restart_desk
state; shot wizard-0 3
echo "--- the first run: welcome, language, name, time zone, then the quiz (sliders), then the online-model step"
ctl "wizard welcome"
ctl "wizard language en"
ctl "wizard name Jordan"
ctl "wizard timezone America/Phoenix"; shot quiz 2
tools/tsh 'llmos desk-ctl wizard profile "$(cat /tmp/quiz.json)"' 60; shot cloud-step 2
tools/tsh 'llmos desk-ctl wizard cloud "$(cat /tmp/cloud.json)"' 120; shot after-cloud 5
ctl "wizard passphrase"; shot done-step 2
ctl "wizard done"; sleep 3; state; shot desk-fresh 3
echo "--- what the quiz decided, and the account"
tools/tsh 'python3 /tmp/brain-check.py' 30

echo "--- the online route: 'ask claude: …' goes to the stand-in (orb online, activity line, audit)"
tools/tsh '( llmos say "ask claude: what is two plus two" > /tmp/say1.out 2>&1 & )' 10; sleep 5; shot online-orb 0; sleep 7; tools/tsh 'cut -c1-300 /tmp/say1.out' 30
audit 4
echo "--- brain=ask: a small request stays here (no dialog); a big one asks first (answered: keep it here)"
say "what is the uptime of this computer" 240
ask_dialog "write me a cover letter for a nursing job" no ask-dialog 6
echo "--- routines: the same small request again is replayed without the model (audit: routine)"
say "what is the uptime of this computer" 240
audit 5
tools/tsh 'python3 /tmp/brain-check.py' 30

echo "--- 'use the online model for everything' loosens a policy: a dialog, answered yes; then everything goes online"
ask_dialog "use the online model for everything" yes brain-dialog 4
say "what is three plus four" 240
audit 3
shot desk-cloud 1

echo "--- settings panel: where it thinks, guidance, desk layout"
say "open the settings" 120; shot settings 3
echo "--- desk layouts"
say "give me a windows style desk" 120; shot layout-windows 4
say "open the models" 120; shot layout-windows-2 3
say "give me a mac style desk" 120; shot layout-mac 4
say "give me a clean desk" 120; shot layout-clean 4

echo "--- quiz 2 (offline, most capable, standard caution, calm screen): brain forced local, firewall closed"
tools/tsh 'python3 /tmp/brain-prep.py' 30; restart_desk
ctl "wizard welcome"; ctl "wizard language en"; ctl "wizard name Jordan"; ctl "wizard timezone America/Phoenix"
tools/tsh 'llmos desk-ctl wizard profile "$(cat /tmp/quiz2.json)"' 60; shot quiz2-next 2
ctl "wizard passphrase"; ctl "wizard done"; sleep 3; state
tools/tsh 'python3 /tmp/brain-check.py; echo "firewall drop rules: $(nft list ruleset 2>/dev/null | grep -c drop)"' 30
echo "--- restore: internet on (a dialog)"
ask_dialog "allow internet use" yes restore 4
tools/tsh 'python3 /tmp/brain-check.py' 30
echo "### done $(date '+%H:%M:%S')"
