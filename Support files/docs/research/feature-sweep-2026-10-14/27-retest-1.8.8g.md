# Retest 1.8.8g: video, Files, notes (tester 27)

**Verdict: PARTLY.** Video window, sound panel, Files and window restore all pass. Step 5 fails: the note contains a "[Neighbor's Name]" blank and the delete reply names the wrong folder.

## Steps

| # | What I did | Expected | Saw | Time | Screenshot |
|---|---|---|---|---|---|
| 1 | Said `play a funny cat video on YouTube` | Video plays, card shows | Video opened below top bar; card "Now playing" fully visible on right. Reply: "Now playing 'You Can't Stop Laughing At These Cats...'" | 8 s | s1_playing |
| 1a | Clicked speaker icon in top bar | Sound panel opens, video stays | Sound panel opened at 75%, video still visible | <2 s | s1a_sound |
| 1b | Clicked 75% in panel | Shows 75%, card slider ~3/4 | Panel already read 75% when opened, so this click changed nothing. Re-tested: set 25%, then 75%. Panel read 75 and card slider moved to about 3/4 | <3 s | s1b_75real, s1b_card75 |
| 1b | Clicked 25% | Both follow | Panel 25, card slider at about 1/4 | <3 s | s1b_25, s1b_card25 |
| 1c | Dragged video title bar (300,77) to (700,250) | Moves | Moved, card and top bar unaffected | <2 s | s1c_drag |
| 1c | Clicked desk background | Video stays | Video stayed visible. (My first click landed inside the video and paused it; repeated on true desk at (150,600), video still visible) | <2 s | s1c_desk2 |
| 1d | Clicked Stop on card | Video and card close | Both closed, desk shown | <3 s | s1d_stop |
| 2 | Clicked apps grid, then Files | Files opens, apps panel closes | Files (Thunar) opened, apps panel closed by itself. Opened at "/" not Home | <3 s | s2_grid, s2_files |
| 3 | Said `show my files`, clicked folder name Documents | Shows ~/Documents | Home window listed; Documents opened as "~/Documents", 1 item | 2 s | s3_home, s3_docs_name |
| 3 | Clicked "↑ Home" then "Open" on Documents | Same result | Home shown, then ~/Documents shown | <3 s | s3_up, s3_docs_open |
| 4 | Maximize Documents, then maximize again | Returns to same place and size | Before: x 481-1259, y 67-250. After restore: identical | <2 s | s4_max, s4_restore |
| 5 | Said `write a short thank-you note to my neighbour and save it as thanks3.txt` | Note with no blanks, "Saved as ~/Documents/thanks3.txt" | Note contains "Dear [Neighbor's Name]," ; "Saved as ~/Documents/thanks3.txt." Reply text matches the file | 14 s | s5_reply |
| 5 | Checked file in VM | File exists, matches reply, no blanks | File exists at /root/Documents/thanks3.txt, matches reply, but contains "[Neighbor's Name]" | - | - |
| 5 | Checked reply line after it had finished | Sentences spaced | Sentences spaced correctly (no "it.Saved"). Reply card did not shrink; header still read "writing thanks3.txt..." | 8 s wait | s5_shrunk |
| 5 | Said `delete thanks3.txt` | File removed | Reply "Moved to trash." File gone from Documents, now at /root/.Trash/thanks3.txt | 114 s | s5_delete |
| end | Clicked Close on reply card | Desk clean | No windows open | - | final |

## Bugs

1. **Placeholder left in the note.** Words typed: `write a short thank-you note to my neighbour and save it as thanks3.txt`. Saw: "Dear [Neighbor's Name]," in the reply and in /root/Documents/thanks3.txt. Should: no square-bracket blank. Either use a plain greeting or ask for the name first. (Step 5 file check, s5_reply.)
2. **Wrong folder in the delete reply.** Words typed: `delete thanks3.txt`. Saw: "trash /home/jordan/Documents/thanks3.txt", but the file was in /root/Documents and went to /root/.Trash/thanks3.txt. Should: show the real path (or ~/Documents). (s5_delete.)
3. **Reply header stuck on "writing thanks3.txt..."** after the file was saved. Words typed: same as bug 1. Should: say "saved" or drop the progress line. (s5_shrunk.)

## Friction

- Files from the apps panel opens at "/" (File System) and not at Home, which is where a person would look first. (s2_files)
- Sound panel covers the Now playing card while it is open, so the card's slider cannot be seen at the same time. (s1a_sound)
- Toasts stack over window titles: "6 items in ~." covers the Home title and "1 item in ~/Documents." covers the "Open in Files" button. (s3_up, s3_docs_open)
- "Delete thanks3.txt" took 114 s for a move-to-trash. (s5_delete)
- Stale status after Stop: the reply line still read "Volume set to 75%." after the video was stopped (harmless, but confusing).
- Tester note: the first 75% click was a no-op because the volume already read 75% when the panel opened. Re-tested from 25%.
- Tester note: my first desk click landed inside the video window and paused it. Repeated on the real desk.

## Ideas

- Pre-fill the note with a real greeting or ask "What is your neighbour's name?" before saving.
- Open Files at Home.
- Show the current volume on the card while the Sound panel is open, or keep the card above the panel.
- Clear the progress line when the reply is saved.

## Cleanup

- All windows closed. Volume left at 75% (its starting value).
- Left alone: /root/Documents/zz-sweep3.txt (existed before this test). thanks3.txt is in /root/.Trash (moved, not permanently deleted).
