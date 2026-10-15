# 12: Pictures, wallpaper, drawing, lock screen, terminal (VM test)

Tester: Haiku agent, 2026-10-15, about 01:16 to 01:27 (VM time). Screenshots are in `run/sweep/shots/` (names below).
The VM was not shut down or restarted. Before the test the desktop showed "While you were away" and an "Inbox · 4" window, both left open at the end.

## Task and verdict
Task: screenshot, Pictures, wallpaper, picture editing, drawing, lock screen, terminal.

**Verdict: PARTLY.** Screenshots, the Pictures folder, lock/unlock and the terminal work. Picture editing (rotate, black and white, PDF), the wallpaper change and "draw me a picture of a cat" do not work. Several requests get a stale answer ("3 items in ~/Pictures.") or the wrong action (a new screenshot).

## Steps

1. **Take a screenshot.** Said "take a screenshot" at 01:16:25. Reply in 2 s: "Saved in Pictures as screenshot-20261015-011627.png and copied: paste it anywhere with Ctrl+V." A picture window opened showing it (`step1-shot`). The file is in /root/Pictures. Verdict WORKS.
   - "show my pictures" at 01:16:35. Reply in 2 s: "3 items in ~/Pictures." A Pictures window showed the Wallpapers folder and two PNGs (`step1-pics`). The two file names overlap in the grid. Verdict WORKS, with a layout bug.

2. **Ocean wallpaper.** Said "make my wallpaper a picture of the ocean" at 01:16:45. The computer ran a web search ("ocean landscape high resolution free to use") and then asked to run commands. It asked six times, each as a "Run this command?" or "open wget" dialog, and I clicked **Don't** on each one:
   - `wget -O ~/Pictures/ocean_wallpaper.jpg https://pixabay.com/images/id-5000000/ocean-landscape/ -T LLM OS` (`step2-dialog`, `step2-dialog2`)
   - `cp ~/Pictures/ocean_wallpaper.jpg /etc/lightdm/backgrounds/ocean_wallpaper.jpg`
   - `chmod 644 /etc/lightdm/backgrounds/ocean_wallpaper.jpg`
   - `sed -i ... /etc/lightdm/lightdm.conf` (two edits)
   - `systemctl restart lightdm`
   - `rm ~/Pictures/ocean_wallpaper.jpg`

   The card kept saying "needs your answer" and then "Working" until I clicked **Stop** at 01:21:22 (about 4.5 minutes). A first Stop click landed on the wrong place (`clicktext Stop` hit a point in the screenshot window). The second click on the card's Stop button worked.
   - Checked afterwards: no ocean file, no change to /etc/lightdm (the folder and config do not exist in the VM), no change to Pictures.
   - "put the wallpaper back" at 01:21:24. Reply in 2 s: "Wallpaper put back to how it was." The desktop changed from the dark purple background to a mountain photo (`step2-back`). That is not how it was at the start, so the reply is wrong. After the next lock and unlock the desktop was dark again.
   - Verdict: BROKEN (download and system-file steps; the product wants to run root commands from a web search).

3. **Open a picture and edit it.**
   - Double-clicked `screenshot-20261015-011627.png` in the Pictures window at 01:21:48. The picture window opened in 4 s (`step3-open`). The window has no toolbar and no menu (a right-click shows nothing).
   - "rotate it" at 01:21:55. Reply in 8 s: "3 items in ~/Pictures." Not rotated (`step3-rotate`).
   - "rotate this picture" at 01:22:26. Reply after 97 s: "3 items in ~/Pictures." Not rotated (`step3-rotate5`).
   - "make it black and white" at 01:24:14. Reply in 8 s: "3 items in ~/Pictures." Still in colour (`step3-bw`).
   - "save it as a PDF" at 01:24:30. Reply in 2 s: "Which file? Say its name..." The open picture is not used as "it".
   - "rotate screenshot-20261015-011627.png" at 01:24:37. It took a NEW screenshot instead (`screenshot-20261015-012446.png`, `step3-rot-name`).
   - "save screenshot-20261015-011627.png as a PDF" at 01:24:56. Reply: "There is no file screenshot-20261015-011627.png." The file is there.
   - "convert my screenshot from today to a PDF" at 01:25:06. It took another NEW screenshot (`screenshot-20261015-012516.png`, `step3-pdf-3`).
   - Checked with `ls -la /root/Pictures`: no PDF, no edited copy, no rotated or black-and-white file. My only changes were the extra screenshots (removed later).
   - Also: I clicked "Open in Files" by mistake, which opened Thunar. I closed it.
   - Verdict: BROKEN (rotate, black and white and PDF do nothing; the computer takes a screenshot instead of rotating).

4. **Draw a cat.** "draw me a picture of a cat" at 01:25:20. Took 30 s. No picture was made. A "Sources" window opened with one link, "ASCII Art Cats - ASCII Art Archive". The reply was empty (`step4-cat`, `step4-cat2`). Verdict BROKEN (no picture, and it sent me to a web link instead). The chat card stayed stuck on "Working... 7 s / usually ~4 s" with "About to: screenshot" for several minutes afterwards.

5. **Lock icon and passphrase.**
   - Clicked the lock icon (1096, 23) at 01:26:19. The lock screen ("Locked.") showed within about 2 s (`step5-locked2`).
   - Wrong passphrase "wrong passphrase" at 01:26:29 (Enter). Message in red in about 3 s: "That passphrase didn't work." (`step5-wrong`). Good.
   - Right passphrase at 01:26:36. Unlocked in about 4 s (`step5-unlocked`).
   - Locking closed EVERY window: the Inbox, the Pictures window and the screenshot and Sources windows. After unlock only "While you were away" was left. A person would not expect that, and the Inbox was not closed by me. Verdict WORKS, with a surprise.

6. **"lock the screen" by asking.** Said it at 01:26:45. Reply "Done." in about 5 s, and the lock screen came up. Unlocked with the right passphrase at 01:26:53, back at the desk by 01:26:56. Verdict WORKS.

7. **Terminal.** "open the terminal" at 01:26:58. Reply in 2 s: "Opened the terminal in a window." A "foot" window opened (`step7-term`). I clicked into it, typed `ls` and pressed Enter. The output was Apps, Documents, Downloads, Music, Pictures, Videos, lost+found (`step7-ls`). Closed with its X at 01:27:11. No window left (`step7-closed`). Verdict WORKS.

## Bugs
1. **Picture editing is not understood.** "rotate it", "rotate this picture", "make it black and white" each get the stale reply "3 items in ~/Pictures." and do nothing. Exact words: "rotate it" / "make it black and white". Expected: the open picture rotates, or the computer says it cannot rotate and shows what it can do.
2. **"rotate ..." and "convert ... to a PDF" take a screenshot.** "rotate screenshot-20261015-011627.png" and "convert my screenshot from today to a PDF" each created a new screenshot. Expected: rotate the picture, or say it is not possible.
3. **"save it as a PDF" cannot find the file it just listed.** Reply: "There is no file screenshot-20261015-011627.png." The file is in /root/Pictures. Expected: find it and save the PDF, or say there is no PDF option.
4. **"make my wallpaper a picture of the ocean" runs web search, then root commands.** The commands included wget from a web page, `cp` into /etc/lightdm, `chmod`, editing lightdm.conf, `systemctl restart lightdm` and `rm`. The product's own check asked before each one (good), but the request for a wallpaper should not have needed root commands at all. The wget line also contains a stray argument: `-T LLM OS`.
5. **"put the wallpaper back" says it did, and the desktop shows a different picture.** Reply: "Wallpaper put back to how it was." The desktop changed from dark purple to a mountain photo.
6. **Stop click position.** `clicktext Stop` clicked the wrong place (a point in the picture window). It is a tester-tool issue, not a product bug, but the card's own Stop worked.
7. **"draw me a picture of a cat" gives a web link.** The reply was empty and a "Sources" window showed an ASCII-art link. Expected: an image, or a clear "I can't draw".
8. **Overlapping file names** in the Pictures grid (the two file labels print on top of each other).
9. **Stuck card.** The chat card kept "Working... / usually ~4 s" for minutes after a request had finished.
10. **Lock closes all windows.** Locking closed windows that were open (Inbox, Pictures, screenshots). After unlock they were gone with no way back.

## Friction
- Picture window has no controls at all: no rotate, no black and white, no save-as. A person would look for a button here first.
- The "Run this command?" dialogs show raw shell commands for root, which is frightening for a normal user even when the answer is No.
- A web-search result led to a command request. Nothing in the request said why it needed the wget.
- The Inbox and "While you were away" windows were already open when I started, so "close every window" does not give a clean desk. I left them.
- Pictures window: "Open in Files" is next to the view buttons and is easy to hit by accident.

## Ideas
- Picture window: add a small toolbar with Rotate, Black and white, Save as PDF.
- Recognise "rotate", "black and white" and "PDF" as picture actions, and say so when they are not possible, instead of taking a screenshot.
- "put back" should keep the wallpaper that was there before the change (save it first).
- Wallpapers: pick from the pictures already on the machine before going to the web.
- Lock: keep the open windows.

## Cleanup
- Removed from the VM /root/Pictures: `screenshot-20261015-011627.png`, `screenshot-20261015-012446.png`, `screenshot-20261015-012516.png` (all made by this test). Left: `screenshot-20261014-121905.png` and `Wallpapers/` (they were there before).
- No PDF, no edited copy, no ocean file, nothing written to /etc.
- All windows I opened are closed. "While you were away" was open from the start and is still open.
- The VM was not shut down or restarted.

## Summary
- Verdict: PARTLY. Lock, unlock, the terminal and screenshots work. Rotate, black and white, PDF, the wallpaper and drawing do not.
- Worst: "rotate it" / "make it black and white" say "3 items in ~/Pictures." and do nothing; "rotate ..." and "convert ... to a PDF" take a screenshot.
- The wallpaper request ran a web download and root commands. I clicked Don't on all six prompts and then Stop after about 4.5 minutes.
- "put the wallpaper back" says it worked but changes the desktop to a different picture.
- Locking closes every open window.
