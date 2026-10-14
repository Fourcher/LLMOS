# 13 pictures-lock-terminal

## Task and verdict

Everyday things: screenshot and view it, change wallpaper to mountains and back, lock and unlock, open and close the power menu without choosing an action, open the terminal and run `ls`.

**Verdict: PARTLY.** Screenshot, picture viewer, lock/unlock, power menu and terminal all work. Wallpaper is broken: the mountain change is unclear on screen, and putting it back failed twice.

## Steps

Times are from the request to the reply (from `vmuser.py waitreply`) or to the screen change.

1. **"take a screenshot"** (shot `13-after-screenshot.png`). Reply in 2 s: "Saved in Pictures as screenshot-20261014-121905.png and copied." A preview window opened by itself showing the desktop. Works. The preview also captured the text in the request box ("take a screenshot"), which is minor.
2. **"show my pictures"** (shot `13-show-pictures.png`). Reply in 4 s: "1 item in ~/Pictures." A Pictures window showed the screenshot thumbnail. Works.
3. **Click the thumbnail** (shot `13-open-image.png`). Image viewer opened at once, showing the screenshot. Works.
4. **Close viewer and Pictures window** (shot `13-closed-pictures.png`). Both closed with the X buttons. Works.
5. **"set my wallpaper to a picture of mountains"** (shot `13-wallpaper-mountains.png`). Reply in 5 s: "Wallpaper set: Mountains of Wadi Shawka denoised.jpg (Original: Florian Kriechbaumer Derivative work: Aristeas, CC BY-SA 4.0)." The desktop changed to a dark, blurry green-and-black image. I could not see any mountains. Before, the desktop was a purple glow. The VM's GNOME setting (`gsettings get org.gnome.desktop.background picture-uri`) still reads `adwaita-l.jxl` after the change, so the change did not go through the system setting.
6. **"put the wallpaper back to how it was"** (shot `13-wallpaper-restored.png`). Took 52 s, then "I couldn't finish that. Try saying it another way, or say 'what did you do'." The steps it listed searched `/usr/share/backgrounds`, `/usr/share/wallpapers`, `~/Pictures/Wallpapers` and ran `find / -name background.jpg`. Nothing was found.
7. **"change the wallpaper back to the original one"** (shot `13-wallpaper-restore2.png`). Took 35 s, same failure message.
8. **"what did you do"** (shot `13-what-did-you-do.png`). Reply in 3 s, listing searches for "Wadi Shawka", "shawka.jpg" and "denoised.jpg" in `~/Pictures`. The VM has no file with those names there. Also `ls /usr/share/backgrounds` in the VM says the folder does not exist, although `gsettings` names a file in it. The mountain picture the reply names is not on disk where it looks. I did not change any VM files to fix this; the brief says not to do the task for the computer.
9. **Lock icon, top bar** (shot `13-locked.png`). First click at the lock icon (1096, 23) only showed the tooltip "Lock now" and did not lock. Second click (shot `13-locked2.png`) locked the screen after about 2 s. Lock screen shows "Locked." with a Passphrase field and Unlock button.
10. **Typed "correct horse battery" and pressed Enter** (shot `13-unlocked.png`). Unlocked at once (about 2 s). Greeting "Good afternoon, Jordan" with three suggestion buttons. Works.
11. **Power icon, top right** (shot `13-power-menu.png`). A "Power" window opened with four buttons: Lock, Sleep, Restart, Shut down. Closed with the window's X (shot `13-power-closed.png`). Nothing was chosen. Works. Shut down is red, which is good.
12. **"open the terminal"** (shot `13-terminal-open.png`). Reply in 4 s: "Opened the terminal in a window." A foot window opened with a prompt `~ #`, and a "Foot" chip appeared bottom-left. Works.
13. **Clicked in the terminal, typed `ls`, Enter** (shot `13-terminal-ls.png`). Output: Apps, Documents, Downloads, Music, Pictures, Videos, lost+found. Works.
14. **Closed the terminal with its X** (shot `13-terminal-closed.png`). Window closed; the "Foot" chip at bottom-left is gone. Works.

## Bugs

1. **Wallpaper restore fails.** Typed "put the wallpaper back to how it was": "I couldn't finish that. Try saying it another way..." Typed "change the wallpaper back to the original one": same. Expected: the purple default back. The reply after "what did you do" shows it looked for files that do not exist.
2. **Mountain wallpaper is not visible and not in the system setting.** Typed "set my wallpaper to a picture of mountains": "Wallpaper set: Mountains of Wadi Shawka denoised.jpg". Expected: a mountain picture on the desktop. Got a dark blurry image with no mountains. The VM's GNOME setting did not change. The reply names a file that is not in Pictures.
3. **Wallpaper is now different from the start.** The start was a purple glow. After unlock the desktop is near-black with a faint purple top-left corner. I could not get it back, so the desktop is not as the user left it.
4. **Lock icon needed two clicks.** Click at (1096, 23) showed "Lock now" but did not lock. Second click locked. Expected: one click locks. (Could be a first click that only focused the top bar. Not certain.)
5. **"While you were away" window disappeared on lock.** It was open before the lock and was not there after unlock. Expected: either it stays or comes back. (Unsure if locking closes all windows by design.)
6. **Leftover file.** The screenshot from step 1 is still in ~/Pictures as `screenshot-20261014-121905.png`. The brief says to leave the computer as found, but I did not delete it, since that is a file change by hand. The user may want it removed.

## Friction

- The wallpaper reply says "Done" in the middle of a bad result, then the restore reply is only "I couldn't finish that". A person would not know what to try next.
- The restore took 52 s and 35 s before failing. That is slow for a failure.
- The request box and reply panel kept an old answer on screen after the lock (the "what did you do" panel stayed over the desktop until the lock).
- Screenshot preview window and the Pictures window open on top of each other; the preview shows the request text too.
- Power menu tooltip "Power" is useful; the menu has no hint that Shut down and Restart are irreversible.

## Ideas

- For wallpaper, offer a short list of pictures to choose from, and a "Reset to default" button in Settings, so restore does not depend on a chat request.
- Make the lock icon respond to one click.
- Keep the "While you were away" window through lock, or say when it was closed.
- After a failed wallpaper change, say what the picture was and where it came from in plain words.
- Name the screenshot after the time and offer to delete it, or put it in a Screenshots folder.

## Timings summary

| Step | Time |
|---|---|
| take a screenshot | 2 s |
| show my pictures | 4 s |
| set wallpaper to mountains | 5 s |
| put wallpaper back (try 1) | 52 s, failed |
| change back to original (try 2) | 35 s, failed |
| what did you do | 3 s |
| lock (click 2) | about 2 s |
| unlock with passphrase | about 2 s |
| open terminal | 4 s |
