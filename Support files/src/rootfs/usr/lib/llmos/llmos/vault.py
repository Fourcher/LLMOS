"""Encrypted storage for everything personal. The user's home (/root: memory,
tasks, notes, audit log, mail account, files) lives in a LUKS2 container
(argon2id) unlocked with their passphrase at boot. There is no recovery key
and no backdoor: forget the passphrase and the data is gone."""
import os
import shutil
import subprocess
import tempfile

from . import config

IMG = os.path.join(config.LIB, "vault.img")
NAME = "llmos-vault"
DEV = "/dev/mapper/" + NAME
MOUNT = "/root"


class VaultError(Exception):
    pass


def _run(cmd, secret=None):
    p = subprocess.run(cmd, input=secret, capture_output=True, text=True)
    if p.returncode != 0:
        raise VaultError((p.stderr or p.stdout).strip()[:300] or f"{cmd[0]} failed")
    return p


def enabled():
    return bool(config.settings.get("vault")) and os.path.exists(IMG)


def unlocked():
    try:
        with open("/proc/mounts") as f:
            return any(ln.split()[0] == DEV for ln in f)
    except OSError:
        return False


def _mount():
    _run(["mount", "-o", "noatime", DEV, MOUNT])
    os.chmod(MOUNT, 0o700)
    # (never chdir into the vault: a process whose cwd is inside it keeps it busy at lock time)


def verify(passphrase):
    """True if the passphrase opens the vault's header (checked without mounting anything)."""
    if not passphrase:
        return False
    p = subprocess.run(["cryptsetup", "open", "--test-passphrase", "--key-file=-", IMG],
                       input=passphrase, capture_output=True, text=True)
    return p.returncode == 0


def create(passphrase):
    if not passphrase:
        raise VaultError("empty passphrase")
    subprocess.run(["modprobe", "dm-crypt"], capture_output=True)
    st = os.statvfs(config.LIB)
    free = st.f_bavail * st.f_frsize
    size = max(1 << 30, min(64 << 30, int(free * 0.4)))
    os.makedirs(config.LIB, exist_ok=True)
    fd = os.open(IMG, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.ftruncate(fd, size)  # sparse: only uses disk as it fills
    os.close(fd)
    try:
        _run(["cryptsetup", "luksFormat", "--type", "luks2", "--pbkdf", "argon2id",
              "--pbkdf-memory", "524288", "--iter-time", "2000", "--batch-mode",
              "--key-file=-", IMG], passphrase)
        _run(["cryptsetup", "open", "--key-file=-", IMG, NAME], passphrase)
        _run(["mkfs.ext4", "-q", "-L", "llmos-vault", DEV])
        staging = tempfile.mkdtemp(prefix="vault-")
        _run(["mount", DEV, staging])
        # move whatever already exists in the home into the vault
        for name in os.listdir(MOUNT):
            src = os.path.join(MOUNT, name)
            _run(["cp", "-a", src, staging + "/"])
        _run(["umount", staging])
        os.rmdir(staging)
        for name in os.listdir(MOUNT):
            src = os.path.join(MOUNT, name)
            if os.path.isdir(src) and not os.path.islink(src):
                shutil.rmtree(src, ignore_errors=True)
            else:
                os.unlink(src)
        _mount()
    except Exception:
        subprocess.run(["cryptsetup", "close", NAME], capture_output=True)
        try:
            os.unlink(IMG)
        except OSError:
            pass
        raise
    config.settings.set("vault", True)


def unlock(passphrase):
    if unlocked():
        # already open (a lock that could not unmount): the passphrase is still checked
        return verify(passphrase)
    subprocess.run(["modprobe", "dm-crypt"], capture_output=True)
    p = subprocess.run(["cryptsetup", "open", "--key-file=-", IMG, NAME],
                       input=passphrase, capture_output=True, text=True)
    if p.returncode != 0:
        return False
    _mount()
    return True


def lock():
    if not unlocked():
        return
    os.chdir("/")
    subprocess.run(["sync"])
    _run(["umount", MOUNT])
    _run(["cryptsetup", "close", NAME])


def change_passphrase(old, new):
    with tempfile.TemporaryDirectory(dir="/run") as d:
        fo, fn = os.path.join(d, "o"), os.path.join(d, "n")
        for path, val in ((fo, old), (fn, new)):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
            os.write(fd, val.encode())
            os.close(fd)
        _run(["cryptsetup", "luksChangeKey", "--key-file", fo, IMG, fn])
