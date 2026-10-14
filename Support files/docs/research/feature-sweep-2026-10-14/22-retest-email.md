# 22 retest-email

## Task
Retest the email fixes from 11-email.md: check mail, click Read on the top message, Delete it, summarize unread
mail, open the email from jordan, send to jordan@localhost and check it arrived. Leave the computer tidy.

## Verdict
PARTLY. Read now opens a message window with no terminal and no /root/Mail prompt. Delete, summarize and send
work, and the shell-search runs are gone. Still wrong: the open inbox window does not refresh after Delete, the
summary is still cut off after three items, and each request opens another inbox window.

## Steps
Times are the "took" line from `waitreply`. Screenshots are in run/sweep/shots/.

1. PASS. Say "check my email": reply in 2 s, Inbox · 6 opened with 6 rows (jordan, Deals Deals, Dr. Patel's Office,
   GitHub, Weekly Digest, Alice Chen). Shot 22-check.png.
2. PASS. Click Read on the top row (732 185). A message window "Re: The sweep test works" opened with From, Date,
   body, Reply box, Send reply, Archive and Delete. No terminal, no mutt, no "Create /root/Mail?" prompt. Shot 22-read.png.
3. PARTLY. Click Delete (241 548). Chat: "Moved 1 message(s) to Trash" in about 2 s, no error. The file is in
   /home/jordan/Maildir/.Trash. But the Inbox · 6 window behind the message still showed the jordan row and
   "Inbox · 6" after I closed the message. A fresh "check my email" showed 5 unread in a new Inbox · 5 window.
   Shots 22-delete.png, 22-delete-closed.png, 22-recheck.png.
4. PARTLY. Say "summarize my unread emails": answered in 2 s with no shell commands and no failure. Reply:
   "5 unread emails: Deals Deals (...); Dr. Patel's Office (...); GitHub (...) …. They're listed on the screen."
   It stops after three items. It is a list, not a summary. Opened another Inbox · 5 window. Shot 22-summarize.png.
5. PASS. Say "open the email from jordan": 2 s. Reply "From jordan: 'The sweep test works'. The sweep test works."
   Window "The sweep test works" opened with From, Date, body, Reply box, Archive and Delete. (The message deleted
   in step 3 is gone, so this opened an older message from jordan.) Shot 22-open-jordan.png.
6. PASS. Say "email jordan@localhost saying retest works": "Sent to jordan@localhost" in 2 s. The body is not shown
   in the reply. Say "check my email": 2 s, "6 unread emails: jordan (Retest works); ..." The message arrived.
   Shots 22-send.png, 22-arrived.png.

Tidy: closed every window I opened (the two stale Inbox windows, the message window and the extra Inbox windows).
Only "While you were away" is open, as at the start. Left the chat history card open.

## Bugs
- **Open inbox does not refresh after Delete.** Read, then Delete, then close: the Inbox · 6 window still lists the
  deleted message and says 6. Should: the open window drops the row and the count goes to 5. Only a new check shows it.
- **Every request opens a new inbox window.** "check my email", "summarize my unread emails" and the re-check each
  added an "Inbox" window, so the desk filled with stacked copies. Should: reuse or refresh the one window.
- **Summary is cut off.** "check my email" and "summarize my unread emails" both list 3 of 5 or 6 items, then
  "….", and say "They're listed on the screen." Should: a one-line summary per unread message (or all of them).
- **Send reply does not show the body.** "Sent to jordan@localhost" hides what was sent.

## Friction
- Reply text ends in "…." and reads unfinished.
- The message window and the inbox window overlap so that the inbox behind it looks as if Delete did nothing.
- "open the email from jordan" opened a different, older message from jordan (the one from step 5 of 11-email),
  because the deleted one was gone. Fine, but a person would not know which one they got.

## Ideas
- After Delete, refresh the open inbox window in place and show "Moved to Trash" as a small toast in that window.
- Reuse one Inbox window for every mail request.
- Summary: one line per unread message, all of them, no "…." cut-off.
- Show the body text in the sent confirmation.
