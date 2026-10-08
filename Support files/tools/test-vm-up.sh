#!/bin/bash
# Boot a fresh test VM from a shipped image and make it ready for tools/usecase-run.py: test shell on the serial line,
# first-boot wizard finished (hands-off, internet on, the test passphrase), the test mail server running.
#   usage: tools/test-vm-up.sh [image] [ram_mb]      (default: dist/llmos-arm64.qcow2, 4096)
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
V="python3 tools/vmctl.py"; L=run/boot-serial.log
IMG=${1:-dist/llmos-arm64.qcow2}; RAM=${2:-4096}
sh() { tools/tsh "$1" "${2:-120}"; }
ctl() { sh "llmos desk-ctl $1 | head -c 300; echo" "${2:-120}"; }
[ -f run/target.pid ] && kill "$(cat run/target.pid)" 2>/dev/null; sleep 2
curl -s -o /dev/null http://127.0.0.1:8765/src/install.sh || {          # the VM fetches the mail fixture and payloads from here
    nohup python3 -m http.server 8765 --bind 127.0.0.1 --directory "$PWD" > run/httpd.log 2>&1 &
    echo $! > run/httpd.pid; sleep 1; }
LLMOS_TESTSHELL=1 tools/boot-target.sh "$IMG" "$RAM" >/dev/null
$V wait $L 'LLM OS test shell' 300 >/dev/null && echo "test shell up" || { echo "no test shell"; exit 1; }
sh 'for i in $(seq 1 60); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done; ls /run/llmos/desk.sock' 200
ctl "wizard welcome"; ctl "wizard language en"; ctl "wizard name Jordan"
ctl "wizard timezone America/Phoenix"; ctl "wizard autonomy hands-off"; ctl "wizard internet yes"
ctl "wizard passphrase correct horse battery" 300; ctl "wizard done"
sh 'wget -qO /tmp/mf.sh http://10.0.2.2:8765/tools/mailfixture.sh && sh /tmp/mf.sh >/tmp/mf.log 2>&1; tail -1 /tmp/mf.log' 300
sh 'llmos desk-state | head -c 120; echo' 30
echo "TEST VM READY"
