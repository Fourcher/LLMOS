"""Starting fresh ("reset this computer", "factory reset"): everything personal goes (files, apps made here,
conversations, memory, settings, Wi-Fi passwords, the vault and its passphrase); the system itself and the
downloaded AI model stay, so it starts at the first-time setup again without a big download. Then it restarts."""
import glob
import os
import shutil
import subprocess

from . import config

KEPT = "the system and the AI model (no big download again)"
LOST = ("all your files (Documents, Pictures, Music, Videos, Downloads, Desktop), the apps you made, every conversation and what I "
        "remember about you, your settings, saved Wi-Fi passwords, and the passphrase")


def erase():
    """Erase everything personal; the caller restarts the computer. Returns a list of what could not be removed."""
    from . import vault
    left = []
    if config.settings.get("vault"):
        try:
            vault.lock()
        except Exception:
            pass
        try:
            os.unlink(vault.IMG)               # the encrypted vault: its contents can't be read without its header
        except OSError as e:
            if os.path.exists(vault.IMG):
                left.append(f"vault ({e.strerror})")
    home = config.home().rstrip("/") or "/"
    if home in ("", "/"):
        return ["home folder (not erased: it is the root of the disk)"]
    for n in os.listdir(home):                # without a vault (or under it): the home folder's contents, hidden ones too
        p = os.path.join(home, n)
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.unlink(p)
        except OSError:
            left.append(p)
    for p in [os.path.join(config.ETC, "settings.json"), os.path.join(config.ETC, "conduct.txt"), os.path.join(config.ETC, "timezone")] + \
            glob.glob("/var/lib/iwd/*.psk") + glob.glob("/var/lib/iwd/*.8021x") + glob.glob("/etc/NetworkManager/system-connections/*") + glob.glob("/etc/wireguard/*.conf"):
        try:
            if os.path.exists(p):
                os.unlink(p)
        except OSError:
            left.append(p)
    subprocess.run(["sync"], timeout=120)
    return left
