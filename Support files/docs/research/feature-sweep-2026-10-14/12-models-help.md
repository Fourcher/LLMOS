# 12 models-help: learning about the computer

## Task
Open the Models page (click the model name in the top bar, and ask "open the models page"). Read it. Click Use on a downloaded model. Download the smallest model not yet downloaded and watch progress for 2 minutes. Ask: which model are you using, what version is this, what can you do, help, how do I connect to wifi, is my data private. Note timings and whether answers are right and plain.

## Verdict
PARTLY

The Models page opens fast and reads well, and the download works. But the page does not refresh after a download or a Use click, the answer to "which model are you using?" is wrong, and "how do I connect to wifi?" fails while "wifi" works.

## Steps
1. Start state: desk with "While you were away" window. Top bar shows "Ministral 3 3B". Screenshot `run/sweep/shots/12-start.png`.
2. Clicked "Ministral 3 3B" in the top bar. Models window opened in about 4 s. Screenshot `12-model-click.png`. Tooltip "Models" appears on hover.
3. Read the page (scrolled through, screenshots `12-models-scroll1` to `12-models-bottom`):
   - Intro: "Pick the brain. On-device models run on this computer and stay private; an online model is faster and can be stronger, but needs the internet and an account. 3.8 GB RAM."
   - ON THIS COMPUTER: Ministral 3 3B (IN USE, 2.1 GB), then Hermes 3 3B 2.0 GB, Gemma 4 E2B 3.3 GB, Granite 4.2 3B 2.2 GB, Gemma 4 E4B 4.6 GB, Ministral 3 8B 5.2 GB, Dolphin 3.0 8B 4.9 GB, Granite 4.1 8B 5.3 GB, LFM2.5 8B 5.2 GB, Gemma 4 12B 7.0 GB, Ministral 3 14B 8.2 GB. Each has "Good at" and "Watch out" lines.
   - ONLINE (OPTIONAL): "Check for new models" button, Claude Opus 5.5, Claude Sonnet 5.5, Claude Fable 5.1, Claude Haiku 4.5, and a "Set up an online model" button. The text says online requests leave this computer and are billed.
   - VOICE, SPEECH TO TEXT: Whisper Tiny 78 MB, Whisper Base 148 MB (IN USE), Whisper Small 488 MB, Whisper Large v3 Turbo 574 MB, and more below.
   - Time to read everything: about 2 minutes of scrolling.
4. Use button, first try: the only downloaded chat model (Ministral 3 3B) has no Use button, only an "IN USE" label. Clicked its name row at (546, 241). Nothing opened and the list shifted a little. Screenshot `12-after-click-inuse.png`. Whisper Base also shows only "IN USE" with no button.
5. Download the smallest model not yet downloaded. The chat models are 2.0 GB or more, so I took Whisper Tiny (78 MB, the smallest on the page). Clicked "Download 0.1 GB" at 12:14:00. Screenshot `12-dl-3s.png` at about 3 s showed the progress panel "downloading Whisper Tiny (78 MB) from huggingface.co/ggerganov/whisper.cpp", 64%. State at about 4 s already said "Downloaded and verified Whisper Tiny; say 'use the tiny voice model' to switch to it". The progress panel was gone by 23 s. Nothing needed cancelling. Shots `12-dl-23s.png`, `12-dl-53s.png`, `12-dl-2min.png`.
6. After the download the Whisper Tiny row still said "Download 0.1 GB" in the open Models window (checked at 53 s, 2 min, and 12:15). Only after I closed the window and asked "open the models page" did the row show "INSTALLED" with Use and Remove buttons (`12-models-whisper-after.png`).
7. Use on Whisper Tiny. First click at (1137, 262) did nothing visible; the list had shifted up. Second click at (1137, 157) worked: the reply "Speech is now transcribed with Whisper Tiny, for the microphone and for Super+D dictation". Screenshots `12-click-use-tiny.png`, `12-click-use-tiny2.png`. The row and the IN USE tag stayed stale (Whisper Tiny still showed Use, Whisper Base still IN USE) until the window was reopened.
8. Asked "open the models page". Reply "Here it is." in 2 s. Models window reopened. Screenshot `12-ask-open-models.png`.
9. Questions (timings from `say` to reply):
   - "which model are you using?" 13 s. Reply: "I am using the **Whisper Tiny** model for speech-to-text and the **LLM OS** architecture for all other tasks. My voice responses are generated using the same model as your dictation..." WRONG (see Bugs). Shot `12-q-which-model.png`.
   - "what version is this?" 2 s (4 s elapsed). Reply: "This is LLM OS 1.8.5 (build 2026-10-14, aarch64). Updates come from Jordans-Mac-Mini.local; the last one (1.8.5) was installed." Correct, matches the "While you were away" note.
   - "what can you do?" 3 s (5 s elapsed). Reply lists find and open files, read and send email, play music and videos, set reminders and timers, change screen and sound, install programs, answer questions, and examples. Opened "Try saying" window with example chips (`12-q-version-and-can.png`). Email and install claims not tested.
   - "help" 3 s (4 s). Reply: "Type what you want. F1 talks. Esc closes the window." Shot `12-q-help.png`. Short and correct, but not much help for a new user.
   - "how do I connect to wifi?" 30 s, then "I couldn't finish that. Try saying it another way..." FAILED.
   - "connect me to wifi" 30 s, same failure message.
   - "wifi" 2 s (3 s). Reply "Here are the Wi-Fi networks." Network window: "Now: Connected (cable). This computer has no Wi-Fi; plug in a network cable." Buttons Airplane mode and Settings. Correct. Shot `12-q-wifi-retry.png`.
   - "is my data private?" 2 s (4 s). Reply: online only when a request needs it (web search, page or video asked for, download, model or app install, clock set at start). Requests answered by the on-device model. "No tracking, no telemetry and no account." Mic only on while talking. Files and chats locked with passphrase. Say "audit". Plain enough but long. Consistent with the Models page; the no-telemetry claim was not checked. Shot `12-q-ismydatapriv.png`.
10. Cleanup: switched voice back with "use the base voice model" (reply "Speech is now transcribed with Whisper Base..."). Closed Models and Network windows. "While you were away" was open at start and left alone. Final shot `12-final.png`.

## Bugs
1. **Wrong answer to "which model are you using?"**. I typed "which model are you using?". Reply: "I am using the Whisper Tiny model for speech-to-text and the LLM OS architecture for all other tasks." The top bar and Models page both show Ministral 3 3B as the chat model. Should have said Ministral 3 3B (on this computer, 2.1 GB), and the voice model is a separate thing. The "same model as your dictation" claim is also wrong.
2. **Models list does not refresh after a download.** I clicked Download on Whisper Tiny. Assistant said "Downloaded and verified". The row kept saying "Download 0.1 GB" until I closed and reopened the window. Should show INSTALLED with Use and Remove straight away.
3. **Models list does not refresh after Use.** After Use on Whisper Tiny, the row still showed Use and Whisper Base still showed IN USE. Should move the IN USE tag to Whisper Tiny.
4. **"how do I connect to wifi?" and "connect me to wifi" fail.** Each took about 30 s then "I couldn't finish that. Try saying it another way". "wifi" alone works and shows the Network window. A new user would likely type the full question first.
5. **Use click on Whisper Tiny did not register the first time.** Clicking at (1137, 262) did nothing; the list had moved. Second click at (1137, 157) worked. The page seems to shift position between a screenshot and a click.
6. **Clicking the in-use model name does nothing**, which is probably fine, but the row gives no hint what to do.

## Friction
- Models page is long: 11 chat models, 1 online section with 4 Claude models, and 6+ voice models. Needed about 2 minutes of scrolling to see everything. Nothing on it says which one to pick for a first-time user.
- "IN USE" is shown only as a label, with no button, on the model in use. A user may look for a Use button there.
- Download reports success in the chat box, but the Models page shows it as not installed, so the user will think it failed.
- Help answer is very short. "Type what you want. F1 talks." does not tell a new user what they can ask.
- "What can you do?" lists many things at once and opens a "Try saying" window. Useful, but the chat answer alone is a long list.
- The privacy answer is long, but it does answer the question in plain words.

## Ideas
- Answer "which model" from the actual setting (Ministral 3 3B), and say separately which voice model is used for speech.
- Refresh the Models list (and mark INSTALLED / IN USE) as soon as a download finishes or Use is clicked.
- Accept "how do I connect to wifi" by routing to the Network window, as "wifi" already does.
- Put a short "Recommended" note on the Models page, or a Use button on the model in use.
- Help could list 3 or 4 things to try, as the "Try saying" window does.

## Notes on leftovers
- Whisper Tiny (78 MB) is still downloaded in the VM. The active voice model was switched back to Whisper Base. I did not remove the file.
- The chat model is unchanged (Ministral 3 3B).
