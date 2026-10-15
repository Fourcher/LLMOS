# 03 Video and music (real laptop, Intel + NVIDIA, 1920x1200)

## Task
Video and music through YouTube: play a video, pause/resume (click picture, card buttons, voice), volume (card slider, Sound panel, voice), full screen, close by window X, relaxing music, stop, next/skip. Sound checked with `/proc/asound/card0/pcm0p/sub0/status` and `amixer get Master`.

## Verdict
PARTLY. Playback, sound, pause/resume, volume, full screen, close and stop all work on this laptop. Two status texts are wrong or stale, skip leaves the window missing for about 10 s, and the card volume slider ignores some clicks.

Start state: Master 40% (raw 26214). Ended at 39% (raw 25559). See step 13.

## Steps

1. **"play a funny cat video on YouTube"**: reply in 7 s. Video window appeared under the top bar (about y=75 to 720, left side). "Now playing" card top right with Pause, Stop, Full screen and a volume slider. Two screenshots 3 s apart show different frames (moving). PCM status RUNNING, Master 40%. Screenshots: dev-v03-cat-1, dev-v03-cat-2.
2. **Click the picture to pause**: card changed to "paused" with a Resume button. Picture frozen (two shots identical). PCM went "closed" within about 2 s. Screenshot: dev-v03-paused, dev-v03-paused-2.
3. **Click picture to resume**: playing again, PCM RUNNING. Screenshot: dev-v03-resumed.
4. **Card Pause, then card Resume**: both worked. Screenshots: dev-v03-card-pause, dev-v03-card-resume.
5. **Card volume slider**: clicked low, Master went 40% to 19% (dev-v03-slider-low). Speaker icon Sound panel showed Volume 19%, matching the mixer. Slider knob and panel agree.
6. **Full screen** (card button): video filled the screen, top bar hidden, black bands at top and bottom. **Esc** returned to the window with video still playing. Screenshots: dev-v03-fullscreen, dev-v03-after-esc.
7. **"turn it down"**: reply in 2 s, "Volume set to 9%." (19% to 9%). **"louder"**: reply in 2 s, "Volume set to 19%." **"pause"**: reply in 2 s, "Paused.", PCM closed. **"resume"**: reply in 2 s, "Playing.", PCM RUNNING.
8. **Close with window X**: window and card both disappeared at once. PCM closed within a few seconds, no player process left (checked with `ps`). **But the chat still said "Playing."** Screenshot: dev-v03-closed-x.
9. **"play some relaxing music"**: reply in 7 s. Card "Now playing" shown, PCM RUNNING. It is NOT audio only: a video window opened showing a still beach-at-night image with a "Inner Healing Sleep" logo. Screenshot: dev-v03-music.
10. **"stop the music"**: reply in 2 s, "Stopped and closed.", window and card gone, PCM closed. Screenshot: dev-v03-stopped.
11. **"play a funny cat video on YouTube"** (reply 7 s), then **"play the next one"**: reply in 21 s, switched to "You Laugh You Lose ... Part 4" (PetsFun).
12. **"skip"**: reply in 2 s, "Playing the next one.", card changed to "Funniest Animals 2024 ... Diary Pets" at once. **The video window did not appear for about 10 s** (first shot showed only the card; second shot 6 s later showed the window). Screenshots: dev-v03-skip (no window), dev-v03-skip-2 (window).
13. **Volume restore**: card slider clicks at 1775/1788/1797 changed it to 33% and 51%, but clicks at 1780/1784/1788 did nothing. Used the Sound panel slider (track x about 1399 to 1775): 40% click gave 39%, the next nudge also 39%. Left at 39%.
14. **Cleanup**: Stop on the card closed the video. Final: no windows, PCM closed, no player process, Master 39%. Screenshots: dev-v03-final, dev-v03-final2 (clean desk).

Timings: reply times 2 s to 7 s for most commands, 21 s for "play the next one" (busy time, includes loading the next video). Video window appeared within about 5 s of the first reply, but up to about 10 s after skip.

## Bugs
1. **Stale "Playing." after closing the window** (step 8). Exact close: clicked the video window X at (957,97). Expected the reply to clear or say "Closed." Got the card and window gone (good), but the chat still said "Playing." and it stayed until the next command.
2. **Chat text does not match the card after skip** (step 12). Said "play the next one" then the chat showed "You Laugh You Lose" while the card and the new window showed "Funniest Animals 2024 ... Diary Pets". Skip reply "Playing the next one." is fine, but the older "Now playing" bubble was not updated.
3. **Gap with no video window after skip** (step 12). Card changed in about 1 s; the picture took about 10 s to appear. A person would think it stalled. Should show a loading state in the window or the card.
4. **Card volume slider ignores some clicks** (steps 5, 13). Clicks at x=1760, 1775, 1797 changed volume; clicks at 1780, 1784, 1788 did nothing. The Sound panel slider works. Could not tell whether the card uses a different hit area than the track.
5. **"Relaxing music" opens a video window with a still image** (step 9). Music is not shown as audio only; some people may expect a plain "now playing" card with no picture. Not necessarily wrong.
6. **Volume restore is off by one step**: a click gave 39%, not 40% (raw 25559 vs 26214). Minor.

Not bugs (noted): on-screen text in the video corner ("DY", "60118431459", "bbornena_0308", "Collab") comes from the source videos. The black bands around full screen are letterboxing of portrait video.

## Friction
- "turn it down" halved the volume (19 to 9), and "louder" doubled it (9 to 19). Fine, but a person would expect a smaller step.
- Pause: the card and the window both change, but the sound device needs about 2 s to close. Not noticeable.
- Full screen has no visible exit hint; Esc works.

## Ideas
- Clear or update the reply text when the video window is closed or the track changes.
- Show "Loading..." in the video window during skip.
- Make the card volume slider respond to clicks along the whole track.
- Show music with a plain card and no video window.

## Hardware notes
- Intel SOF audio (sof-hda-dsp) output "Speaker" was selected; PCM goes RUNNING during play and closed when paused or stopped. Sound works.
- Video was smooth in all screenshots (frames changed every few seconds). No black frames, no tearing seen in still shots. Graphics not checked beyond that.
- Battery 100% plugged in during test.
