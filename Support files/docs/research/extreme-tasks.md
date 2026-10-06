# Extreme requests: what a person might really ask an LLM-driven OS

Not features to build one by one: a spread of unusual, sweeping or many-step requests that test whether the OS's
general abilities (look, files, media, scheduling, mail, apps, commands) combine to do what was asked, exactly. A
request that changes the computer is followed by one that puts it back. Run with
`tools/usecase-run.py --file docs/research/extreme-tasks.md --out run/extreme` (VM only: these really change things).
The success column says what must actually be true afterwards, not what the reply should say.

| ID | Request | What must be true afterwards | P |
|---|---|---|---|
| U01 | "convert the entire interface to ASCII, like an old text terminal" | Desk restyled: monospace font, green/amber on black, square corners, no gradients | P1 |
| U02 | "back to the default look" | (put back) | P1 |
| U03 | "make all the windows triangles" | Does the nearest real thing (e.g. sharp/angled corners) and says plainly what it can't; no refusal, no nag | P1 |
| U04 | "make everything look like a 1950s newspaper" | Serif font, off-white paper colours, black ink accent | P1 |
| U05 | "back to the default look" | (put back) | P1 |
| U06 | "make the text tiny but the buttons huge" | Text size down, controls bigger (or the nearest the look allows), said exactly | P1 |
| U07 | "normal size everything" | (put back) | P1 |
| U08 | "everything in black and white, no colour at all" | Grayscale palette | P1 |
| U09 | "back to the default look" | (put back) | P1 |
| U10 | "speak klingon from now on" | Language set (or the nearest: tells what it did and how to undo) | P2 |
| U11 | "speak english" | (put back) | P2 |
| C01 | "take the newest jpeg in my pictures, turn it into a pdf, flip it upside down, add the words Happy Birthday, call it Happy Birthday.pdf, then email it to craig@localhost in an hour" | Happy Birthday.pdf exists, upside down, with the text; a scheduled task emails it as an attachment in ~60 min | P0 |
| C02 | "make a folder called Trip, move every pdf from downloads into it, and write a list of their names in a text file inside it" | ~/Trip has the PDFs and a list file naming each | P0 |
| C03 | "take a screenshot, crop it to the top half and make it my wallpaper" | Wallpaper is the cropped screenshot | P1 |
| C04 | "back to the default wallpaper" | (put back) | P1 |
| C05 | "turn on dark mode, set the volume to 30 percent and open bbc news in the browser on the left half of the screen" | All three done | P0 |
| C06 | "rename every file on my desktop to lowercase with dashes instead of spaces" | Desktop files renamed exactly so | P1 |
| C07 | "find all my photos, shrink them to half size, zip them up and put the zip on my desktop" | A zip on the Desktop holding half-size copies; originals untouched | P1 |
| C08 | "read the wikipedia article on octopuses, summarize it in five bullet points, save that as octopus.txt in documents and read it out loud" | ~/Documents/octopus.txt has five bullets; spoken | P1 |
| C09 | "convert every wav in my music folder to mp3, then delete the wav files" | MP3s exist and play; WAVs gone (to the trash) | P1 |
| C10 | "every weekday at 8am tell me the weather and then play some jazz" | A weekday 08:00 task doing both | P1 |
| C11 | "cancel the 8am task" | (put back) | P1 |
| C12 | "make a shopping list with milk, eggs and bread, then remind me about it at 6pm" | List has the three; reminder at 18:00 mentions the list | P0 |
| O01 | "say good morning to me every time I unlock the computer" | A greeting happens at each unlock (or the nearest true thing, said plainly) | P2 |
| O02 | "shut the computer down at 11pm every night" | A daily 23:00 shutdown task | P1 |
| O03 | "cancel the shutdown task" | (put back) | P1 |
| O04 | "block every website except wikipedia" | Only wikipedia reachable in the browser, with a way back | P2 |
| O05 | "unblock all websites" | (put back) | P2 |
| O06 | "make my mouse pointer huge" | Bigger cursor (or a true answer) | P2 |
| O07 | "show a giant clock in the middle of the screen" | A big clock is visible | P2 |
| O08 | "change my wallpaper to a random photo from my pictures every day" | A daily task that does it | P2 |
| O09 | "cancel the wallpaper task" | (put back) | P2 |
| G01 | "make me an app that tracks how many glasses of water I drink and reminds me every hour" | An app that counts glasses; an hourly reminder | P1 |
| G02 | "write a three paragraph story about a lonely robot, and save it as a pdf with a title page" | A PDF with a title page and the story | P1 |
| G03 | "make a spreadsheet for my monthly budget with rent, food and fun, with a total that adds itself up" | A spreadsheet file with those rows and a SUM formula | P1 |
| G04 | "build a little website about my cat Biscuit and open it" | An HTML page about Biscuit opens in the browser | P1 |
| G05 | "draw a cat in ascii art and save it to my desktop" | A text file with ASCII art on the Desktop | P2 |
| A01 | "count how many files I have in each folder and show it as a chart" | A chart (image or app) with per-folder counts | P2 |
| A02 | "open the newest pdf, read me the first paragraph, then email the pdf to craig@localhost" | First paragraph spoken/shown; email with the PDF attached | P1 |
| A03 | "what's the biggest file on this computer, and delete it if it's a video" | Names the biggest file; deletes it only if it's a video (to the trash) | P2 |
