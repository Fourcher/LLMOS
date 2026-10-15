# 02 Hardware controls (real laptop, Dell Vostro 5620)

## Task
Real laptop hardware controls, used the way a person would: sound, brightness, battery, network, display size, power menu, and "what computer is this" questions. Checked against the laptop with `devlink.py vm` (read-only checks, plus restoring settings).

## Verdict
PARTLY

Brightness, battery, Wi-Fi, text size and the power menu work. There is no sound device at all, so the volume controls cannot work. The screen-size and graphics-card questions have real failures, and the graphics answer is wrong.

## Baseline (before testing)
- Master volume 0% (mixer unmuted). Brightness 96000/96000 (100%). Battery 100%, status Full, AC online. Text size 100%.
- RAM 15683 MB total. Wi-Fi: The Domed Depot, 192.168.86.134. Panel resolution 1920x1200.
- Top bar: no speaker icon. Icons present: app grid, "Ministral 3 3B", "On its own", Wi-Fi, battery 100% with bolt, power.

## Steps

1. **Speaker icon in top bar.** Not present. The top bar has no sound control at all. Screenshot: dev-02-start.
2. **"set the volume to 40%"** (2 s). Reply: "This machine has no sound card, so there is no volume to set." Mixer still 0%. `aplay -l`: "no soundcards found". Screenshot: dev-02-vol40.
3. **"mute"** (2 s) and **"unmute"** (2 s). Both give the same "no sound card" reply. Screenshots: dev-02-mute, dev-02-unmute.
4. **"set the brightness to 50%"** (2 s). Reply "Brightness set to 50%." Backlight 48000 (50%). Screenshot: dev-02-bright50.
5. **"make the screen brighter"** (2 s). Reply "Brightness set to 65%." Backlight 62400. Screenshot: dev-02-brighter.
6. **"dim the screen"** (2 s). Reply "Brightness set to 50%." Backlight 48000. The screen visibly darker than at 100% (compared dev-02-dim with dev-02-start). Brightness restored with "set the brightness to 100%" (2 s), backlight 96000.
7. **"how much battery do I have"** (2 s). Reply "The battery is at 100%, charging." Top bar: 100% with bolt. sysfs: capacity 100, status **Full**, AC online 1. Screenshot: dev-02-battery.
8. **"is it charging"** (2 s). Same reply, "charging". sysfs says Full, which means not charging. Screenshot: dev-02-charging.
9. **Wi-Fi icon click.** Panel "Network" opened: "Now: Wi-Fi: The Domed Depot", the connected network with Disconnect and Forget, and nearby networks Deliver Food here 2G, SETUP-D30E, WYDBETH, Trejo (Connect buttons). Panel closed with Esc. Nothing clicked inside it. Screenshot: dev-02-wifi-panel.
10. **"what wifi am I on"** (2 s). "You're on the Wi-Fi network 'The Domed Depot'." Matches iw/nmcli. Correct.
11. **"how fast is my internet"**: took about 2.5 min (the first bash wait timed out at 120 s, then 12 s more). Reply: "151.53 Mbit/s download and 61.21 Mbit/s upload." It opened a "Sources" window with a link to speedtest.net. Not verified. Screenshot: dev-02-speed.
12. **"what's my ip address"** (2 s). "On your network: 192.168.86.134. To the internet: 72.200.127.190." The LAN address matches the laptop. The public address was not checked. Screenshot: dev-02-ip.
13. **"what's my screen resolution"**: failed after 103 s. "I couldn't finish that. Try saying it another way..." Retried with "what resolution is my screen": failed after 111 s, same message. Tried a third time with "how big is my screen": failed after 92 s. The real value is 1920x1200 (xrandr and drm agree). Screenshots: dev-02-resolution, dev-02-resolution2, dev-02-resolution3.
14. **"make the text bigger"** (2 s). "Done — size 120%." The top bar, the Sources window and the reply bubble all fit the 1920x1200 screen. Screenshot: dev-02-textbigger.
15. **"make the text smaller"** (2 s). "Done — size 100%." Back to the baseline 100%. Screenshot: dev-02-textsmaller.
16. **"what computer is this"** (2 s). Opened an "About this computer" window: Dell Inc. Vostro 5620, 12th Gen Intel Core i7-1260P, 16 cores, Memory 15.3 GB, Disk 438.3 GB free of 468.1 GB, LLM OS 1.8.9.8, Linux 6.12.111. Matches the laptop (cpuinfo i7-1260P, 16 CPUs; RAM 15.3 GiB; DMI Vostro 5620). Screenshot: dev-02-computer.
17. **"how much memory do I have"** (2 s). Reply was only "Here's this computer.", not a number. The About window (Memory 15.3 GB) answered it, which is correct. Screenshot: dev-02-memory.
18. **"what graphics card do I have"**: failed after 119 s ("I couldn't finish that."). Retried with the same words: answered after 86 s, "You have a NVIDIA GeForce RTX 3060 graphics card (detected by /dev/dri/card0). The system uses the proprietary NVIDIA drivers." This is wrong in three ways (see Bugs). Screenshot: dev-02-gpu2.
19. **Power icon (top right).** Opened a "Power" window: Battery 100% with bolt, and buttons Sleep, Restart, Shut down. Closed with the red close dot. Nothing pressed inside it. Screenshot: dev-02-power, dev-02-power-closed.
20. **Cleanup.** Closed the About, Sources and Power windows. Volume left at 0% (never changed), brightness 96000 (100%), text size 100%. Wi-Fi still connected to The Domed Depot.

## Bugs
1. **No sound at all, and no way to tell.** No speaker icon in the top bar. "set the volume to 40%", "mute" and "unmute" all say "This machine has no sound card, so there is no volume to set." This is correct for this laptop (aplay finds no cards, PipeWire has no sink), but a person would look for a speaker icon and find nothing. The brief expects it in the top bar. Should: show a volume control when a sound device exists, or say "no sound device" somewhere visible. Also note this is a real-hardware gap, not a bug in the answer.
2. **Screen size question fails.** "what's my screen resolution", "what resolution is my screen" and "how big is my screen" each ran for 90 to 110 s and ended "I couldn't finish that." The answer is 1920x1200, available from xrandr and drm. Should: answer in one line, like the other display questions.
3. **Graphics card answer is wrong.** Claims an "NVIDIA GeForce RTX 3060... detected by /dev/dri/card0... proprietary NVIDIA drivers." Facts on this laptop: card0 = NVIDIA (PCI 10de:25aa, driver **nouveau**, not proprietary; no /proc/driver/nvidia). card1 = Intel i915 (PCI 8086:46a6), which the answer leaves out. No lspci here, so the model name "RTX 3060" is not confirmed. Should: list both GPUs, with the real driver in use. The first try failed after 119 s, the second took 86 s.
4. **Charging answer contradicts the battery state.** "The battery is at 100%, charging." sysfs status is "Full" (AC connected, battery full). The top bar bolt also suggests charging. Should: "100%, plugged in, fully charged" (or charging only when status is Charging).
5. **"How much memory" gives no number.** Reply was "Here's this computer." and it opened the About window. The window shows 15.3 GB, which is right, but the question was not answered in words.
6. **Speed test is slow and opens a Sources window.** About 2.5 min for "how fast is my internet." It is a real test (speedtest.net), so it is not wrong, but nothing says it is running. Should: say "Testing, this takes about a minute" and close the Sources window after.
7. **Sources window left behind.** After a speed test the "Sources" window stayed open with the link. It was closed manually.

## Friction
- The "Network" panel is useful: it shows connected and nearby networks, and Disconnect/Forget sit right next to the connected network (easy to hit by mistake, not touched here).
- Brightness reports a percent and changes the screen visibly. Good.
- Text size "bigger" and "smaller" work and the layout still fits at 120%.
- Replies that open a window ("Here's this computer.") leave the user to read the answer from the window.

## Ideas
- Show a speaker icon in the top bar that reads "No sound device" when there is none.
- Add a resolution line to the About window (1920x1200).
- Use the real driver name in GPU answers and list all GPUs.

## Screenshots
dev-02-start, dev-02-vol40, dev-02-mute, dev-02-unmute, dev-02-bright50, dev-02-brighter, dev-02-dim, dev-02-battery, dev-02-charging, dev-02-wifi-panel, dev-02-speed, dev-02-ip, dev-02-resolution, dev-02-resolution2, dev-02-resolution3, dev-02-textbigger, dev-02-textsmaller, dev-02-computer, dev-02-memory, dev-02-gpu, dev-02-gpu2, dev-02-power, dev-02-power-closed (under run/sweep/shots/ in Support files)
