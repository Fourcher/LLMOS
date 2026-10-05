#!/bin/bash
# Give a test or build VM a hard lifetime: a detached guard kills the QEMU
# process named in the pidfile after N seconds (default 3 hours, or
# $LLMOS_VM_LIFETIME). A test that hangs, or a harness timeout that killed
# the driving script, can then never leave a VM running for days.
#   usage: tools/vm-lifetime.sh run/target.pid [seconds]
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
pidfile=$1; secs=${2:-${LLMOS_VM_LIFETIME:-10800}}
pid=$(cat "$pidfile" 2>/dev/null) || exit 0
( sleep "$secs"
  if [ "$(cat "$pidfile" 2>/dev/null)" = "$pid" ] && ps -p "$pid" -o command= 2>/dev/null | grep -q '^qemu-system'; then
      kill "$pid" 2>/dev/null; sleep 3; kill -9 "$pid" 2>/dev/null
      echo "$(date '+%F %T') vm-lifetime: killed VM $pid ($pidfile) after ${secs}s" >> run/vm-lifetime.log
  fi ) > /dev/null 2>&1 &
disown 2>/dev/null || true
