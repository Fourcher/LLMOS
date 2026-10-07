# Everyday experience: normal requests, phrased the way people say them

The test for each row is the owner's: it gets done, at once if it can be, with no refusal, no questions back when a
sensible default exists, and no lecture. The success column says what must be true afterwards. Typos and two-part
requests are on purpose. Run with `tools/usecase-run.py --file docs/research/everyday-experience.md --yes M03,M04,M05,G07 --out run/everyday`
(VM only). The --yes list accepts the confirmations for sending mail and installing a program, which the owner would
say yes to. Power (sleep, restart, shut down) is not in this set: the harness skips those, and they are tested on their own. Results are graded by tools/ux-grade.py for refusals, questions back, lectures, empty replies and slowness,
then read by hand.

| ID | Request | What must be true afterwards | P |
|---|---|---|---|
| T01 | "what time is it" | the time, straight away | P0 |
| T02 | "what's today's date" / "what day is it" | today's date | P0 |
| T03 | "how's the weather today" / "wats the weather" | today's forecast here, straight away | P0 |
| T04 | "should I bring an umbrella tomorrow" | yes or no, with the chance of rain | P0 |
| T05 | "what's in the news" | a few headlines and where they're from | P1 |
| T06 | "who won the game last night" | answered from a web search, or says it couldn't find out; no refusal | P1 |
| T07 | "what's the capital of australia" | Canberra, from knowledge, no search | P0 |
| T08 | "how tall is mount everest" | about 8,849 m | P0 |
| T09 | "convert 3 cups to ml" | about 709 ml | P0 |
| T10 | "what's an 18 percent tip on 46 dollars" | the tip (8.28) and the total (54.28) | P0 |
| T11 | "how many days until next friday" | a number, and the date | P1 |
| T12 | "what's the time in london" | London's time | P0 |
| F01 | "where did I put my passport scan" | the file, or says none is there; no question back | P0 |
| F02 | "open my downloads" | the Downloads window | P0 |
| F03 | "make a folder called Receipts on my desktop" | the folder exists | P0 |
| F04 | "move the screenshots from my desktop into pictures" | they are in Pictures; the count is said | P0 |
| F05 | "rename my resume to Jordan resume 2026" | renamed, or it names the one file it means (once) | P1 |
| F06 | "copy my passport scan to my usb stick" | copied, or says no stick is plugged in and what to do | P1 |
| F07 | "what's taking up the most space on my computer" | the biggest things, with sizes | P0 |
| F08 | "show my biggest files" | a list with sizes | P1 |
| F09 | "find my tax papers from last year" | the matches, or says there are none; no question back | P0 |
| F10 | "open the pdf I downloaded today" | the newest pdf opens | P0 |
| F11 | "zip up my pictures" | a zip of Pictures exists | P1 |
| W01 | "open youtube" | youtube opens | P0 |
| W02 | "search for the best budget headphones" | results shown | P0 |
| W03 | "find me a recipe for banana bread" | a recipe or search results; no refusal | P0 |
| W04 | "is paypal down right now" | checks, and says what it found | P1 |
| W05 | "what time does the post office close" | an answer from search, or says it couldn't find one | P1 |
| W06 | "open the wikipedia page about the moon" | that page opens | P0 |
| M01 | "do I have any new email" | the count and who it is from | P0 |
| M02 | "is there an email from my landlord" | that email, or that there is none | P0 |
| M03 | "send craig@localhost an email saying I'll be ten minutes late" | sent to craig@localhost | P0 |
| M04 | "reply to the last email saying thanks, sounds good" | a reply sent to the newest email | P1 |
| M05 | "email my resume to craig@localhost" | sent with the file, or says which resume it means | P1 |
| A01 | "play some relaxing music" | music plays | P0 |
| A02 | "pause the music" | paused | P0 |
| A03 | "skip this song" | the next track plays | P0 |
| A04 | "turn the volume up" | one step louder | P0 |
| A05 | "mute the sound" | muted | P0 |
| A06 | "unmute" | sound back | P0 |
| A07 | "how loud is it right now" | the level | P1 |
| A08 | "play the newest video in my videos" | that video plays | P1 |
| S01 | "turn on dark mode" | dark mode | P0 |
| S02 | "make the text bigger" | bigger text | P0 |
| S03 | "turn the brightness up" | brighter (or says honestly that this machine has no backlight) | P0 |
| S04 | "turn on night light" | warmer screen | P0 |
| S05 | "stop the notifications for an hour" | do not disturb for an hour | P1 |
| S06 | "lock the screen after 10 minutes" | auto-lock after 10 minutes | P0 |
| S07 | "make the mouse faster" | faster pointer | P0 |
| S08 | "turn bluetooth on" | bluetooth on | P1 |
| S09 | "connect to wifi" | the networks are shown | P0 |
| S10 | "change the time zone to london" | London's zone | P0 |
| S11 | "what's my ip address" | the address | P1 |
| S12 | "change the wallpaper to a picture of mountains" | a mountain wallpaper | P0 |
| S13 | "make it look like windows 7" | the taskbar layout | P1 |
| S14 | "switch to the 24 hour clock" | 24-hour time | P1 |
| S15 | "turn the screen off after 5 minutes" | blanking after 5 minutes | P1 |
| D01 | "print this" | with nothing open: says what to open, once | P1 |
| D02 | "print my resume" | printed, or says there's no printer and how to add one | P1 |
| D03 | "add a printer" | the printers screen | P1 |
| D04 | "is my camera working" | a test result | P1 |
| D05 | "what's plugged into my computer" | the devices | P1 |
| C01 | "write a birthday message for my mum" | a short message | P0 |
| C02 | "tell me a joke" | a joke | P0 |
| C03 | "write a thank you note to my neighbour for watering my plants" | a short note | P0 |
| C04 | "translate good luck to spanish" | buena suerte | P0 |
| C05 | "what does serendipity mean" | a definition | P0 |
| C06 | "give me five ideas for dinner with chicken and rice" | five ideas | P0 |
| C07 | "write a message to my boss saying I'm sick today" | the message | P0 |
| C08 | "explain a vpn in simple words" | a plain explanation | P1 |
| C09 | "what's a good name for a golden retriever puppy" | some names | P1 |
| C10 | "summarize this: the meeting moved to three on friday and bring the report" | a one-line summary | P1 |
| N01 | "remind me to call the dentist at 2pm" | reminder at 14:00 | P0 |
| N02 | "add eggs and milk to my shopping list" | both on the list | P0 |
| N03 | "what's on my shopping list" | the items | P0 |
| N04 | "remind me to take my medicine every day at 8am" | a daily reminder at 08:00 | P0 |
| N05 | "make a note that the wifi password is in the blue folder" | the note is saved | P0 |
| N06 | "what did I write in my notes" | the notes | P0 |
| N07 | "remind me in 20 minutes to check the bread" | a reminder in 20 minutes | P0 |
| N08 | "set a timer for 15 minutes for the pasta" | a 15-minute timer | P0 |
| N09 | "cancel the dentist reminder" | removed | P1 |
| G01 | "open the calculator" | opens | P0 |
| G02 | "open the calendar" | opens | P0 |
| G03 | "open my email" | the mail (or webmail) opens | P0 |
| G04 | "open the text editor" | opens | P0 |
| G05 | "open the terminal" | opens | P0 |
| G06 | "close firefox" | closed | P0 |
| G07 | "install vlc" | installed (it may take minutes) | P1 |
| G08 | "open the photo viewer" | opens | P1 |
| G09 | "what apps do I have" | the list | P1 |
| G10 | "make me a simple to-do app" | made and opened | P1 |
| H01 | "what can you do" | a short list of what it can do | P0 |
| H02 | "how do I take a screenshot" | the way to do it, in one or two lines | P0 |
| H03 | "my computer is really slow" | checks what is busy and says what to close | P0 |
| H04 | "the screen froze" | what to do, straight, no lecture | P0 |
| H05 | "I can't hear anything" | checks, and fixes it or says what's wrong | P0 |
| H06 | "the internet isn't working" | checks, and says what it found | P0 |
| H07 | "my mouse stopped working" | checks, and says what to try | P1 |
| H08 | "how much battery is left" | the battery answer | P0 |
| H09 | "how do I copy and paste" | how, in one or two lines | P0 |
| K01 | "what's on my calendar today" | says no calendar is connected, and how to add one | P0 |
| K02 | "add dentist to my calendar on friday at 2pm" | a reminder on Friday at 14:00 | P0 |
| X01 | "opn firefox" | Firefox opens | P1 |
| X02 | "chang the volum up" | volume up | P1 |
| X03 | "hwo do i print" | how, in one or two lines | P1 |
| X04 | "wat time is it" | the time | P1 |
| X05 | "remindme to feed the cat at 6" | a reminder at 18:00 | P1 |
| Y01 | "turn on dark mode and make the text bigger" | both done | P0 |
| Y02 | "open my email and play some music" | both done | P0 |
| Y03 | "what time is it and what's the weather" | both answered | P1 |
| Y04 | "thanks" | a short friendly reply; nothing done | P0 |
| Y05 | "yes" | nothing pending, so a short reply saying so; nothing done | P1 |
