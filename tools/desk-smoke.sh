#!/bin/bash
# Graphical desk acceptance on the SHIPPED arm64 image, on a throw-away
# overlay: first-boot wizard, requests with windows, lock/unlock, background
# task -> "while you were away". The serial line is a test shell; the desk
# is driven through its control socket (`llmos say`, `llmos desk-ctl`) and
# photographed with QEMU's screendump after each step (run/shot-desk-*.png).
#   usage: tools/desk-smoke.sh [image] [ram_mb]     (LLMOS_HOSTGPU_URL optional)
cd "/Volumes/Files/Claude Work Area/LLMOS"
V="python3 tools/vmctl.py"; S=run/tser.sock; L=run/boot-serial.log
IMG=${1:-dist/llmos-arm64.qcow2}; RAM=${2:-4096}
sh() { tools/tsh "$1" "${2:-120}"; }
shot() { sleep "${2:-2}"; python3 tools/screendump.py run/tmon.sock "run/shot-desk-$1.png"; }
ctl() { sh "llmos desk-ctl $1 | head -c 600; echo" "${2:-120}"; }
say() { sh "llmos say \"$1\" | head -c 700; echo" "${2:-400}"; }
state() { sh "llmos desk-state | python3 -c 'import json,sys; s=json.load(sys.stdin); print(s[\"screen\"], [w[\"title\"] for w in s[\"windows\"]])'" 30; }

printf '\n======== desk: first boot of %s (%s MB) ========\n' "$IMG" "$RAM"
LLMOS_TESTSHELL=1 tools/boot-target.sh "$IMG" "$RAM" >/dev/null
$V wait $L 'LLM OS test shell' 300 >/dev/null && echo "  -> test shell up"
sh 'for i in $(seq 1 60); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done; ls /run/llmos/desk.sock && pgrep -a "labwc|desk-app" | cut -c1-50' 200
sleep 6; state; shot wizard-0 1
echo "--- wizard: welcome, language, name, time zone, autonomy, internet, passphrase (each step photographed)"
ctl "wizard welcome"; shot wizard-1 1
ctl "wizard language en"; shot wizard-2 1
ctl "wizard name Jordan"; shot wizard-3 1
ctl "js \"document.getElementById('wz-tz').value='tok'; document.getElementById('wz-tz').dispatchEvent(new Event('input'))\""; shot wizard-3b 1
ctl "wizard timezone America/Phoenix"; shot wizard-4 1
ctl "wizard autonomy hands-off"; shot wizard-5 1
ctl "wizard internet yes"; shot wizard-6 1
ctl "wizard passphrase correct horse battery" 300; shot wizard-7 1
ctl "wizard done"; sleep 3; state; shot desk-fresh 2
echo "--- requests"
say "how much disk space do I have?"; shot disk 1
say "settings"; shot settings 1
say "make everything teal with square corners"; shot teal 2
say "show me a photo of the Matterhorn"; shot photo 3
say "in 1 minute, tell me one real fact about Mars"; shot sched 1
say "clear"
echo "--- files, screenshot, animations, the empty desk"
say "show my files"; shot files 1
say "take a screenshot"; shot screenshot 2
say "add milk to my shopping list"; say "remember to call Sam"; say "show my lists"; shot lists 1
say "set a timer for 1 minute"
say "fewer animations"; sh 'python3 -c "import sys; sys.path.insert(0, \"/usr/lib/llmos\"); from llmos import config; print(\"motion now:\", config.settings.get(\"appearance.motion\"))"' 30
say "turn animations on"
say "open the settings"; shot settings-2 1
say "clear"; ctl "js \"document.getElementById('reply-close').click()\""; shot hero 2
echo "--- lock / unlock"
ctl "lock"; shot lock 2; state
sh 'echo "vault mounted after lock: $(mount | grep -c " /root ")"; cryptsetup status llmos-vault 2>&1 | head -1' 30
ctl "unlock wrong one"; shot lock-wrong 2
ctl "unlock correct horse battery"; sleep 3; state; shot unlocked 1
echo "--- waiting for the scheduled task and the timer to land in 'While you were away'"
sleep 75; ctl "state" 30 >/dev/null; sleep 22; state; shot away 1
sh 'llmos desk-state | python3 -c "import json,sys; s=json.load(sys.stdin); print([r for w in s[\"windows\"] if w[\"title\"].startswith(\"While\") for r in w.get(\"rows\", [])][:6])"' 30
sh 'free -m | sed -n 2p; ps -o rss,comm | sort -rn | head -4' 30
echo "======== desk smoke done $(date +%H:%M:%S) ========"
