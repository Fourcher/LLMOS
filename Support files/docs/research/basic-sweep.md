# Basic sweep: the first things a person tries

Run after any model or OS change, on the VM, one request at a time (`tools/usecase-run.py --file docs/research/basic-sweep.md --yes Q08 --timeout 300 --out run/basic`). Every reply is read, not just graded. The point is the basics: the things a person does in the first five minutes.

| ID | Request | Must be true | P |
|---|---|---|---|
| S01 | "hello" | a short greeting, nothing done | P0 |
| S02 | "what can you do" | a short useful list in words | P0 |
| S03 | "what time is it" | the time, straight away | P0 |
| S04 | "open the files" | the files window opens | P0 |
| S05 | "open the terminal" | a terminal window opens | P0 |
| S06 | "open firefox" | the browser opens | P0 |
| S07 | "open the calculator" | the calculator opens | P0 |
| S08 | "what's the weather" | today's forecast in words | P0 |
| S09 | "turn the volume down" | volume goes down one step | P0 |
| S10 | "turn the volume up" | volume goes up one step | P0 |
| S11 | "make the text bigger" | text gets bigger, said plainly | P0 |
| S12 | "make it dark" | dark look, said plainly | P0 |
| S13 | "make it light" | light look, said plainly | P0 |
| S14 | "what's my ip address" | the local and internet address | P0 |
| S15 | "is the internet working" | yes or no, from a real check | P0 |
| S16 | "how much battery" | battery answer (or no battery, said plainly) | P1 |
| S17 | "list my files" | the files shown | P0 |
| S18 | "where are my downloads" | the Downloads folder opens or is named | P0 |
| S19 | "make a folder called Test on my desktop" | folder exists on the desktop | P0 |
| S20 | "delete the folder Test" | removed (to the trash, said so) | P1 |
| S21 | "remind me in 5 minutes to stretch" | reminder set for 5 minutes from now | P0 |
| S22 | "set a timer for 2 minutes" | timer set, said plainly | P0 |
| S23 | "what did I say a minute ago" | answered from the conversation, no fabrication | P1 |
| S24 | "write a poem about the sea, four lines" | four lines | P1 |
| S25 | "translate thank you to french" | merci | P0 |
| S26 | "what's 15 percent of 240" | 36 | P0 |
| S27 | "convert 10 kilometres to miles" | about 6.2 miles | P0 |
| S28 | "who is the prime minister of the uk" | a name, with the date caveat if needed | P1 |
| S29 | "search the web for the best free text editor" | results shown | P0 |
| S30 | "open youtube" | youtube opens | P0 |
| S31 | "play some music" | music plays | P0 |
| S32 | "pause the music" | paused (state kept between requests) | P0 |
| S33 | "what's on my screen" | a description of the windows and text | P1 |
| S34 | "take a screenshot" | a screenshot saved and shown | P0 |
| S35 | "lock the screen" | locked | P0 |
| S36 | "unlock the screen" | unlocked with the test passphrase | P0 |
| S37 | "turn wifi off" | wifi off, or says no wifi adapter | P1 |
| S38 | "show my email" | the inbox or the mail window | P0 |
| S39 | "do I have new email" | count and senders | P0 |
| S40 | "send craig@localhost an email saying hello" | sent to craig@localhost | P0 |
| S41 | "make a note that the door code is 1234" | saved in notes | P0 |
| S42 | "what's in my notes" | the note | P0 |
| S43 | "add milk to my shopping list" | on the list | P0 |
| S44 | "what's on my shopping list" | milk | P0 |
| S45 | "open my shopping list" | the list window | P1 |
| S46 | "what's the date" | today's date | P0 |
| S47 | "install vlc" | installed, said plainly | P1 |
| S48 | "help" | how to use it, short | P0 |
| S49 | "thanks" | a short reply, nothing done | P0 |
| S50 | "stop" | nothing running is stopped, said plainly | P1 |
