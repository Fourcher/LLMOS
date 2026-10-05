#!/bin/bash
# Stop every test VM and helper this project started, and drop the big
# scratch disks (the shipped images in dist/ are kept).
cd "/Volumes/Files/Claude Work Area/LLMOS"
for s in tmon ymon bmon xmon; do
  python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/$s.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null && echo "stopped VM on $s"
done
sleep 2
for p in run/host-model-8080.pid run/host-model-8081.pid run/httpd.pid run/llama.pid run/llama-exp.pid run/fake-mic.pid run/isotest.pid run/x86test.pid; do
  [ -f "$p" ] && kill "$(cat "$p")" 2>/dev/null && echo "stopped $(basename "$p" .pid)"; rm -f "$p"
done
pgrep -fl 'qemu-system|llama-server|mic-bridge' | cut -c1-80
rm -f build/work/*.qcow2 run/*.qcow2 run/*.raw run/*.fd
du -sh build/work run dist 2>/dev/null
