# 23 Retest: video and apps

## Task
Retest of the fixes from 03-video.md and 09-apps: play a cat video, pause, resume, full screen and exit it, close the video, show my apps and open Files, open the video player. Screenshots are in `run/sweep/shots/` with prefix `23-`.

## Verdict
WORKS. All seven steps pass. Pause keeps the picture, resume brings it back, full screen works, close works, Files opens a real file manager, and the player opens with no assertion. One stale reply line and one root-account warning remain.

## Steps

| # | What I typed or clicked | Expected | What happened | Time | Screenshot |
|---|---|---|---|---|---|
| 1 | "play a funny cat video on YouTube" | Video plays | Reply "Now playing 'You Can't Stop Laughing At These Cats 😂 TOP Funny Cats Video 2025'". Player window with picture. Picture changed between frames 5 s apart, so it plays. | 8 s to reply | 23-1b-cat-later.png |
| 2 | "pause" | Picture stays, paused | Reply "Paused." The video window stayed with the picture. Frame was the same 5 s later (paused). | 2 s | 23-2-paused.png, 23-2b-still-paused.png |
| 3 | "resume" | Picture back and playing | Reply "Playing." Picture visible with new footage. | 2 s | 23-3-resumed.png |
| 4a | "make the video full screen" | Full screen within a few seconds | Reply "Full screen. Press Esc or say 'exit full screen' to go back." Picture filled the screen. No JSON error, no stray windows. | 2 s | 23-4-fullscreen.png |
| 4b | "exit full screen" (typed while full screen) | Back to window | Window went back to windowed size and kept playing. The reply line still showed the old "Full screen..." text (stale). I did not need Esc. | 2 s | 23-4b-exit-fs-ask.png, 23-4c-after-exit-fs.png |
| 5 | "close the video" | Video closes | Reply "Stopped and closed." Window and card gone, no "player is not open" message. | 2 s | 23-5-close-video.png |
| 6 | "show my apps", then clicked the "Files" tile | File manager window opens | Apps window listed Programs including Files. Click opened Thunar at "/" with the file list. No "Failed to open" error. Closed it with X; its taskbar chip went away and no Thunar process was left. | 2 s, then 3 s | 23-6-apps.png, 23-6b-files-open.png, 23-6c-files-closed.png |
| 7 | "open the video player" | Player opens, no assertion | Reply "Opened the media player in a window." Window "No file - mpv" with the drop area. No assertion error. Closed with X; chip and process gone. | 2 s | 23-7-open-player.png |

Cleanup: closed the player, the Files window and the Apps window. Left "While you were away", which was on the desk at the start. Final desk is the same as at the start (23-8-final.png).

## Bugs
1. Minor, step 4b: after "exit full screen" the reply line kept the old text "Full screen. Press Esc or say 'exit full screen' to go back." The window did exit full screen. Expected: the reply says it went back to the window.
2. Minor, step 6: the Files window opens at "/" with the warning "Warning: you are using the root account. You may harm your system." (23-6b-files-open.png). Expected: no root warning in a plain file manager, or a reason for it.
3. Minor, step 6: the reply "Opened Files in a window." stayed in the reply state after the window closed, while the desk showed "Here they are." (the apps list reply). Reply state and screen did not match.

## Friction
- The full-screen request answered in 2 s this time, not the 3.5 min in 03-video.md. Good.
- Typing "exit full screen" while the player was full screen still reached the request box (the window exited), so the box did not get in the way this time.
- The Apps window listed "To-do" and "Calculator" under apps before I started. They were left as found.

## Ideas
- Update the reply text after a full-screen exit so it matches the window.
- Open Files as a normal user, or drop the root warning, since it is confusing for a plain file manager.
- Clear the reply line when its window closes, so it matches the desk.
