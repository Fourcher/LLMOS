# Boring tasks: the dull, everyday things people do all day

The plain requests not already in use-cases.md (P0) or parity-tasks.md: small sums, quick facts, notes and lists,
simple file chores, mail, media and settings nudges. Each should be right, quick and exact; most need no model.
Run with `tools/usecase-run.py --file docs/research/boring-tasks.md --out run/boring` (VM; mail goes to the local test
server, craig@localhost). Changes are followed by the request that puts them back.

| ID | Request | What must be true afterwards | P |
|---|---|---|---|
| N01 | "what's 15% of 80" | 12 | P0 |
| N02 | "23 times 47" | 1081 | P0 |
| N03 | "convert 5 miles to km" | about 8.05 km | P0 |
| N04 | "how many ounces in a pound" | 16 | P0 |
| N05 | "what's 72 fahrenheit in celsius" | about 22.2 °C | P0 |
| N06 | "split 84 dollars between 3 people" | 28 each | P1 |
| N07 | "what's the time in tokyo" | Tokyo's current time | P0 |
| N08 | "how long until 5pm" | the right hours and minutes | P1 |
| N09 | "what day of the week is christmas this year" | the right weekday | P1 |
| N10 | "what's the weather tomorrow" | tomorrow's forecast for the owner's place, or asks where once | P0 |
| N11 | "will it rain today" | a yes/no with the chance | P1 |
| K01 | "spell necessary" | n-e-c-e-s-s-a-r-y | P0 |
| K02 | "define ubiquitous" | a short correct definition | P0 |
| K03 | "another word for happy" | a few synonyms | P1 |
| K04 | "translate good morning to spanish" | buenos días | P0 |
| L01 | "write down: dentist on friday at 3" | a note saved | P0 |
| L02 | "show my notes" | the notes, including the dentist one | P0 |
| L03 | "delete the note about the dentist" | that note gone, others kept | P1 |
| L04 | "add bread to my shopping list" | bread on the shopping list | P0 |
| L05 | "add milk and eggs to my shopping list" | both added | P0 |
| L06 | "what's on my shopping list" | bread, milk, eggs | P0 |
| L07 | "clear my shopping list" | the list empty | P1 |
| L08 | "set an alarm for 7am" | an alarm/timer that rings at 07:00 | P0 |
| L09 | "what reminders do I have" | the scheduled items listed | P0 |
| L10 | "cancel the alarm" | the 07:00 alarm gone | P0 |
| L11 | "remind me in 5 minutes to check the oven" | a reminder in 5 min | P0 |
| L12 | "set a 3 minute timer" | a 3-minute timer | P0 |
| L13 | "cancel all my reminders" | (put back) nothing scheduled | P1 |
| H01 | "make a text file called todo on my desktop" | ~/Desktop/todo.txt exists | P0 |
| H02 | "add call the bank to todo.txt" | the line is in the file | P1 |
| H03 | "open todo.txt" | opens in the editor | P0 |
| H04 | "copy Trip Plan.pdf to my desktop" | a copy on the Desktop, original kept | P0 |
| H05 | "move Hotel Booking.pdf to documents" | moved | P0 |
| H06 | "rename todo.txt to chores.txt" | renamed | P0 |
| H07 | "how big is my documents folder" | its size | P1 |
| H08 | "how many files are in downloads" | the right count | P1 |
| H09 | "sort my downloads by newest" | the folder shown newest first | P0 |
| H10 | "open the last screenshot" | the newest screenshot opens | P1 |
| H11 | "zip my documents folder" | a zip of Documents | P1 |
| H12 | "empty the trash" | trash empty (balanced: asked first) | P0 |
| E01 | "how many unread emails do i have" | the number | P0 |
| E02 | "read my latest email" | the newest email's sender, subject and gist | P0 |
| E03 | "email craig@localhost saying the meeting moved to 3pm" | sent, with that message | P0 |
| E04 | "did craig reply" | checks and answers | P1 |
| V01 | "turn the volume down a bit" | a bit lower | P0 |
| V02 | "volume 50" | 50% | P0 |
| V03 | "make the screen a little dimmer" | dimmer (or an honest "can't" on a VM) | P0 |
| V04 | "what wifi am i on" | the network name or "a cable" | P0 |
| V05 | "is the internet working" | yes/no, checked | P0 |
| B01 | "search the web for banana bread recipe" | a search opens | P0 |
| B02 | "open wikipedia" | wikipedia opens | P0 |
| B03 | "what's playing" | says what's playing, or nothing | P1 |
| B04 | "play some relaxing music" | music starts | P0 |
| B05 | "skip this song" | next track | P1 |
| B06 | "stop the music" | stops | P0 |
| G01 | "close all windows" | none left | P0 |
| G02 | "open settings" | settings shown | P0 |
| G03 | "what's today's date" | today's date | P0 |
