#!/bin/bash
# Edge cases on the graphical desk (shipped arm64 image on an overlay, test
# shell on the serial line, requests through the desk's control socket).
# Covers the autonomy/internet policies as dialogs, a model outage and
# recovery, cancelling, odd input, many windows, a non-Latin interface
# language, no-account email, focus mode, and persistence across a reboot.
#   usage: tools/desk-edge.sh [image] [ram_mb]   (LLMOS_HOSTGPU_URL makes it fast)
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
V="python3 tools/vmctl.py"; S=run/tser.sock; L=run/boot-serial.log
IMG=${1:-dist/llmos-arm64.qcow2}; RAM=${2:-4096}
sh() { tools/tsh "$1" "${2:-120}" | grep -vE '^\s*$|^\[vmctl|^# $|^~ # $|^llmos |^"import|^\(sys|^"\]\)|^chr\(' ; }
shot() { sleep "${2:-2}"; python3 tools/screendump.py run/tmon.sock "run/shot-edge-$1.png"; }
ctl() { sh "llmos desk-ctl \"$1\" | head -c 300; echo" "${2:-120}"; }
say() { sh "llmos say \"$1\" | python3 -c 'import json,sys; s=json.load(sys.stdin); print(\"reply:\", s[\"reply\"][:200].replace(chr(10),\" \")); print(\"windows:\", [w[\"title\"] for w in s[\"windows\"]], \"dialogs:\", len(s[\"dialogs\"]))'" "${2:-400}"; }
state() { sh "llmos desk-state | python3 -c 'import json,sys; s=json.load(sys.stdin); print(\"screen\", s[\"screen\"], \"busy\", s[\"busy\"], \"queued\", s[\"queued\"], \"dialogs\", [d[\"title\"] for d in s[\"dialogs\"]], [w[\"title\"] for w in s[\"windows\"]])'" 30; }
# a request that will raise a confirmation: start it, wait for the dialog, answer, wait for the turn
ask_dialog() {   # $1 request, $2 answer, $3 shot name
  sh "(llmos say \"$1\" > /tmp/dlg.json 2>&1 &); for i in \$(seq 1 45); do llmos desk-state | grep -q '\"dialogs\": \[{' && break; sleep 2; done; llmos desk-state | python3 -c 'import json,sys; s=json.load(sys.stdin); print(\"dialog:\", [(d[\"title\"], d[\"text\"][:80]) for d in s[\"dialogs\"]])'" 120
  shot "$3" 1
  ctl "dialog $2" >/dev/null
  sh "for i in \$(seq 1 120); do [ -s /tmp/dlg.json ] && break; sleep 2; done; python3 -c 'import json; s=json.load(open(\"/tmp/dlg.json\")); print(\"reply:\", s[\"reply\"][:200].replace(chr(10),\" \"))'" 300
}
onboard() { for step in "language en" "name Jordan" "timezone America/Phoenix" "autonomy hands-off" "internet yes" "tor no" "passphrase" "done"; do ctl "wizard $step" 200 >/dev/null; done; sleep 2; state; }

printf '\n======== desk edge cases: %s (%s MB) ========\n' "$IMG" "$RAM"
LLMOS_TESTSHELL=1 tools/boot-target.sh "$IMG" "$RAM" >/dev/null
$V wait $L 'LLM OS test shell' 300 >/dev/null && echo "  -> test shell up"
sh 'for i in $(seq 1 60); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done; U=$(cat /run/llmos/model_url 2>/dev/null || echo http://127.0.0.1:8080); for i in $(seq 1 150); do curl -s $U/health | grep -q ok && break; sleep 2; done; echo "model ready at $U"' 400
onboard
echo "--- 1. hands-on: a change asks first; declining is honoured; allowing does it"
say "switch to hands-on mode"
ask_dialog "create a file called note.txt in my home folder that says testing" no dialog
sh 'ls /root/note.txt 2>&1 | head -1' 30
ask_dialog "create a file called note.txt in my home folder that says testing" yes dialog-yes
sh 'cat /root/note.txt 2>&1 | head -1' 30
echo "--- 2. loosening the policy asks; internet 'ask' asks per request; 'no internet' is refused by the firewall"
ask_dialog "switch back to hands-off mode" yes loosen
say "ask me each time before using the internet"
ask_dialog "search the web for the tallest building in the world" no netdialog
ask_dialog "turn the internet off" yes
say "what's the latest news about the Artemis program?" 300
ask_dialog "allow internet use" yes
echo "--- 3. odd input: unknown colour, whitespace, a very long request"
say "make everything blurple"
sh 'llmos say "   " | head -c 120; echo "(empty request ignored)"' 30
say "$(printf 'please tell me in one short sentence what this computer is for%.0s ' $(seq 1 8))"
echo "--- 4. cancel a long request"
sh '(llmos say "write a 400 word essay about the history of the bicycle" > /tmp/cancel.json 2>&1 &); sleep 8; llmos desk-ctl cancel >/dev/null; for i in $(seq 1 40); do [ -s /tmp/cancel.json ] && break; sleep 1; done; python3 -c "import json; s=json.load(open(\"/tmp/cancel.json\")); print(\"reply:\", s[\"reply\"][:120])"' 90
shot cancel 1
echo "--- 5. model outage and recovery"
sh 'if [ -f /run/llmos/model_url ]; then echo "(host-GPU mode: firewall off the host link instead)"; nft insert rule inet llmos output ip daddr 10.0.2.2 tcp dport 8080 drop && nft list chain inet llmos output | grep -c "dport 8080 drop"; else rc-service llmos-model stop >/dev/null 2>&1 </dev/null; fi; sleep 2; echo cut' 60
say "what is 12 times 34?" 200
shot modeldown 1
sh 'if [ -f /run/llmos/model_url ]; then nft -a list chain inet llmos output 2>/dev/null | grep -E "dport 8080 drop" | sed -n "s/.*handle //p" | while read h; do nft delete rule inet llmos output handle $h; done; else rc-service llmos-model start >/dev/null 2>&1 </dev/null; fi; U=$(cat /run/llmos/model_url 2>/dev/null || echo http://127.0.0.1:8080); for i in $(seq 1 150); do curl -s $U/health | grep -q ok && break; sleep 2; done; echo back' 400
say "what is 12 times 34?" 200
echo "--- 6. many windows, then clear"
for i in 1 2 3 4 5 6 7 8; do ctl "js llmos.receive({t:'window',id:'t$i',spec:{title:'Window $i',kind:'panel',size:'s',blocks:[{type:'text',text:'test $i'}]}})" 20 >/dev/null; done
shot manywindows 1; state
say "clear"; state
echo "--- 7. the whole interface in Chinese, then back"
say "put everything in Chinese"; shot chinese 3
say "settings" 60; shot chinese-settings 2
say "switch everything back to English"; shot english 2
echo "--- 8. email without an account; focus mode; voice without a microphone"
say "reply to Alice that Friday works"
say "turn on focus mode"; sh 'grep -c "" /etc/hosts; grep -m2 -E "facebook|tiktok" /etc/hosts' 30
say "turn off focus mode"
ctl "js document.getElementById('mic').click()" >/dev/null; shot voice 3
echo "--- 9. persistence across a reboot (theme, wallpaper, memory, name)"
say "make everything orange"; say "remember that I like short answers"; say "use a photo of the Alps as my wallpaper" 300
shot before-reboot 2
# power off and boot the same installation again (QEMU's serial socket does
# not survive an in-guest reboot, so this is a fresh QEMU on the kept overlay)
sh 'sync; poweroff' 10 >/dev/null
for i in $(seq 1 40); do pgrep -f 'run/target-overlay.qcow2' >/dev/null || break; sleep 2; done
LLMOS_TESTSHELL=1 LLMOS_KEEP_OVERLAY=1 tools/boot-target.sh "$IMG" "$RAM" >/dev/null
$V wait $L 'LLM OS test shell' 300 >/dev/null && echo "  -> rebooted"
sh 'for i in $(seq 1 60); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done; U=$(cat /run/llmos/model_url 2>/dev/null || echo http://127.0.0.1:8080); for i in $(seq 1 150); do curl -s $U/health | grep -q ok && break; sleep 2; done; echo ready' 400
sleep 3; state; shot rebooted 2
say "what do you remember about me?" 300
say "settings" 60; shot rebooted-settings 2
echo "--- 10. shutdown by request (hands-off: no question asked)"
say "switch to hands-off mode"; ctl "dialog yes" >/dev/null
sh '(llmos say "shut down the computer" > /dev/null 2>&1 &); sleep 4; llmos desk-state 2>/dev/null | head -c 200; echo; echo asked' 30
shot bye 2
for i in $(seq 1 30); do pgrep -f "run/target-overlay" >/dev/null || break; sleep 2; done
pgrep -f "run/target-overlay" >/dev/null && echo "  -> VM still running (bug)" || echo "  -> powered off"
echo "======== desk edge cases done $(date +%H:%M:%S) ========"
