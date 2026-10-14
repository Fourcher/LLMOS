# 03 Video

## Task
Watch a video like a normal person: "play a funny cat video on YouTube", check it plays and has sound/volume, pause (by asking and by clicking), resume, make it bigger or full screen, close it. Then "play some relaxing music" with the same steps.

## Verdict
PARTLY. Videos start, pause, resume and close, and the volume slider works. But pausing hides the picture for good, the full-screen request failed and left stray windows, and "close the video" and "stop the music" did not do what they said.

## Steps
Times are from the sweep tool unless noted. Screenshots are in `run/sweep/shots/`.

1. **"play a funny cat video on YouTube"** (03-cat-reply.png). Reply in 8 s: "Now playing 'You Can't Stop Laughing At These Cats... TOP Funny Cats Video 2025'". A video window opened with the picture showing. Expected: a player window with the video running. Met.
2. **Check it is moving.** Second frame 5 s later (03-cat-play2.png) shows different content. Plays. The player's clock reads 27.8 s, so audio/position advance. Sound level not heard directly; checked through the player.
3. **"pause"** (03-pause-ask.png, 03-pause-ask-later.png). Reply "Paused." in 3 s. The video window closed at once and was replaced by a "Now playing" card (Resume / Stop / volume slider). Expected: the video stays visible and paused. Confusing: the picture vanished.
4. **Click Resume on the card** (03-resume-click.png). Immediate. The card now shows Pause, and the player is running. The video window did NOT come back. Playback continues with no picture.
5. **Click Pause on the card** (03-pause-click.png). Immediate. Player confirmed paused.
6. **"resume the video"** (03-resume-ask.png). Reply "Playing." in 2 s. Player confirmed running.
7. **Volume slider on the card** (03-volume-drag.png). Dragging to the left set player volume to 35; dragging back gave 100. Works.
8. **Speaker icon in top bar** (03-speaker-icon.png). Opens a "Sound" panel: Volume 40%, buttons for mute, 25/50/75/100%, "More sound settings". This is a different volume from the card slider, which was at 100 while the panel said 40. Two volume controls that disagree.
9. **"make the video full screen"**. Did not work. Busy for about 3.5 minutes (waitreply gave up at 123 s; "About to: media control..." for a while). Final reply: "Failed to parse tool call arguments as JSON: ... invalid string: missing closing quote". Side effects: a "/tmp" file browser window and a "Full Screen Mode" window opened. The reply log also listed "volume: 100%". Video was not full screen. I closed both stray windows (03-close-tmp.png) and the Full Screen window.
10. **Maximize button on the card** (03-maximize-card.png). The card filled the screen as text only. No picture. Not a real full screen.
11. **"close the video"** (03-close-ask.png). Reply in 2 s: "The player is not open." The card was still on screen and the player was still running. Wrong.
12. **Stop button on the card** (03-stop-click.png). Immediate. Player shut down (checked: process gone). Card closed.
13. **"play some relaxing music"**. Reply in 8 s: "Now playing 'Relaxing music Relieves stress, Anxiety and Depression... Deep Sleep' by Relaxing Calming Music." A video window with a candle/water picture showed (03-music-later.png). Two frames 13 s apart differ (md5 check), so it plays.
14. **Maximize on the player window** (03-music-maximize.png). Worked: picture fills the screen, title bar stays.
15. **"pause the music"** (03-music-pause-ask.png). Reply in 2 s. Player confirmed paused. But the picture showed the mpv debug/stats overlay (File, Video, Audio, Cache info) and its control bar. The stats overlay was probably switched on by a letter typed into the focused player window, not by a request (see Bugs).
16. **Resume by clicking the player's play button** (03-music-resume-click.png). Worked (player confirmed playing).
17. **Player's full-screen button** (03-music-fs-button.png). Worked (player confirmed fullscreen).
18. **Click on the picture to pause**. Did NOT pause, tried twice (03-music-pause-click-video.png). Picture clicks do nothing here.
19. **Pause from the player's bottom bar**. The first click only showed the bar; the second click paused (confirmed; 03-music-pause-bar.png).
20. **"stop the music"** (03-music-stop-ask.png). Reply in 2 s was the old "Now playing" line, not a new answer. The player was playing again afterwards. The typed words most likely reached the fullscreen player, where the space key toggles pause.
21. **Exit full screen with the bottom-bar button** (03-exit-fs.png). Worked (fullscreen=false, still playing).
22. **Window X on the player** (03-music-close-x.png). The player closed (process gone), but a stale "Now playing" card stayed with Pause and Stop.
23. **Stop on the stale card** (03-music-card-stop.png). Card cleared. Desk is back to the start state, except a transient chat reply line and the pre-existing "While you were away" window (left as found).

## Bugs
1. **Pause hides the video.** Saying "pause" (and the earlier "pause" request) closed the video window and left only a text card. Expected: the picture stays visible, paused.
2. **Resume does not bring the picture back.** Clicking Resume on the card, or asking "resume the video", plays audio/position on with no visible picture. Expected: the video window comes back and plays.
3. **"make the video full screen"** typed exactly as above. Expected: the player goes full screen. Got: 3.5 minutes of busy, then "Failed to parse tool call arguments as JSON ... missing closing quote", plus a stray /tmp file browser and a "Full Screen Mode" window that I had to close.
4. **"close the video"** typed exactly as above, with the video playing. Expected: the video closes. Got: "The player is not open." while the card and player were still running.
5. **"stop the music"** typed exactly as above, with the full-screen player up. Expected: music stops. Got: the old reply text repeated and the music kept playing (the space in the request likely toggled pause in the player).
6. **Typed requests reach the full-screen player.** When the player is full screen the request box is hidden, so typed words go to the video (space pauses, letters trigger mpv keys such as the stats overlay after "pause the music"). A person would not know the box is hidden.
7. **Clicking the picture does not pause** in the player (two tries).
8. **Stale "Now playing" card** after the player window is closed with its X. The card keeps Pause and Stop until clicked.
9. **Two volume controls disagree.** Top bar Sound panel says 40%, card slider says 100% and changes only the player. Not clear which one a person should use.
10. **Card maximize shows no picture.** Maximizing the "Now playing" card enlarges the text card only. Expected: video full screen, or no maximize button.

## Friction
- Cat video: 8 s to the reply, 1 s to a picture. Good. Music: same.
- No ads, cookie banners or sign-in prompts appeared.
- Pause/resume by ask: 2-3 s each. Card buttons: instant.
- Pausing removes the video, so a person would think the video closed.
- The full-screen request is slow (3.5 min) before failing; no way to know that it is still trying except the small "About to: media control" text.
- The request box vanishes in full screen, so a person keeps typing into a video.
- Two different volume controls with no hint which applies.
- Sound was not heard directly; the volume test only checks the player's volume value.

## Ideas
- Keep the picture when paused: pausing should keep the video window, not swap it for a card.
- Make Resume reopen the picture if it was closed.
- Full screen: a button on the video window (the player already has one) and a request that does not produce a JSON error.
- Hide keystrokes from the video while the request box has focus, or bring the box back in full screen.
- Make "close the video" and "stop the music" both answer with what was stopped, and close the card with the player.
- One volume control: the card slider and the Sound panel should show the same number.
