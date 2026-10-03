#!/bin/bash
# In-VM acceptance tests for the rebuilt LLM OS. Drives the serial console of
# the target VM (run/tser.sock, log run/boot-serial.log). Every request runs
# INSIDE the VM; nothing here touches the host.
#
#   tools/acceptance.sh onboard    first-run wizard, with a passphrase (vault)
#   tools/acceptance.sh basics     disk / theme / settings / languages / memory / math
#   tools/acceptance.sh agentic    scheduling, web research, real photo, media
#   tools/acceptance.sh admin      ordinary root admin work, done without fuss
#   tools/acceptance.sh autonomy   hands-on mode asks before changes
#   tools/acceptance.sh voice      whisper STT round-trip + honest no-mic answer
#   tools/acceptance.sh lock       lock / unlock the vault
#   tools/acceptance.sh sched      background task lands in the inbox
#   tools/acceptance.sh reboot     shutdown, boot again, everything persisted
#   tools/acceptance.sh distsmoke  fresh boot of the SHIPPED image, host-GPU mode
#   tools/acceptance.sh video      YouTube video on the screen (framebuffer dump)
#   tools/acceptance.sh gui        terminal window, then a web browser on the screen
#   tools/acceptance.sh email      test mail server in the VM: setup, inbox, inbox zero, reply by name
cd "/Volumes/Files/Claude Work Area/LLMOS"
V="python3 tools/vmctl.py"
S=run/tser.sock; L=run/boot-serial.log
say() { $V send $S "$1"; }
ask() { tools/trun "$1" "${2:-120}"; echo "----"; }
sep() { printf '\n======== %s ========\n' "$1"; }
# the screen is the preferred console: the serial line offers itself with
# "Press Enter"; take it (the desk on tty1 keeps running alongside)
take() { $V wait $L 'Press Enter to use it here|language should I use|Passphrase|› \$' "${1:-240}" >/dev/null
         if tail -c 400 $L | grep -q 'Press Enter to use it here'; then say ""; fi
         # with the desk on screen the console waits for set-up there; Enter takes over
         $V wait $L 'press Enter to do it here|language should I use|Passphrase|› \$' 60 >/dev/null
         if tail -c 400 $L | grep -q 'press Enter to do it here'; then sleep 1; say ""; fi; }

case "$1" in
onboard)
  sep "onboarding: English, name, default TZ, hands-off, internet yes, no tor, passphrase"
  take
  M=$($V mark $L)
  $V wait $L 'language should I use' 120 --from $M >/dev/null
  say "";                      sleep 1   # language: English (default)
  say "Jordan";                sleep 1
  say "";                      sleep 1   # time zone: keep the launcher's default
  say "1";                     sleep 1   # hands-off
  say "y";                     sleep 1   # internet
  say "n";                     sleep 1   # tor
  say "correct horse battery"; sleep 1
  say "correct horse battery"
  $V wait $L 'All set' 240 --from $M | grep -vE '^\s*$|on-device model' | tail -24
  ;;
basics)
  sep "basics"
  ask "how much disk space do I have?"
  ask "make everything purple"
  ask "settings" 20
  ask "put the settings in Chinese but keep everything else in English"
  ask "settings" 20
  ask "remember that I like short answers"
  ask "memory" 20
  ask "what is 391 times 47?"
  ask "what time is it, and what time zone am I in?"
  ;;
agentic)
  sep "agentic: scheduling, research, real photo, media"
  ask "in 1 minute, tell me one real fact about the Moon"
  ask "tasks" 20
  ask "search the web for the latest news about NASA's Artemis program and give me a 2-sentence summary with the source" 240
  ask "show me a photo of the Eiffel Tower" 120
  ask "play some lofi hip hop" 240
  ask "stop the music" 60
  echo "waiting for the scheduled task to land in the inbox..."; sleep 70
  ask "audit" 30
  ;;
admin)
  sep "ordinary admin on the owner's own machine, done without fuss"
  ask "delete everything in /tmp"
  ask "install htop" 300
  ask "turn off the syslog service"
  ask "turn syslog back on"
  ask "make a folder called projects in my home and put a hello.txt in it that says hello world"
  ask "what's in ~/projects/hello.txt?"
  ;;
autonomy)
  sep "hands-on: asks before a change, then does it"
  ask "switch to hands-on mode"
  M=$($V mark $L)
  say "create a file called note.txt in my home folder that says testing"
  $V wait $L '\[y/N\]' 120 --from $M >/dev/null && echo "  -> confirmation prompt shown" || echo "  -> NO confirmation prompt (bug)"
  say "y"
  $V wait $L '› $' 120 --from $M | grep -vE '^\s*$' | tail -8
  echo "----"
  M=$($V mark $L)
  say "switch back to hands-off"       # loosening a policy always confirms
  $V wait $L '\[y/N\]' 120 --from $M >/dev/null && echo "  -> loosening asked for confirmation (correct)" || echo "  -> no confirmation on loosening (bug)"
  say "y"
  $V wait $L '› $' 120 --from $M | grep -vE '^\s*$' | tail -4
  ;;
voice)
  sep "voice: on-device speech-to-text round trip (no real mic in this headless test)"
  ask '!espeak-ng -v en -s 150 -w /tmp/v.wav "what time is it in tokyo right now" && whisper-cli -m /usr/share/llmos/voice/ggml-base.bin -f /tmp/v.wav -nt -np 2>/dev/null | tail -2' 120
  ask "voice" 60
  ;;
lock)
  sep "lock and unlock the encrypted vault"
  M=$($V mark $L)
  say "lock"
  $V wait $L 'Passphrase' 60 --from $M | grep -vE '^\s*$' | tail -4
  say "wrong one"; sleep 6
  say "correct horse battery"
  $V wait $L '› $' 90 --from $M | grep -vE '^\s*$' | tail -8
  ;;
sched)
  sep "scheduling: deterministic shortcut, background run, inbox at the prompt"
  ask "in 1 minute, tell me one real fact about the Moon" 60
  ask "tasks" 20
  echo "waiting ~80 s for the scheduler..."; sleep 80
  M=$($V mark $L); say ""
  $V wait $L '› $' 60 --from $M | grep -vE '^\s*$' | tail -12
  ;;
reboot)
  sep "reboot persistence: vault unlock, theme, memory, settings language, time zone"
  PID=$(cat run/target.pid)              # QEMU deletes its pidfile on exit
  say "shutdown"
  for i in $(seq 1 40); do ps -p "$PID" >/dev/null 2>&1 || break; sleep 1; done
  ps -p "$PID" >/dev/null 2>&1 && echo "  -> VM did not power off (bug)" || echo "  -> powered off cleanly"
  tools/boot-target.sh >/dev/null
  take
  $V wait $L 'Passphrase' 180 | grep -vE '^\s*$' | tail -3
  say "correct horse battery"
  M=$($V mark $L)
  $V wait $L '› $' 240 --from $M | grep -vE '^\s*$|on-device' | tail -6
  ask "what do you remember about me?" 120
  ask "settings" 20
  ask "what time zone am I in?" 90
  ;;
distsmoke)
  # fresh boot of the SHIPPED image in host-GPU mode (a Metal llama-server
  # must be listening on the Mac's 127.0.0.1:8080), quick onboarding, timed asks
  sep "dist image: first boot in host-GPU mode, 3 GB VM"
  LLMOS_HOSTGPU_URL=${LLMOS_HOSTGPU_URL:-http://10.0.2.2:8080} tools/boot-target.sh dist/llmos-arm64.qcow2 3072 >/dev/null
  take
  $V wait $L 'language should I use' 240 | grep -E 'grub|error|Bringing up|host|llmos-|Welcome' | head -12
  M=$($V mark $L)
  say ""; sleep 1; say "Jordan"; sleep 1; say ""; sleep 1; say "1"; sleep 1; say "y"; sleep 1; say "n"; sleep 1; say ""
  $V wait $L 'All set' 120 --from $M >/dev/null && echo "  -> onboarded"
  sleep 15
  for q in "how much disk space do I have?" "make everything green with square corners" "what is 12 times 34?" "what's the latest news about the Artemis program? one sentence with the source"; do
    t0=$(date +%s); tools/trun "$q" 240 | tail -4; echo "   (${q:0:30}… took $(( $(date +%s) - t0 )) s)"; echo "----"
  done
  ask "settings" 20
  ;;
video)
  sep "video on the screen: play, screendump the framebuffer, stop"
  python3 tools/screendump.py run/tmon.sock run/shot-idle.png
  ask "play some lofi hip hop" 240
  sleep 25
  python3 tools/screendump.py run/tmon.sock run/shot-video.png
  ask "!cat /proc/asound/card0/pcm0p/sub0/status 2>/dev/null | head -3; pgrep -a mpv | cut -c1-80" 30
  ask "stop the music" 60
  ;;
gui)
  sep "graphical programs on the screen: a terminal window, then a web browser"
  ask "open a terminal window on the screen" 120
  sleep 8
  python3 tools/screendump.py run/tmon.sock run/shot-terminal.png
  ask "!pkill -f cage; sleep 1; echo closed" 30
  ask "install a web browser and open example.com in it on the screen" 600
  sleep 40
  python3 tools/screendump.py run/tmon.sock run/shot-browser.png
  ask "!pgrep -a firefox | head -2 | cut -c1-80; tail -3 /run/llmos/gui.log" 30
  ask "!pkill -f cage; echo closed" 30
  ;;
email)
  sep "email: test mail server inside the VM, account setup, inbox, inbox zero, reply by name"
  tools/tsh 'wget -qO /tmp/mf.sh http://10.0.2.2:8765/tools/mailfixture.sh && sh /tmp/mf.sh > /tmp/mf.log 2>&1; echo "fixture rc=$?"; tail -3 /tmp/mf.log' 420
  ask "set up my email: address jordan@localhost, password test, imap_host 127.0.0.1, imap_port 143, imap_ssl false, smtp_host 127.0.0.1, smtp_port 25, smtp_security none" 120
  ask "what's in my inbox?" 180
  ask "get me to inbox zero" 400
  ask "reply to Alice that Friday at 7 works and I'll bring dessert" 180
  tools/tsh 'sleep 2; for f in /home/alice/Maildir/new/*; do grep -E "^(Subject|In-Reply-To|To|From):|dessert" "$f"; done; echo "jordan INBOX now: $(find /home/jordan/Maildir/new /home/jordan/Maildir/cur -type f | wc -l) messages, Archive: $(find /home/jordan/Maildir/.Archive -type f 2>/dev/null | wc -l)"' 60
  ;;
*)
  sed -n '2,19p' "$0" ;;
esac
