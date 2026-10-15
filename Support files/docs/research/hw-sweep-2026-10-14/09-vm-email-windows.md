# 09 VM email and windows (2026-10-14)

## Task
Part A: email (check, read, reply, summarize, delete, send, check again).
Part B: windows (Settings, Files, Lists together; drag, minimize and restore from the bottom dock, maximize and restore, close with X; five windows then "close all windows").

## Verdict
- Part A (email): **BROKEN**
- Part B (windows): **PARTLY** (window handling works; overlap and transparency problems; "close all" closed a window I had not opened)

## Steps

### Part A: email
| # | Said / did | Expected | What happened | Time | Screenshot |
|---|---|---|---|---|---|
| A1 | "check my email" | List of inbox messages | "IMAP login to 127.0.0.1 failed: the other side isn't answering." | 2 s | run/sweep/shots/email1.png |
| A2 | Clicked Close, then "show my inbox" (second wording) | Inbox | Same IMAP error | 2 s | run/sweep/shots/email2.png |
| A3 | Opened the Apps grid (top bar grid button) | A Mail app | No Mail app. Apps are Calculator, To-do, and the programs AbiWord, Archive manager, Files, Firefox, Gnumeric, Image viewer, Terminal, Text editor. There is a "Connectors (add abilities)" button. | - | run/sweep/shots/apps1.png |
| A4 | "summarize my unread emails" | Summary of unread mail | Same IMAP error | 5 s | run/sweep/shots/pa-summarize_my.png |
| A5 | "delete the first email" | First email moved to trash, and say so | Nothing deleted. Reply "/var/mail is empty." and a Files window titled /var/mail opened showing an empty folder. | 14 s | run/sweep/shots/pa-delete_the_f.png |
| A6 | "send an email to jordan@localhost with subject Test and say hello" | Message sent and delivered to the inbox | Reply "Email sent to jordan@localhost with subject "Test" and message "hello"." Mail is not delivered (see Bugs). | 47 s | run/sweep/shots/pa-send_an_emai.png |
| A7 | "check my email" again, to see the test mail | Test mail listed | Same IMAP error | 2 s | run/sweep/shots/checkmail2.png |
| A8 | "reply to it saying thanks, I'll be there" | A reply sent to the first message | Did not send an email. Replied in chat: "Thanks, Jordan! I'll be here whenever you need me." No message was open, so there was nothing to reply to. | 14 s | run/sweep/shots/a-reply.png |

Not done: "open a message with its Read button". No message list ever appeared, so there was no Read button to press.

VM check (read-only): the test mail is queued at /var/spool/postfix/maildrop/C23CDC0052. It is addressed to jordan@localhost, Subject: Test, body: hello, dated 23:56:00. Nothing listens on TCP 143 (IMAP) inside the VM; only 127.0.0.1:631 and 127.0.0.1:8080 are listening. No postfix master or dovecot process is running. /var/mail is empty.

### Part B: windows
| # | Action | Expected | What happened | Time | Screenshot |
|---|---|---|---|---|---|
| B1 | "open settings" | Settings window | Opened ("Here it is.") | 2 s | run/sweep/shots/b-settings.png |
| B2 | "show my files" | Files window | Opened as a window titled "Home" listing Apps, Documents, Downloads, Music, Pictures, Videos | 2 s | run/sweep/shots/b-files.png |
| B3 | "show my lists" | Lists window | Opened, "(nothing on this list)" | 2 s | run/sweep/shots/b-lists.png |
| B4 | Drag Lists by its title bar from (720,149) to (420,469) | Window moves | Moved to the new spot | - | run/sweep/shots/b-drag.png |
| B5 | Minimize Settings (button at 1162,89) | Window goes to dock | Became a "Settings" chip at bottom left (58,756) | - | run/sweep/shots/b-min.png |
| B6 | Click the "Settings" chip | Window comes back | Came back in front, at the same place | - | run/sweep/shots/b-restore.png |
| B7 | Maximize Settings (1197,89) | Full screen | Filled the screen | - | run/sweep/shots/b-max.png |
| B8 | Restore Settings (1205,77) | Same place as before | Back at x 701-1259, y 67-689, same as before maximizing | - | run/sweep/shots/b-restored.png |
| B9 | Close Settings, Lists and Home with their X buttons | Windows close | All three closed | - | run/sweep/shots/b-closed3.png |
| B10 | "open calculator", "open my to-do", "show my files", "open settings", "show my lists" | Five windows open | All five opened, each reply about 2-4 s. They overlap badly (see Friction). | 2 s each | run/sweep/shots/b-five.png |
| B11 | "close all windows" | All windows close | "Done." All windows closed, including "While you were away", which was already open when I started and which I did not open. | 4 s | run/sweep/shots/b-closeall.png |

End state: no windows open, no dialogs. The VM was not shut down, restarted or stopped.

## Bugs
1. **Email does not work at all (IMAP).** "check my email" and "show my inbox" and "summarize my unread emails" all answer "IMAP login to 127.0.0.1 failed: the other side isn't answering." Nothing listens on IMAP port 143 in the VM, and no mail daemon is running. Expected: the inbox list.
2. **Sent mail never arrives, but the computer says it was sent.** "send an email to jordan@localhost with subject Test and say hello" replied "Email sent to jordan@localhost..." after 47 s. The message is still in the Postfix maildrop, and Postfix is not running, so it was never delivered. Expected: the message is in the inbox, and "check my email" lists it. Also, a 47 s wait for a send that does not happen is long.
3. **"delete the first email" with no email opened a folder window.** The reply was "/var/mail is empty." and it opened a Files window at /var/mail. Expected: "There are no emails to delete" (no folder window), or, when there is mail, the email moves to trash and it says so.
4. **"reply to it saying thanks, I'll be there" was answered as chat.** It replied "Thanks, Jordan! I'll be here whenever you need me." and sent nothing. Expected: with no message open, it asks which email to reply to, or opens the inbox first.
5. **"close all windows" also closed "While you were away".** I did not open it, and it was already on screen when I started. Expected: close only the app windows, or ask first.
6. **Lists window is see-through.** When Lists sat over Home, the Home rows ("Pictures", "Videos") showed through its body. Expected: an opaque background.

## Friction
- Email is a dead end for a normal person: no Mail app in the Apps grid, and "Connectors (add abilities)" is the only related entry. Nothing says why email is unavailable.
- The Lists window opened in the middle of the screen over Home and covered most of it. Five windows opened at once land on top of each other and hide Calculator completely (it sits behind To-do). A person would need to drag windows around just to see what is open.
- Opening Files with "show my files" gives a window titled "Home" but the path button says "↑ /". The window name and the path do not agree.
- The "While you were away" panel is always on top of the left side of the desk, and it is closed by "close all windows" as well.
- The Settings chip in the dock is the only sign of a minimized window. It is small and easy to miss, but it works.
- Replies are quick for window requests (2 s) and slow for the send (47 s).

## Ideas
- Add a Mail app to the Apps grid, or say in the reply that email is not set up and how to set it up.
- Make "delete the first email" and "reply to it" say what they need when there is no open message, instead of acting on a folder or answering in chat.
- Make "send" wait for delivery before saying "sent", or say "queued" when it is not delivered.
- When a window opens, place it so it does not fully cover the others, or cascade new windows.
- Make "close all windows" skip the "While you were away" panel, or leave that panel alone.
- Make the Lists window background opaque.
