#!/bin/bash
# Compliance pass against the original brief, on the SHIPPED arm64 image:
#   phase 1 (host-GPU mode, 4 GB): security facts from inside the OS, then the
#           brief's own examples as desk requests (brightness, YouTube, real
#           quote, research with a source, a composed panel, a schedule, a
#           downloaded browser, a terminal program)
#   phase 2 (model inside the VM, 6 GB): the owner downloads and switches to a
#           different model from the catalog (verified official release)
# Output: run/spec-check.log, frames run/shot-spec-*.png.
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
V="python3 tools/vmctl.py"; S=run/tser.sock; L=run/boot-serial.log
IMG=${1:-dist/llmos-arm64.qcow2}; PHASES=${2:-12}
sh() { tools/tsh "$1" "${2:-120}" | grep -vE '^\s*$|^\[vmctl|^# $|^~ # $|^llmos |^"import|^\(sys|^"\]\)|^chr\('; }
shot() { sleep "${2:-2}"; python3 tools/screendump.py run/tmon.sock "run/shot-spec-$1.png"; }
ctl() { sh "llmos desk-ctl \"$1\" | head -c 300; echo" "${2:-120}"; }
say() { sh "llmos say \"$1\" | python3 -c 'import json,sys; s=json.load(sys.stdin); print(\"reply:\", s[\"reply\"][:260].replace(chr(10),\" \")); print(\"windows:\", [w[\"title\"] for w in s[\"windows\"]], \"apps:\", s[\"apps\"])'" "${2:-400}"; }
wait_desk() { sh 'for i in $(seq 1 60); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done; U=$(cat /run/llmos/model_url 2>/dev/null || echo http://127.0.0.1:8080); for i in $(seq 1 300); do curl -s $U/health | grep -q ok && break; sleep 2; done; echo "model ready at $U"' 700; }
onboard() { for step in "language en" "name Jordan" "timezone America/Phoenix" "autonomy hands-off" "internet yes" "tor no" "passphrase correct horse battery" "done"; do ctl "wizard $step" 300 >/dev/null; done; sleep 2; }
# a request that raises a confirmation: start it, answer the dialog, wait for the turn
ask_dialog() {   # $1 request, $2 answer
  sh "(llmos say \"$1\" > /tmp/dlg.json 2>&1 &); for i in \$(seq 1 45); do llmos desk-state | grep -q '\"dialogs\": \[{' && break; sleep 2; done; llmos desk-ctl dialog $2 >/dev/null; for i in \$(seq 1 120); do [ -s /tmp/dlg.json ] && break; sleep 2; done; python3 -c 'import json; s=json.load(open(\"/tmp/dlg.json\")); print(\"reply:\", s[\"reply\"][:200].replace(chr(10),\" \"))'" 400
}

case "$PHASES" in *1*) ;; *) PHASES1=skip ;; esac
if [ -z "${PHASES1:-}" ]; then
printf '\n======== phase 1: host-GPU mode, security facts + the brief'"'"'s examples ========\n'
LLMOS_TESTSHELL=1 LLMOS_HOSTGPU_URL=${LLMOS_HOSTGPU_URL:-http://10.0.2.2:8080} tools/boot-target.sh "$IMG" 4096 >/dev/null
$V wait $L 'LLM OS test shell' 300 >/dev/null && echo "  -> test shell up"
wait_desk; onboard
echo "--- security facts (from inside the OS)"
sh 'echo "root password: $(passwd -S root 2>/dev/null | cut -d" " -f2 || grep ^root /etc/shadow | cut -d: -f2 | cut -c1-2)"; echo "listening sockets:"; netstat -tuln 2>/dev/null | awk "NR>2 {print \"  \" \$1, \$4}"; echo "firewall input policy: $(nft list chain inet llmos input | grep -o "policy [a-z]*")"; echo "firewall output rules: $(nft list chain inet llmos output | grep -cE "accept|drop")"; echo "vault: $(cryptsetup status llmos-vault 2>/dev/null | head -1)"; echo "mounts: $(grep -E " /root | /tmp " /proc/mounts | cut -d" " -f1-3 | tr "\n" ";")"; echo "cron jobs: $(ls /etc/periodic/*/ 2>/dev/null | wc -l) / crontab lines: $(crontab -l 2>/dev/null | grep -cv "^#")"; echo "outbound now (established): $(netstat -tn 2>/dev/null | grep -c ESTABLISHED)"; echo "settings.json perms: $(stat -c %a /etc/llmos/settings.json)"; echo "packages: $(apk info 2>/dev/null | wc -l) (all from $(cut -d/ -f3 /etc/apk/repositories | sort -u | tr "\n" " "))"' 60
echo "--- with the internet off, the host's model (on whichever port) must stay reachable"
say "turn the internet off"
sh 'nft list chain inet llmos output | grep -E "policy|daddr 10.0.2.2"' 30
say "what is 12 times 34?" 200
ask_dialog "allow internet use" yes
sh 'nft list chain inet llmos output | grep -o "policy [a-z]*"' 30
echo "--- the brief's examples, on the desk"
say "set the brightness to 60"; shot brightness 1
say "set the volume to 30"
say "pull up a YouTube video of ocean waves and play it" 300; shot youtube 20
say "stop the video"
say "give me a real quote from Marcus Aurelius" 300; shot quote 2
say "what's the weather in Tokyo right now? one sentence with the source" 300; shot research 2
say "show me my disk, memory and scheduled tasks in one panel" 300; shot panel 2
say "every weekday at 8 give me a summary of my day"; say "tasks"; shot tasks 1
say "remember that I'm vegetarian"; say "what do you know about me?"
say "install htop and open it" 600; shot htop 6; ctl "js document.activeElement && document.activeElement.blur()" >/dev/null
sh 'pkill -x htop; pkill -x foot; echo closed' 30 >/dev/null
say "install a web browser and open example.com in it" 900; shot browser 40
sh 'pgrep -a firefox | head -1 | cut -c1-60; pkill -x firefox-esr; pkill -f firefox; echo closed' 30
say "audit"; shot audit 1
sh 'sync' 10 >/dev/null
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; sleep 3
fi

case "$PHASES" in *2*) ;; *) echo "======== spec check done $(date +%H:%M:%S) ========"; exit 0 ;; esac
printf '\n======== phase 2: model inside the VM (6 GB): download and switch to another catalog model ========\n'
LLMOS_TESTSHELL=1 tools/boot-target.sh "$IMG" 6144 >/dev/null
$V wait $L 'LLM OS test shell' 300 >/dev/null && echo "  -> test shell up"
wait_desk; onboard
say "models"; shot models 1
t0=$(date +%s); say "download gemma 4 e2b" 1500; echo "   (download took $(( $(date +%s) - t0 )) s)"
sh 'ls -la /var/lib/llmos/models/ | tail -3; sha256sum /var/lib/llmos/models/gemma-4-E2B-it-Q4_0.gguf 2>/dev/null | cut -c1-20' 120
t0=$(date +%s); say "use gemma 4 e2b" 900; echo "   (switch took $(( $(date +%s) - t0 )) s)"
say "what is 12 times 34?" 300; shot gemma 1
say "show me my disk, memory and scheduled tasks in one panel" 300; shot panel2 2
sh 'free -m | sed -n 2p; cat /etc/llmos/settings.json | python3 -c "import json,sys; print(\"model setting:\", json.load(sys.stdin).get(\"model\"))"; pgrep -a llama-server | cut -c1-120' 30
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null
echo "======== spec check done $(date +%H:%M:%S) ========"
