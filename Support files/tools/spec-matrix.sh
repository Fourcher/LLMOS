#!/bin/bash
# Minimum / recommended hardware: boot the shipped arm64 image with the model
# INSIDE the VM under several RAM and CPU configurations and measure boot time,
# whether the model loads, free memory afterwards, and the model's own
# prompt/generation speed (llama-server timings). Results -> run/spec-matrix.txt
#   usage: tools/spec-matrix.sh ["2048 3072 4096 6144 8192"] ["2 4 8"]
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
V="python3 tools/vmctl.py"; L=run/boot-serial.log
RAMS=${1:-"2048 3072 4096 6144 8192"}; CPUS_LIST=${2:-"2 4 8"}
OUT=run/spec-matrix.txt
sh() { tools/tsh "$1" "${2:-120}" | grep -vE '^\s*$|^\[vmctl|^# $|^~ # $'; }
printf 'RAM_MB  CPUS  boot_to_shell_s  model_ready_s  free_MB_after_model  prompt_tok_s  gen_tok_s  desk_RSS_MB  note\n' | tee "$OUT"
for ram in $RAMS; do
  for cpus in $CPUS_LIST; do
    t0=$(date +%s)
    LLMOS_TESTSHELL=1 LLMOS_CPUS=$cpus tools/boot-target.sh dist/llmos-arm64.qcow2 "$ram" >/dev/null
    if ! $V wait $L 'LLM OS test shell' 240 >/dev/null 2>&1; then
      printf '%-7s %-5s boot failed within 240 s\n' "$ram" "$cpus" | tee -a "$OUT"; continue
    fi
    tboot=$(( $(date +%s) - t0 ))
    # wait for the model (up to 10 min: a small machine is slow), then measure
    res=$(sh 't0=$(date +%s); for i in $(seq 1 300); do curl -s http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; sleep 2; done; tm=$(( $(date +%s) - t0 )); curl -s http://127.0.0.1:8080/health | grep -q ok && ok=1 || ok=0; free=$(free -m | awk "/Mem:/ {print \$7}"); if [ $ok = 1 ]; then curl -s http://127.0.0.1:8080/completion -d "{\"prompt\": \"Explain in three sentences why the sky is blue. Then list five countries and their capitals.\", \"n_predict\": 96, \"temperature\": 0}" | python3 -c "import json,sys; t=json.load(sys.stdin)[\"timings\"]; print(\"%.1f %.1f\" % (t[\"prompt_per_second\"], t[\"predicted_per_second\"]))"; else echo "- -"; fi; echo "MODEL $ok $tm $free"; echo "DESK $(ps -o rss,comm | awk "/desk-app|WebKitWebProcess|labwc/ {s+=\$1} END {print int(s/1024)}")"; dmesg | grep -ci "out of memory\|oom-kill"' 700)
    speed=$(echo "$res" | grep -E '^[0-9.]+ [0-9.-]+$' | tail -1)
    model=$(echo "$res" | grep '^MODEL' | tail -1)
    desk=$(echo "$res" | grep '^DESK' | tail -1 | awk '{print $2}')
    oom=$(echo "$res" | tail -1)
    ok=$(echo "$model" | awk '{print $2}'); tm=$(echo "$model" | awk '{print $3}'); free=$(echo "$model" | awk '{print $4}')
    note=""; [ "$ok" != 1 ] && note="model did not load"; [ "$oom" != "0" ] && [ -n "$oom" ] && note="$note OOM-kills:$oom"
    printf '%-7s %-5s %-16s %-14s %-20s %-13s %-10s %-12s %s\n' "$ram" "$cpus" "$tboot" "${tm:-?}" "${free:-?}" "$(echo $speed | cut -d' ' -f1)" "$(echo $speed | cut -d' ' -f2)" "${desk:-?}" "$note" | tee -a "$OUT"
    python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; sleep 3
  done
done
echo "written to $OUT"
