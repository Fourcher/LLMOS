"""What is plugged into this computer, read from /sys (no model, no extra programs)."""
import glob
import os


def _read(p):
    try:
        with open(p) as f:
            return f.read().strip()
    except OSError:
        return ""


def plugged_in(root="/"):
    """Plain names of attached things: USB devices (not hubs), cameras, removable drives, disc drives, sound cards."""
    j = lambda *a: os.path.join(root, *a)
    out = []
    for d in sorted(glob.glob(j("sys/bus/usb/devices/*"))):
        if ":" in os.path.basename(d):
            continue                                      # an interface, not a device
        prod = _read(os.path.join(d, "product"))
        if not prod or "hub" in prod.lower() or "host controller" in prod.lower():
            continue
        maker = _read(os.path.join(d, "manufacturer"))
        name = prod if (not maker or maker.lower() in prod.lower()) else f"{prod} ({maker})"
        if name not in out:
            out.append(name)
    if glob.glob(j("dev/video[0-9]*")) and not any("camera" in n.lower() or "webcam" in n.lower() for n in out):
        out.append("a camera")
    for b in sorted(glob.glob(j("sys/block/sd*"))):
        if _read(os.path.join(b, "removable")) == "1":
            model = _read(os.path.join(b, "device", "model")) or os.path.basename(b)
            out.append(f"a removable drive ({model})")
    if glob.glob(j("dev/sr[0-9]")):
        out.append("a disc drive")
    for line in _read(j("proc/asound/cards")).splitlines():
        if "]: " in line:
            out.append("sound: " + line.split("]: ", 1)[1].split(" - ")[0].strip())
    return out


def plugged_in_sentence(root="/"):
    items = plugged_in(root)
    return ("Plugged in: " + "; ".join(items) + ".") if items else "Nothing extra is plugged in."
