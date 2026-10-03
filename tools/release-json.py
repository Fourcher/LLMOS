#!/usr/bin/env python3
"""Write dist/RELEASE.json: the version, build date and every image/ISO in dist with size and checksum.
Run after the builds (the build and ISO scripts call it)."""
import json, os, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
ver = open(os.path.join(ROOT, "VERSION")).read().strip()
sums = {}
try:
    for line in open(os.path.join(DIST, "SHA256SUMS")):
        p = line.split()
        if len(p) == 2:
            sums[p[1].lstrip("*")] = p[0]
except OSError:
    pass
images = []
for name in sorted(os.listdir(DIST)):
    if name.endswith((".iso", ".qcow2")):
        path = os.path.join(DIST, name)
        images.append({"file": name, "arch": "x86_64" if "x86" in name else "arm64", "kind": "iso" if name.endswith(".iso") else "vm",
                       "size": os.path.getsize(path), "sha256": sums.get(name, ""),
                       "built": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))})
rel = {"name": "LLM OS", "version": ver, "built": time.strftime("%Y-%m-%d"), "images": images}
with open(os.path.join(DIST, "RELEASE.json"), "w") as f:
    json.dump(rel, f, indent=2)
with open(os.path.join(DIST, "VERSION"), "w") as f:
    f.write(ver + "\n")
print(f"RELEASE.json: {ver}, {len(images)} image(s)")
