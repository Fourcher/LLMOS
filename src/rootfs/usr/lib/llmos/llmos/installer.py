"""Install LLM OS onto this computer's own disk, from the running system
(booted from a USB stick or a disk image):

  alongside  -- into free space next to an existing operating system
                (macOS on an Intel Mac, Windows, another Linux); the other
                system's partitions are never touched, its EFI system
                partition is shared
  whole      -- erase one whole disk and use all of it

Everything the owner has already set up (name, settings, memory, the
encrypted vault) is carried over: the installed system continues exactly
where the live one was. Partitioning uses sfdisk, copying uses rsync, the
bootloader is GRUB installed for UEFI (and BIOS on x86 when the machine was
booted that way). On Apple firmware the removable path (EFI/BOOT/BOOTX64.EFI)
is what the Option-key Startup Manager shows as "EFI Boot", so it is always
written there when that path is free.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import time

from . import config, release

ESP_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
LINUX_GUID = "0fc63daf-8483-4772-8e79-3d69d8477de4"
BIOSBOOT_GUID = "21686148-6449-6e6f-744e-656564454649"
KNOWN = {"7c3457ef-0000-11aa-aa11-00306543ecac": "macOS (APFS)", "48465300-0000-11aa-aa11-00306543ecac": "macOS (HFS+)",
         "426f6f74-0000-11aa-aa11-00306543ecac": "macOS boot", "52414944-0000-11aa-aa11-00306543ecac": "macOS RAID",
         "69646961-6700-11aa-aa11-00306543ecac": "macOS boot", "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7": "Windows",
         "e3c9e316-0b5c-4db8-817d-f92df00215ae": "Windows (reserved)", "de94bba4-06d1-4d40-a16a-bfd50179d6ac": "Windows recovery",
         LINUX_GUID: "Linux", "0fc63daf-8483-4772-8e79-3d69d8477de4": "Linux", "4f68bce3-e8cd-4db1-96e7-fbcaf984b709": "Linux root",
         "0657fd6d-a4ab-43c4-84e5-0933c84b4f4f": "Linux swap", "e6d6d379-f507-44c2-a23c-238f2a3df928": "Linux LVM"}
MIN_ROOT_GB = 12
TARGET = "/mnt/llmos-install"
_plans = {}


class InstallError(Exception):
    pass


def _sh(cmd, check=True, input=None, timeout=3600):
    p = subprocess.run(cmd, capture_output=True, text=True, input=input, timeout=timeout)
    if check and p.returncode != 0:
        raise InstallError(f"{cmd[0]} failed: {(p.stderr or p.stdout).strip()[:400]}")
    return p.stdout


def uefi():
    return os.path.isdir("/sys/firmware/efi")


def apple_firmware():
    try:
        with open("/sys/class/dmi/id/sys_vendor") as f:
            return "apple" in f.read().lower()
    except OSError:
        return False


def _read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def root_disk():
    """The whole disk the running system lives on (never a target)."""
    dev = ""
    for ln in _read("/proc/mounts").splitlines():
        parts = ln.split()
        if len(parts) > 1 and parts[1] == "/":
            dev = parts[0]
    if dev == "overlay":                      # running from the live medium: the medium is the one to protect
        for ln in _read("/proc/mounts").splitlines():
            parts = ln.split()
            if len(parts) > 1 and parts[1] == "/run/live":
                dev = parts[0]
    if not dev.startswith("/dev/"):
        return ""
    name = os.path.basename(os.path.realpath(dev))
    for disk in os.listdir("/sys/block"):
        if name == disk or os.path.isdir(f"/sys/block/{disk}/{name}"):
            return "/dev/" + disk
    return ""


def disks():
    out = []
    live = root_disk()
    for name in sorted(os.listdir("/sys/block")):
        if re.match(r"^(loop|ram|sr|zram|dm-|nbd|fd|md)", name):
            continue
        size = int(_read(f"/sys/block/{name}/size", "0")) * 512
        if size < 4e9:
            continue
        model = _read(f"/sys/block/{name}/device/model") or _read(f"/sys/block/{name}/device/name") or name
        out.append({"dev": "/dev/" + name, "size": size, "model": " ".join(model.split()),
                    "removable": _read(f"/sys/block/{name}/removable") == "1", "live": "/dev/" + name == live})
    return out


def layout(dev):
    try:
        data = json.loads(_sh(["sfdisk", "-J", dev], check=False) or "{}")
    except ValueError:
        data = {}
    tbl = data.get("partitiontable", {})
    parts = []
    for p in tbl.get("partitions", []):
        parts.append({"node": p["node"], "start": int(p["start"]), "size": int(p["size"]),
                      "type": str(p.get("type", "")).lower(), "name": p.get("name", "")})
    return {"label": tbl.get("label", ""), "sector": int(tbl.get("sectorsize", 512)), "parts": parts,
            "last": int(tbl.get("lastlba", 0)), "first": int(tbl.get("firstlba", 2048))}


def free_areas(lay, dev):
    """Gaps (start, size in sectors) between partitions, 1 MiB aligned."""
    total = int(_read(f"/sys/block/{os.path.basename(dev)}/size", "0"))
    last = lay["last"] or (total - 34)
    cur = max(lay["first"], 2048)
    gaps = []
    for p in sorted(lay["parts"], key=lambda x: x["start"]):
        if p["start"] > cur:
            gaps.append((cur, p["start"] - cur))
        cur = max(cur, p["start"] + p["size"])
    if last > cur:
        gaps.append((cur, last - cur))
    out = []
    for start, size in gaps:
        a = (start + 2047) // 2048 * 2048
        size -= a - start
        size = size // 2048 * 2048
        if size >= 2048 * 64:
            out.append((a, size))
    return out


def _gb(sectors, sector=512):
    return sectors * sector / 1e9


def plan(mode="alongside", disk=None, size_gb=None):
    """Decide what would be done; nothing is written. Returns a plan dict
    with human-readable lines and a one-time token that authorises run()."""
    mode = "whole" if str(mode).lower().startswith(("whole", "erase", "all", "entire")) else "alongside"
    cands = [d for d in disks() if not d["live"]]
    if disk:
        cands = [d for d in cands if d["dev"] == disk or d["dev"].endswith("/" + str(disk).replace("/dev/", ""))]
        if not cands:
            raise InstallError(f"no such disk: {disk}")
    if not cands:
        raise InstallError("no other disk found to install onto (the running system's own disk is never a target)")
    cands.sort(key=lambda d: (d["removable"], -d["size"]))
    d = cands[0]
    dev = d["dev"]
    lay = layout(dev)
    others = [f"{p['node']}: {KNOWN.get(p['type'], p['type'][:8])} ({_gb(p['size'], lay['sector']):.0f} GB)"
              for p in lay["parts"] if p["type"] in KNOWN]
    p = {"mode": mode, "disk": dev, "model": d["model"], "disk_gb": d["size"] / 1e9, "uefi": uefi(),
         "apple": apple_firmware(), "arch": os.uname().machine, "others": others, "lines": []}
    if mode == "whole":
        p["lines"] = [f"Erase {dev} ({d['model']}, {d['size'] / 1e9:.0f} GB) completely.",
                      "Create: EFI system partition 256 MB" + (", BIOS boot 2 MB" if p["arch"] == "x86_64" else "") + ", LLM OS on the rest.",
                      "Copy this system there, install the bootloader (UEFI" + (" + BIOS" if p["arch"] == "x86_64" else "") + ")."]
        if others:
            p["lines"].append("WARNING: this destroys " + "; ".join(others))
    else:
        if lay["label"] != "gpt":
            raise InstallError(f"{dev} has no GPT partition table; installing next to another system needs GPT "
                               f"(say 'erase the whole disk and install' to use the entire disk)")
        gaps = free_areas(lay, dev)
        if not gaps:
            raise InstallError(f"no free space on {dev}; shrink the other system's partition first "
                               f"(macOS: Disk Utility → Partition; Windows: Disk Management → Shrink Volume)")
        start, size = max(gaps, key=lambda g: g[1])
        esp = next((q for q in lay["parts"] if q["type"] == ESP_GUID), None)
        need_esp = esp is None
        want = int(float(size_gb) * 1e9 / lay["sector"]) if size_gb else size
        want = min(want, size)
        if _gb(want, lay["sector"]) < MIN_ROOT_GB:
            raise InstallError(f"the free space on {dev} is {_gb(size, lay['sector']):.1f} GB; at least {MIN_ROOT_GB} GB is needed")
        p.update({"start": start, "size": want, "esp": esp["node"] if esp else "", "need_esp": need_esp,
                  "need_biosboot": p["arch"] == "x86_64" and not p["uefi"] and not any(q["type"] == BIOSBOOT_GUID for q in lay["parts"])})
        p["lines"] = [f"Use {_gb(want, lay['sector']):.0f} GB of free space on {dev} ({d['model']}, {d['size'] / 1e9:.0f} GB).",
                      "Keep everything already there: " + ("; ".join(others) if others else "no other system found") + ".",
                      ("Share the existing EFI system partition " + esp["node"]) if esp else "Create an EFI system partition (256 MB).",
                      "Copy this system there and install the bootloader" + (" (UEFI, removable path for Apple's startup manager)" if p["apple"] else " (UEFI)" if p["uefi"] else " (BIOS)") + "."]
    p["token"] = secrets.token_hex(4)
    _plans[p["token"]] = p
    return p


def _wait_node(node):
    for _ in range(50):
        if os.path.exists(node):
            return
        subprocess.run(["mdev", "-s"], capture_output=True)
        time.sleep(0.2)
    raise InstallError(f"partition {node} did not appear")


def _partnode(dev, n):
    return f"{dev}p{n}" if dev[-1].isdigit() else f"{dev}{n}"


def _mounts_down(target):
    for sub in ("boot/efi", "sys/firmware/efi/efivars", "sys", "proc", "dev", ""):
        subprocess.run(["umount", "-l", os.path.join(target, sub)], capture_output=True)


def run(token, status=lambda s: None):
    """Carry out a plan (by its token). Returns a summary for the owner."""
    p = _plans.pop(token, None)
    if not p:
        raise InstallError("that installation plan is no longer valid; ask again")
    dev, sector = p["disk"], 512
    lay = layout(dev)
    sector = lay["sector"]
    os.makedirs(TARGET, exist_ok=True)
    if p["mode"] == "whole":
        status(f"partitioning {dev}")
        script = "label: gpt\n"
        script += f"size=256MiB, type={ESP_GUID}, name=EFI\n"
        if p["arch"] == "x86_64":
            script += f"size=2MiB, type={BIOSBOOT_GUID}, name=bios\n"
        script += f"type={LINUX_GUID}, name=llmos\n"
        _sh(["wipefs", "-a", dev], check=False)
        _sh(["sfdisk", "-q", "--wipe", "always", dev], input=script)
        esp_node = _partnode(dev, 1)
        root_node = _partnode(dev, 3 if p["arch"] == "x86_64" else 2)
        esp_new = True
    else:
        status(f"adding a partition to {dev}")
        start, size = p["start"], p["size"]
        script = ""
        n = len(lay["parts"])
        esp_node = p["esp"]
        esp_new = False
        if p["need_esp"]:
            script += f"start={start}, size={256 * 1024 * 1024 // sector}, type={ESP_GUID}, name=EFI\n"
            start += 256 * 1024 * 1024 // sector
            size -= 256 * 1024 * 1024 // sector
            n += 1
            esp_node = _partnode(dev, n)
            esp_new = True
        if p.get("need_biosboot"):
            script += f"start={start}, size={2 * 1024 * 1024 // sector}, type={BIOSBOOT_GUID}, name=bios\n"
            start += 2 * 1024 * 1024 // sector
            size -= 2 * 1024 * 1024 // sector
            n += 1
        script += f"start={start}, size={size}, type={LINUX_GUID}, name=llmos\n"
        _sh(["sfdisk", "-q", "--append", dev], input=script)
        root_node = _partnode(dev, n + 1)
    subprocess.run(["blockdev", "--rereadpt", dev], capture_output=True)
    subprocess.run(["partx", "-u", dev], capture_output=True)
    _wait_node(root_node)

    status(f"formatting {root_node}")
    _sh(["mkfs.ext4", "-q", "-F", "-L", "llmos", root_node])
    if esp_new:
        _wait_node(esp_node)
        _sh(["mkfs.vfat", "-F", "32", "-n", "EFI", esp_node])
    _sh(["mount", root_node, TARGET])
    try:
        status("copying the system (a few minutes)")
        excl = ["/proc", "/sys", "/dev", "/run", "/tmp", "/mnt", "/media", "/lost+found", "/var/cache/apk", TARGET, "/boot/efi", "/run/live"]
        cmd = ["rsync", "-aHAX", "--one-file-system", "--numeric-ids", "/", TARGET + "/"] + [f"--exclude={e}" for e in excl]
        if not shutil.which("rsync"):
            raise InstallError("rsync is missing")
        _sh(cmd, timeout=7200)
        # from the live medium the model directory is a bind mount that --one-file-system skipped
        models = "/var/lib/llmos/models"
        tgt_models = os.path.join(TARGET, models.lstrip("/"))
        if os.path.isdir(models) and not (os.path.isdir(tgt_models) and os.listdir(tgt_models)):
            status("copying the model")
            os.makedirs(tgt_models, exist_ok=True)
            _sh(["rsync", "-a", models + "/", tgt_models + "/"], timeout=3600)
        for d in ("proc", "sys", "dev", "run", "tmp", "mnt", "media", "boot/efi", "var/cache/apk"):
            os.makedirs(os.path.join(TARGET, d), exist_ok=True)
        os.chmod(os.path.join(TARGET, "tmp"), 0o1777)

        status("writing fstab")
        root_uuid = _sh(["blkid", "-s", "UUID", "-o", "value", root_node]).strip()
        esp_uuid = _sh(["blkid", "-s", "UUID", "-o", "value", esp_node]).strip() if esp_node else ""
        fstab = f"UUID={root_uuid}\t/\text4\trw,relatime,discard\t0 1\n"
        if esp_uuid:
            fstab += f"UUID={esp_uuid}\t/boot/efi\tvfat\trw,umask=0077\t0 2\n"
        fstab += "tmpfs\t/tmp\ttmpfs\tnosuid,nodev,mode=1777\t0 0\n"
        with open(os.path.join(TARGET, "etc/fstab"), "w") as f:
            f.write(fstab)
        # the copy carries this system's build stamp; the installed system runs from a disk, not the live medium
        rel = release()
        rel["MEDIUM"] = "disk"
        with open(os.path.join(TARGET, "etc/llmos-release"), "w") as f:
            f.write("".join(f"{k}={v}\n" for k, v in rel.items()))

        status("installing the bootloader")
        for src, dst, typ in (("/dev", "dev", None), ("proc", "proc", "proc"), ("sys", "sys", "sysfs")):
            if typ:
                _sh(["mount", "-t", typ, typ, os.path.join(TARGET, dst)])
            else:
                _sh(["mount", "--bind", src, os.path.join(TARGET, dst)])
        if esp_node:
            _sh(["mount", esp_node, os.path.join(TARGET, "boot/efi")])
        gd = os.path.join(TARGET, "etc/default/grub")
        cfg = _read(gd)
        cfg = re.sub(r"^GRUB_TIMEOUT=.*$", "", cfg, flags=re.M).strip() + "\n"
        cfg += f"GRUB_TIMEOUT={3 if p['others'] else 0}\nGRUB_DISABLE_OS_PROBER={'false' if p['others'] else 'true'}\n"
        with open(gd, "w") as f:
            f.write(cfg)
        efi_target = "arm64-efi" if p["arch"] == "aarch64" else "x86_64-efi"
        chroot = ["chroot", TARGET]
        notes = []
        if p["uefi"] or p["arch"] == "aarch64":
            efivars = os.path.join(TARGET, "sys/firmware/efi/efivars")
            if os.path.isdir("/sys/firmware/efi/efivars"):
                subprocess.run(["mount", "-t", "efivarfs", "efivarfs", efivars], capture_output=True)
            _sh(chroot + ["grub-install", f"--target={efi_target}", "--efi-directory=/boot/efi", "--bootloader-id=llmos",
                          "--no-nvram", "--boot-directory=/boot"])
            boot_dir = os.path.join(TARGET, "boot/efi/EFI/BOOT")
            fallback = os.path.join(boot_dir, "BOOTAA64.EFI" if p["arch"] == "aarch64" else "BOOTX64.EFI")
            if p["mode"] == "whole" or not os.path.exists(fallback) or p["apple"]:
                _sh(chroot + ["grub-install", f"--target={efi_target}", "--efi-directory=/boot/efi", "--removable",
                              "--no-nvram", "--boot-directory=/boot"])
                notes.append("EFI/BOOT (the removable path) points to LLM OS")
            if shutil.which("efibootmgr") and not p["apple"]:
                m = re.search(r"(\d+)$", esp_node)
                loader = "\\EFI\\llmos\\grubaa64.efi" if p["arch"] == "aarch64" else "\\EFI\\llmos\\grubx64.efi"
                r = subprocess.run(["efibootmgr", "-c", "-d", dev, "-p", m.group(1) if m else "1", "-L", "LLM OS", "-l", loader],
                                   capture_output=True, text=True)
                notes.append("firmware boot entry 'LLM OS' added" if r.returncode == 0 else "no firmware boot entry could be added (use the boot menu / EFI Boot)")
        if p["arch"] == "x86_64" and (not p["uefi"] or p["mode"] == "whole"):
            r = subprocess.run(chroot + ["grub-install", "--target=i386-pc", "--boot-directory=/boot", dev], capture_output=True, text=True)
            notes.append("BIOS bootloader written to the disk's MBR" if r.returncode == 0 else f"BIOS bootloader not written: {r.stderr.strip()[:120]}")
        _sh(chroot + ["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
        subprocess.run(chroot + ["sh", "-c", "command -v mkinitfs >/dev/null && mkinitfs $(ls /lib/modules | head -1)"], capture_output=True)
        status("finishing")
        _sh(["sync"])
    finally:
        _mounts_down(TARGET)
    where = f"{root_node} ({_gb(p.get('size', 0), sector):.0f} GB)" if p["mode"] == "alongside" else f"{dev} (whole disk)"
    how = ("Hold the Option key while the Mac starts and choose “EFI Boot”." if p["apple"] else
           "Restart; if the other system starts instead, pick LLM OS in the firmware's boot menu (F12/F8/Esc at power-on)." if p["others"] else "Restart.")
    return {"where": where, "notes": notes, "how": how, "plan": p}
