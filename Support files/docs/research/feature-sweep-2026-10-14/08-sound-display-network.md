# 08 sound-display-network: everyday hardware controls

## Task
Everyday hardware controls on the VM: sound (window presets and voice), display (brightness, night light, size), network (online check, IP, Wi-Fi).

## Verdict
PARTLY. Voice requests for volume, mute, night light, size, online status and IP answer correctly and fast (about 2 s). The Sound window and top-bar state are unreliable: the Sound window number lags by many seconds, and mute is not shown anywhere. Brightness is correctly refused (no backlight in a VM). The Wi-Fi request gives a nonsense answer on a machine with no Wi-Fi.

## Steps
Starting state: top bar showed a speaker icon with tooltip "Sound 100%", Network icon with no status, screen size 100%, night light off (as far as the replies show). Screenshot 08-start.

1. **Sound icon, click (1191,23).** Expected the Sound panel at once. The first click showed nothing; the panel appeared on the second look, about 3 s later (08-sound-open, 08-sound-open2). Reads "Volume 100%" with presets 25/50/75/100% and a mute button. There is no drag slider, only preset buttons.
2. **Click 50% preset (1080,180).** Toast "Volume set to 50%." appeared (08-sound-50). The window still showed 100% and the 100% button still highlighted, even after a 3 s wait (08-sound-50b). The top-bar tooltip read "Sound 100%" (08-sound-after-icon). Actual level could not be checked from the VM (pactl and amixer report no audio server; the card is "virtio-snd").
3. **Say "turn the volume down".** Reply "Volume set to 40%." in about 2 s. Window and tooltip then both read 40% (08-sound-40, 08-muted-tooltip). The starting point is unclear because of step 2, so the size of the drop cannot be judged.
4. **Say "mute".** Reply "Muted." (08-say-mute). The Sound window still showed 40% with no mute state. The top-bar tooltip read "Sound 40%" and the icon looked unchanged (08-muted-tooltip). Mute is not visible anywhere on screen.
5. **Say "unmute".** Reply "Unmuted." (08-say-unmute).
6. **Restore 100%.** Clicked the 100% preset in the Sound window. Toast "Volume set to 100%." The window still said 40% (08-restore-vol100) and the tooltip still said "Sound 40%" (08-restore-vol100-tip). After about 8 s more, the window read 100% (08-restore-check) and the tooltip read "Sound 100%" (08-end-volume). Restored.
7. **Say "make the screen brighter".** Reply: "This machine has no adjustable backlight, so brightness can't be changed here (under a virtual machine the host controls the screen)." Correct and clear (08-say-brighter). Nothing changed.
8. **Say "turn on night light".** Reply "Night light is on: the screen turns warmer from 7 pm to 7 am" (08-say-nightlight-on). It is 11:53 am, so there is no visible change. The reply is accurate but a person would not see anything happen.
9. **Say "turn off night light".** Reply "Night light is off" (08-say-nightlight-off). Restored.
10. **Say "make everything bigger".** Reply "Done — size 120%." The desktop and top-bar text visibly grew (08-say-bigger). Works.
11. **Say "make everything back to normal size".** Reply "Done — size 100%." Back to normal (08-say-normal).
12. **Network icon, click (1144,23).** Network panel opened (08-network-open): "Now: Connected (cable)", "This computer has no Wi-Fi; plug in a network cable.", buttons "Airplane mode" and "Settings". The reply text still said "Here are the Wi-Fi networks." Tooltip "Network".
13. **Say "am I online?".** Reply "Yes, the internet is working (answered in 143 ms)." (08-say-online). Correct, quick.
14. **Say "what's my IP address".** Reply "On your network: 10.0.2.15. To the internet: 72.200.127.190." (08-say-ip). Shown in the bar. Plausible for a VM NAT.
15. **Say "connect to wifi".** Reply "Here are the Wi-Fi networks." (state). No list appeared on screen, the bar kept showing the IP answer (08-say-wifi, 08-say-wifi-later), and the panel still says there is no Wi-Fi. Wrong answer.
16. Closed the Network window and the Sound window. Final state: desk, one "While you were away" window (it was there at the start), Sound 100%, size 100%, night light off.

Timing: voice replies came back in about 2 s each. Window and tooltip refresh took 3 to 10 s after a change.

## Bugs
1. **Sound window and top bar lag or show a stale level.** Typed/clicked: click "50%" in the Sound window. Saw: toast "Volume set to 50%.", window still 100%, tooltip "Sound 100%". Expected: window and tooltip show 50% at once. The same happened when clicking "100%" (toast 100%, window and tooltip 40% for about 8 s).
2. **Mute is not shown.** Said: "mute". Saw: reply "Muted.", window still at 40% with no muted state, tooltip "Sound 40%", icon unchanged. Expected: the top-bar icon shows a muted speaker and the window shows Muted.
3. **Sound panel did not open on the first click.** Clicked the top-bar sound icon. Nothing visible for about 2 s; it opened on the next look. Minor, but a person might click again and toggle it shut.
4. **Wi-Fi answer is wrong.** Said: "connect to wifi". Saw: reply "Here are the Wi-Fi networks." with no list, and the panel says "This computer has no Wi-Fi". Expected: "This computer has no Wi-Fi, plug in a network cable" or a list of networks if any.
5. **Reply bar did not show the wifi reply.** After "connect to wifi" the bar kept the earlier "On your network: 10.0.2.15" text. Expected the new reply.
6. **Night light gives no visible result before 7 pm.** Said: "turn on night light". Reply "Night light is on: the screen turns warmer from 7 pm to 7 am." Nothing on screen changed (it was 11:53 am). The reply is accurate, but a person would think it did nothing. Expected: a note such as "It will start at 7 pm" is shown, or a preview.
7. **Drag is not possible on volume.** Brief asks for drag; the Sound panel has only preset buttons. Not a bug, but note for the tester plan.

## Friction
- The Sound panel's number and icon tooltip refresh slowly. A person would click 50% and think it failed.
- Mute and the level are not separate in the top bar; a person cannot tell whether sound is muted.
- "Make the screen brighter" is answered honestly. Good, but a person may want a note that the host controls the screen.
- The Network panel stays in the same spot; the top-bar network icon gives no status (connected or not) without opening it.
- Pressing the sound icon again closes the panel. This is expected but easy to hit by accident.

## Ideas
- Update the Sound panel and top-bar tooltip the moment the level changes, and show a muted state (icon and "Muted" text).
- Add a drag slider to the Sound panel, as the brief expects.
- For night light before its schedule, say "It will turn on at 7 pm".
- For "connect to wifi" on a machine without Wi-Fi, say so plainly and point to Settings.
- Show the new reply in the bar right away.
