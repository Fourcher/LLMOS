# Fix a bug from the laptop

While you are using the laptop you can point at something that is wrong. The laptop tries to fix it on itself, waits for you to say yes, and then opens a pull request. It does not merge that pull request.

## What you can say

- **I found a bug, fix it.** Also: "hey, I found a bug here, fix it", "there's a bug, fix it", "this is broken, fix it", "this doesn't work, fix it", "fix this bug". Anything you say in the same sentence is the description.
- **Apply that fix.** Also "install that fix". The laptop says what changed, installs it, and checks health.
- **Undo that fix.** Drops a fix that is only staged. If it was already installed, the previous files are put back.
- **What happened with that fix.** The last thing the laptop did with it.
- **File that as an issue.** After a fix fails, opens a GitHub issue instead of a pull request.
- **Try the github report again.** Sends a report that was saved because the network or the token was missing.
- **Trust this laptop for updates.** Makes the signing key and tells you its code.
- **Stop signing my own updates.** Spoken fixes stop being installed. A computer you already paired is left as it is.
- **Get updates from my computer.** Still the way to trust a different computer. It keeps working next to the laptop's own key.

## Once, before the first install

1. Say **trust this laptop for updates**. Compare the key code it speaks with the one you expected. A fix is still not installed until you say **apply that fix**.
2. Save a GitHub token if you want the pull request opened for you. Without one, the laptop still fixes and installs, and it keeps the report until a token is there.

### The GitHub token

Use a fine-grained personal access token, limited to this one repository.

1. On GitHub, open Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token.
2. Resource owner: the account that can open pull requests on `Fourcher/LLMOS`.
3. Repository access: **Only select repositories**, and choose **Fourcher/LLMOS**.
4. Permissions:
   - Contents: **Read and write** (so it can push a branch)
   - Pull requests: **Read and write** (so it can open the pull request)
   - Issues: **Read and write** (so a failed fix can be filed as an issue)
   - Metadata is included. Do not grant Administration.
5. Generate the token and copy it. It starts with `github_pat_` and is shown only once.

On the laptop, save it so it is not left in the shell history:

```sh
python3 - <<'PY'
import getpass, sys
sys.path.insert(0, "/usr/lib/llmos")
from llmos.bugfix import save_github_token
save_github_token(getpass.getpass("GitHub token: "))
print("Saved.")
PY
```

The file is `github.token` in the loop's state directory, mode 0600. A setup script may instead write `/etc/llmos/github.token` (one line, mode 0600). The token is not printed back and is not put in the pull request.

## What happens

The laptop notes the window in front, any screen text or screenshot it already has, and a short piece of the recent logs. It edits a staging copy with the local model, runs a short list of tests (not the full suite), and stops. You hear what it changed. **Apply that fix** runs those tests again and, only if they pass, signs the update, installs it, and runs the health check. If the health check fails, the previous files are put back.

When the health check passes, it pushes a new branch and opens a pull request on `Fourcher/LLMOS`. The pull request has the bug you described, the diff, the light-test result, and the health-check result. If GitHub cannot be reached, or the token is not there, the report is saved. Say **try the github report again** later. If the fix itself fails, say **file that as an issue**.

## What it will not do

- It will not install a spoken fix while the kill switch is on, or past the daily cap, or past the iteration cap.
- It will not run the full test suite on the laptop. That suite has frozen a 16 GB machine. The light list is capped and run under `nice`.
- It will not restart network services, ssh, Tailscale, or the model server.
- It will not edit `selfloop_ctl.py` or `ota.py` in the same update.
- It will not merge the pull request.

## On a dev machine

`python3 tools/test-bugfix.py`

The loop's other checks are still `python3 tools/test-selfloop.py` and `python3 tools/test-selfloop-device.py`.
