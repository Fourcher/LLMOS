#!/bin/bash
# Push the current src/rootfs into the running arm64 test VM (over the host
# HTTP server) and restart what changed. usage: tools/push.sh [desk|console|all]
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
python3 -m compileall -q src/rootfs/usr/lib/llmos/llmos || exit 1
find src/rootfs -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
chmod 0755 src/rootfs/usr/bin/llmos src/rootfs/usr/bin/llmos-model-run src/rootfs/usr/libexec/llmos-login src/rootfs/usr/libexec/llmos-desk src/rootfs/etc/init.d/llmos-*
(cd src/rootfs && tar --format=ustar --uid 0 --gid 0 --uname root --gname root -cf ../../build/work/payload.tar .)   # system files belong to root, not to the Mac user who built them
curl -s -o /dev/null http://127.0.0.1:8765/src/install.sh || {
    nohup python3 -m http.server 8765 --bind 127.0.0.1 --directory "$PWD" > run/httpd.log 2>&1 &
    echo $! > run/httpd.pid; sleep 1; }
what=${1:-all}
tools/tsh 'wget -qO /tmp/p.tar http://10.0.2.2:8765/build/work/payload.tar && tar -xf /tmp/p.tar -C / && echo pushed' 60
case "$what" in
  desk|all)
    # ("[l]lmos" so the pattern never matches this very command line)
    tools/tsh 'pkill -f "[l]lmos desk-app"; pkill -x labwc; pkill -x seatd; sleep 1; rm -f /run/seatd.sock /run/llmos/desk.sock; (setsid /usr/libexec/llmos-desk < /dev/null > /run/llmos/desk.log 2>&1 &); sleep 10; pgrep -a "labwc|desk-app" | cut -c1-60; grep -vE "^$|Gtk-WARNING|Gdk-WARNING|a11y" /run/llmos/desk.log | tail -4' 60 ;;
esac
