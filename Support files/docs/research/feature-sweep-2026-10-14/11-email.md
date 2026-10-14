# 11 email

## Task
Use email like a normal person: check mail, open the newest message, summarize unread mail, send an email to
jordan@localhost, check it arrived, reply to a message, delete one message.

## Verdict
PARTLY. Check mail, open newest (by typing), send, arrival and reply worked. Opening by clicking Read, summarizing
unread mail, and deleting failed. Every failure ended in a "couldn't finish" message after the assistant ran a
string of shell searches (find /, cat /var/mail, ls /var/spool/mail) that a person would never see or want.

## Steps
Times are from the reply line of `waitreply` unless noted. Screenshots are in run/sweep/shots/.

1. Starting state (11-start.png): desk with a "While you were away" window already open. Left it as found.
2. Say "check my email". Reply in 2 s. Showed "Inbox · 6" with 6 rows (Bob Martinez, Deals Deals, Dr. Patel's Office,
   GitHub, Weekly Digest, Alice Chen), Read and Archive buttons on each, and an "Inbox zero" button.
   Expected: the list. Got the list. Chat reply says "6 unread emails: ... ...." and "They're listed on the screen."
   Reply text is cut off with "...." after three items (11-check-email.png).
3. Click the subject "Invoice for the deck repair" (row text). Nothing opened. Chat only changed to the previous reply.
   Expected: the message opens. (11-open-newest.png)
4. Click the Read button on the top row (click 696 155). Chat showed "You read email 6", then 30 s later:
   "You used 'mutt'; it exited with code 0". A terminal window ran mutt and showed
   "/root/Mail does not exist. Create it? ([yes]/no):" (11-read-result.png). I typed "no" and Enter. Mutt then
   opened with "(no mailbox) [Msgs:0]" and no mail (11-mutt-prompt-no.png). Pressed q to quit. Expected: the
   message opens in the Inbox window.
5. Say "open my newest email". Reply in 2 s: "From Bob Martinez: 'Invoice for the deck repair'. Hi, attached is the
   invoice ... $850. Can you pay by the 30th? Thanks, Bob". A window opened with From, Date, body, a "Reply to Bob
   Martinez" box, Send reply, Archive and Delete (11-open-newest-say.png). This is the path that works.
6. Say "summarize my unread emails" (43 s): "I couldn't finish that." The chat log shows the assistant running
   `ls /usr/sbin/ | grep mail`, `mailx -n`, `find / -name "mail"`, `ls -la /var/spool/mail`, `cat /var/mail`, then
   "Stopped." (11-summarize.png). Retried with "summarize the unread emails in my inbox" (48 s) and
   "what are my unread emails about" (35 s): same failure (11-summarize-2/-3.png).
7. Say "email jordan@localhost saying the sweep test works". Reply in 2 s: "Sent to jordan@localhost". No
   confirmation was asked for. Chat shows "email: send jordan@localhost". The body text was not shown anywhere
   (11-send.png).
8. Say "check my email". Reply in 2 s: "6 unread emails: jordan (The sweep test works); ...". The message arrived.
   The sender shows as just "jordan" (11-check-after-send.png). Rows now: jordan, Deals Deals, Dr. Patel's Office,
   GitHub, Weekly Digest, Alice Chen. Bob's invoice dropped out of the unread list because it was opened in step 5; the count stayed at 6.
9. Say "reply to jordan's email saying got it, thanks" (2 s): "Sent: jordan@localhost (Re: The sweep test works)"
   (11-reply.png). No confirmation asked. The reply text is not shown anywhere.
10. Say "delete the email from jordan, the sweep test" (35 s): "I couldn't finish that." Same run of shell searches
    (find ~/Mail -name "*sweep test*", etc.) (11-delete.png). Not deleted.
11. Say "open the email from jordan" (35 s): "I couldn't finish that." (11-open-jordan.png). Clicking the row text
    "The sweep test works" (click 300 232) did nothing (11-click-jordan-row.png).
12. Opened Bob's invoice (from step 5). Clicked its red Delete button (205 462). Chat showed "You delete email 6",
    thinking for 30 s, then "I couldn't finish that." with shell searches in /var/mail (11-delete-click.png,
    11-delete-result.png). The message is still there.
13. Say "delete this email" (2 s): "Which file? Say its name (for example 'delete recipe.pdf')..."
    (11-delete-say.png). It treated email as files.
14. Say "delete the email titled Invoice for the deck repair" (41 s): "I couldn't finish that." (11-delete-say2.png).
    I stopped trying here. Nothing was deleted, so no message is lost.
15. Cleanup: closed the invoice window, the Inbox window and the reply panel. Closed the leftover "mutt" chip at the
    bottom left. The desk is back to "While you were away" only (11-cleanup.png, 11-final.png).

Totals: check mail 2 s each time, send 2 s, reply 2 s. Failed requests 30 to 48 s. Summary and delete tries
35 to 48 s each.

## Bugs
- **Read button opens mutt, not the message.** Clicking Read on the top row (click 696 155) sent "read email 6".
  Result: a terminal ran mutt and asked "/root/Mail does not exist. Create it? ([yes]/no):". With no mailbox
  it showed "(no mailbox) [Msgs:0]". Should: open the message in a window like "open my newest email" does.
  Also, the mail client runs as root, and asks a question a person can't answer.
- **Delete button and "delete" wording fail.** Red Delete on the open message sent "delete email 6"; nothing was
  deleted. "delete the email from jordan, the sweep test", "delete the email titled ...", and "delete this email"
  all failed. The last one asked "Which file?". Should: delete the open message, or ask "which email?" with the list.
- **Summarize unread mail fails.** "summarize my unread emails", "summarize the unread emails in my inbox" and
  "what are my unread emails about" all failed. The assistant ran shell searches (find /, cat /var/mail, mailx -n).
  It had just read the mail with the mail tool. Should: list the six unread messages with a one-line summary each.
- **Open by name fails.** "open the email from jordan" failed. "open my newest email" worked. Clicking subject text
  or the row does nothing.
- **Failed requests search the whole computer.** Every failure ran find / and shell commands over /var/mail and
  ~/Mail, for 30 to 48 s, then said "I couldn't finish that." The person sees a long list of internal commands in
  the chat. Should: say what it could not do after one or two tries.
- **Sent without confirmation or showing the text.** "email jordan@localhost saying the sweep test works" sent in 2 s.
  Nothing showed the body, or asked to confirm. The same for the reply. A person can't see what was sent.
- **Reply on the list cut off.** "check my email" ends the list with "...." after 3 of 6 items, then says "They're
  listed on the screen." Reads as unfinished.
- **Inbox window does not update.** After the reply and delete failures, "Inbox · 6" count and rows stayed as shown.
  After opening Bob's message, his row left the list but the count stayed 6 (the new jordan message replaced it).
- **"Inbox zero" button** sits under a list of six unread messages. Confusing.
- **Leftover chip.** The "mutt" chip stayed at the bottom left after mutt exited. I closed it with its x.

## Friction
- Clicking a message's row text does nothing. Only the Read button or the typed request works.
- Read and Delete buttons send their request to the chat as "read email 6" / "delete email 6". The chat shows
  "thinking" for 30 s. A person sees this as the button doing nothing.
- Four different ways to ask for the same email (click, say, Read, Delete) give four different results.
- The "Read" action gives a terminal prompt that a person cannot answer correctly.
- Chat reply for "check my email" shows only the first 3 items, then "...." (see Bugs).
- Message from jordan shows sender "jordan", not an address.

## Ideas
- Make the Read and Delete buttons call the same code as "open my newest email" and "delete this email" for the
  open message, not the shell.
- Show the sent body in the chat reply ("Sent to jordan@localhost: 'The sweep test works'") so a person can check it.
- When a request fails, skip the shell searches and say what it tried in one line.
- List all unread messages with a one-line summary when asked to summarize.
- Ask "which email?" with the list on screen when the target is unclear.
