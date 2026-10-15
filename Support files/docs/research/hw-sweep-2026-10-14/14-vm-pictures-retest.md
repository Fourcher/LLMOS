# 14 VM pictures retest

**Verdict: PARTLY.** Screenshots, PDFs, black and white, "draw me a cat" and most picture actions work. Rotate makes the wrong or extra files, "this picture" for wallpaper sets the wrong picture, and the wallpaper restore reported success several times without the desk visibly changing.

Times are from the request to the reply (wall clock or the tool's "took" line). Screenshots are in `run/sweep/shots/` (s1a to s6b, end).

## Steps

1. **"take a screenshot"** (shot s1a). Reply in 5 s: "Saved in Pictures as screenshot-20261015-020914.png". The window opened on screen. WORKS.
2. **"rotate it"** with that window open (shot s1b). Reply in about 5 s: "Saved ~/Pictures/screenshot-20261015-020914-edited.png (1.4 MB) with: rotate". Expected a rotated copy shown on screen. What happened: the file was made, but the window on screen became a new screenshot, screenshot-20261015-020921.png, which was taken by the request itself. The rotated copy was never shown. PARTLY.
3. **"make it black and white"** (shot s1d). About 5 s. The reply says it was made from screenshot-20261015-020921 (the window on screen). Made screenshot-20261015-020921-edited.png, and again took and opened a new screenshot (020936). WORKS, with the same side effect.
4. **"save it as a PDF"** (shot s1e). About 5 s. Reply: "Saved ~/Pictures/screenshot-20261015-020936.pdf (1.0 MB) with: no changes". The PDF is in Pictures. WORKS. The reply says "no changes", which is confusing after a PDF was made.
5. **"show my pictures"** (shot s2a). About 5 s. "8 items in ~/Pictures." The file window shows the thumbnails. BUG: file names overlap in the grid, so they can't be read.
6. **Click the picture** at (680,258) (shot s2b). It opened screenshot-20261015-020914-edited.png, the rotated copy, shown rotated. WORKS.
7. **"rotate this picture"** (shot s2c). About 5 s. Reply: "Saved ... screenshot-20261015-020914-edited-edited.png (1.3 MB) with: rotate". The picture window still showed the old image. It again took and opened a new screenshot (021004). PARTLY, same problems as step 2.
8. **"convert my screenshot from today to a PDF"** (shot s3a). About 5 s. Reply: "Saved ~/Pictures/screenshot-20261015-021004.pdf (835.2 KB)". It picked the 021004 screenshot, which was not the one on screen. It again took and opened a new screenshot (021014). WORKS, with the side effect. The brief says to convert "my screenshot from today", and there were many, so it is unclear which one a person would expect.
9. **"make my wallpaper a picture of the ocean"** (shots s4a, s4b). About 6 s. It set "Ocean beach at low tide against the sun.jpg" without asking for internet permission. The desk turned grey and showed a beach with a bird. WORKS.
10. **"put the wallpaper back"** (shots s4c, s4d). About 5 s. Reply: "Wallpaper put back to how it was." The desk stayed grey and beach-like on the screenshots taken right after. Later, the desk showed the mountain again (end shot), after the windows were closed. Result unclear, see Bugs.
11. **"the wallpaper is still the beach, put my old mountain wallpaper back"** (shot s4h). 52 s, then "I couldn't finish that." The log shows it searched for a "mountain" picture in Pictures, found none, and stopped. FAILED. The wording was a natural retry.
12. **"draw me a picture of a cat"** (shot s5a). About 5 s. Reply: "I can't draw new pictures on this computer, so here is a real photo instead: Felis catus-cat on snow.jpg (Von.grzanka, CC BY-SA 3.0)." A real cat photo opened in a window. WORKS, and the wording is plain.
13. **"use this picture as my wallpaper"** with the cat window open (shot s6a). About 6 s. Reply: "Wallpaper set to screenshot-20261015-020914-edited.png." The cat was not used. The desk showed the rotated screenshot. BROKEN.
14. **"put the wallpaper back"** (shot s6b). About 4 s. Reply: "Wallpaper put back to how it was." The desk still showed the screenshot-style background. Result unclear, see Bugs.
15. **Clean up.** Closed the cat window and the screenshot window (the file windows closed too). Deleted the 10 files of today I made with `rm` in the VM (all `screenshot-20261015-*` files). Left the pre-existing `screenshot-20261014-121905.png` and `Wallpapers/` as found. The "While you were away" window was already open when I started and is still open.

## Bugs

1. **"rotate it" / "rotate this picture" open a new screenshot.** The request takes a new screenshot of the desk and opens it, so the picture the person is working on is pushed out of view. Repeated for black and white and for "convert ... to a PDF". Expected: the open picture is changed and shown. Seen: a new file screenshot-...-021004.png or -021014.png is made and opened each time.
2. **The rotated copy is not shown on screen.** Asked for "a rotated copy shown on screen". The reply says "Saved ... -edited.png", and the window still shows the old image. The copy only shows when it is opened from the Pictures grid.
3. **Rotate picks a different file from the one on screen.** "rotate it" rotated screenshot-20261015-020914.png, while the window open was -020921. Expected: the rotated copy of the picture in the open window.
4. **"use this picture as my wallpaper" uses the wrong picture.** With the cat window open, it set screenshot-20261015-020914-edited.png. Expected: the cat photo. The reply names the wrong file, so the person would notice, but it is still wrong.
5. **"put the wallpaper back" is hard to trust.** It said "put back to how it was" three times, while the desk still showed the changed wallpaper at the time of the check. In the end the desk showed the mountain wallpaper again after the windows were closed, so the display may only be slow to refresh. Expected: the desk changes right away and the reply matches what is on screen.
6. **"put my old mountain wallpaper back" fails.** It searched for a mountain photo in Pictures and gave up after 52 s with "I couldn't finish that". Expected: it restores the wallpaper the computer had before. Asking for "put the wallpaper back" alone works in the reply.
7. **File names overlap in the Pictures grid.** The labels run into each other, so the names can't be read.
8. **"save it as a PDF" says "no changes"** even though a new PDF was made. Confusing.
9. **"convert my screenshot from today to a PDF" picks a file that is not the one on screen**, and there were 5 candidates. It does not say which one it picked before it saves.

## Friction

- Every picture action makes an extra screenshot window, which covers the picture being worked on.
- Wording differences: "put back" works, "old mountain wallpaper" does not.
- Requests take about 5 s and replies are quick. The 52 s failure is the only slow step.
- The "Working..." card for "convert my screenshot..." stayed on screen for a long time after the reply arrived (seen in shots s4e to s4g), and the screen view lagged the state.
- The ocean wallpaper request did not ask for permission to use the internet. The brief expected it might. No problem, but the wallpaper was a black and white beach.

## Ideas

- Do not take a new screenshot when the request is about the picture already open.
- Show the rotated or edited copy in the window that the request came from.
- Use the name of the open picture in the reply so the person can see which file was used.
- Keep the original wallpaper name and offer "put back" as a single step that reads the saved name.
- Show full file names in the Pictures grid, or wrap them.
