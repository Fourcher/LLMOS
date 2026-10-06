"""A folder locked with its own password ("lock this folder with a password"): the folder becomes one encrypted 7z file
(AES-256, file names hidden too) next to where it was, which opens only with that password, here or on any computer
with 7-Zip. "unlock <name>" turns it back into the folder. The password is never stored; 7z gets it on its standard
input stream, never on a command line other programs could read."""
import os
import shutil
import subprocess

SUFFIX = " (locked).7z"


def _7z():
    return shutil.which("7z") or shutil.which("7za")


def _run(args, password, timeout=3600):
    # creating: -p with no value makes 7z ask for the password (twice), read from stdin. Testing and extracting: no -p at
    # all (a bare -p there means an empty password); 7z asks when it meets the encrypted archive, again from stdin
    p = subprocess.run([_7z()] + args, input=(password + "\n") * 2, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stderr or p.stdout).strip()


def lock(folder, password):
    """(ok, words). The folder's files are removed for good only after the locked copy has been checked with the password."""
    folder = os.path.abspath(folder.rstrip("/"))
    if not _7z():
        return False, "the locking program (7-Zip) is not installed: say “install 7zip”"
    if not os.path.isdir(folder):
        return False, f"{folder} is not a folder"
    if len(password) < 4:
        return False, "that password is too short (4 characters at least)"
    arc = folder + SUFFIX
    if os.path.exists(arc):
        return False, f"there is already a locked copy: {os.path.basename(arc)}"
    rc, err = _run(["a", "-t7z", "-mhe=on", "-p", "-bso0", "-bsp0", arc, folder], password)
    if rc != 0 or not os.path.exists(arc):
        try:
            os.remove(arc)
        except OSError:
            pass
        return False, f"could not lock it: {err[-200:]}"
    rc, err = _run(["t", "-bso0", "-bsp0", arc], password)
    if rc != 0:
        os.remove(arc)
        return False, f"the locked copy did not check out, so nothing was changed: {err[-200:]}"
    shutil.rmtree(folder)
    return True, arc


def unlock(arc, password):
    arc = os.path.abspath(arc)
    if not _7z():
        return False, "the locking program (7-Zip) is not installed: say “install 7zip”"
    if not os.path.isfile(arc):
        return False, f"{arc} is not a locked folder"
    where = os.path.dirname(arc)
    name = os.path.basename(arc)[:-len(SUFFIX)] if arc.endswith(SUFFIX) else os.path.splitext(os.path.basename(arc))[0]
    if os.path.exists(os.path.join(where, name)):
        return False, f"a folder called {name} is already there; rename or move it first"
    rc, err = _run(["t", "-bso0", "-bsp0", arc], password)
    if rc != 0:
        return False, "wrong password" if "password" in err.lower() or "Wrong" in err else f"could not open it: {err[-200:]}"
    rc, err = _run(["x", "-bso0", "-bsp0", "-o" + where, arc], password)
    if rc != 0 or not os.path.isdir(os.path.join(where, name)):
        return False, f"could not unlock it: {err[-200:]}"
    os.remove(arc)
    return True, os.path.join(where, name)


def find_locked(words, home):
    """The locked folder the owner means by its name ('unlock taxes'), searched in the home folder (two levels)."""
    w = words.strip().lower().rstrip("/")
    hits = []
    for d, dirs, fs in os.walk(home):
        if d[len(home):].count("/") > 2:
            dirs[:] = []
            continue
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in fs:
            if f.endswith(SUFFIX) and (not w or w in f[:-len(SUFFIX)].lower()):
                hits.append(os.path.join(d, f))
    return sorted(hits, key=lambda p: (len(p), p))
