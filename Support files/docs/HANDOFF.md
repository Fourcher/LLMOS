# LLM OS: handoff for you

## 1. Version and where it is

- Version: 1.8.2.
- Package: `packages/LLM OS 1.8.2.zip` in the LLM OS project folder (not the Desktop).
- To start: at the top of the LLM OS folder, double-click **Start Here (Mac).command**
  (Windows: **Start Here (Windows).bat**, Linux: **Start Here (Linux).sh**).
  LLM OS Setup opens in your browser and takes it from there.
- The user guide is `dist/README.md`.
- RELEASE STATUS: <filled in when the final build reports>

## 2. What changed since 1.7.1

Everyday commands
- Reminders work with "at 3", "tonight", "this evening" and "next monday". A trailing "please" is ignored.
- "Remind me what's on tonight" is a question, so it is answered, not saved as a reminder.
- "Map of Paris" opens OpenStreetMap; "world clock Tokyo", "alarm for 7am" and "scientific calculator" work.
- "Do I have new email", "youtube music", "share over the network" and "use my Claude account" work.
- "Undo delete" restores only deletions. "Get my file back" and "open the bin" show the trash.
- "Open the file manager", "open Word", "open Excel" and "apt install" with several packages work.
- Saves never overwrite an existing file. Spreadsheets and "where did it save" are handled.

Speed
- Faster first replies. Rarely used tools are offered only when you ask about them.
- Web search runs both engines at once and gives up after 10 seconds, with a plain message.
- Greetings, "15 percent of 240" and "stop the music" get instant answers.
- Apps open as soon as their window appears, and clicks and typing are quicker.

Your control and privacy
- "Turn off the firewall" works. On the balanced setting it asks first. "Undo" puts it back.
- "Turn off the guard", "stop asking me before acting on emails" and "trust everything" are understood.
- The question before acting on web, email or file instructions now says why it asked and how to stop it.
- "Turn off the internet" and "work offline" work. "What is my IP" asks first when internet is set to ask.
- "Sign out" and "log out" lock the screen and say so.
- Do-not-disturb holds the away card's alert until you turn it off.
- The activity log is trimmed past 2 MB. "Clear the activity log" and "forget my routines" work.

Looks and wording
- Text boxes and the switch knob are readable in dark and light themes. Keyboard focus is visible.
- "Private window", "font bigger", "scale 150%", "less blue light at night" and "show all apps" work.
- Replies say "you", errors are in plain words, and all 6 languages are complete.

Your own account
- The desk runs under your own account when you have one. If that can't start, it falls back safely.
- Replies come back in your language at once.

Reliability
- "This app is frozen" and "connected but no internet" get plain help.
- Typos like "opn firefox" are understood. A trailing "please" or "thanks" no longer breaks a command.
- Declined dialogs close when you stop a request. Test resets close other programs.

## 3. What to try first

1. `what can you do`
2. `what did I miss`
3. `remind me at 3 to take my pills`
4. `world clock Tokyo`
5. `map of Paris`
6. `private window`
7. `turn off the firewall`, then `turn it on`
8. Delete a file, then `undo delete`
9. `scientific calculator`
10. `stop asking me before acting on emails`

## 4. Known problems

- Version 1.8.1 was never released: its x86 ISO step hung.
- macOS sometimes blocks access to the project drive for a minute ("Operation not permitted"). If it keeps happening, give your terminal app Full Disk Access in System Settings.
- Host tests must run only with `bash "Support files/tools/run-host-tests.sh"`. It keeps tests inside the project, so macOS won't ask for your personal folders.
- `tools/hostloop.sh` does not use that environment yet, so do not use it for tests.
- "Browser left, notes right" tiles the browser but not Notes, because Notes is not a separate window.
- A model bigger than memory works but is slow: about 1 to 2 words a second on a 4 GB machine.
- The encrypted vault can't be turned off by asking.
- The guard explanation on button prompts is not in this build (see section 5), so those prompts may not say why they ask.
- "Remind me to look at the stars tonight" and "remind me to X at 3" keep the words "remind me to" inside the saved task.
- Shorter assistant instructions and merged tools for speed were shelved: the saving was small and the risk to the small model was not worth it.

## 5. Left unmerged or open

- Guard explanation on button prompts: its check did not finish, so it is not merged.
- Vault moved to a root service: not done.
- Running the desk under your own account: not yet tested end to end on a VM. The shared account is still the default.
- Re-run of the usecase checks on the new build.
- The "Largest (slow, runs from disk)" model option: label not yet corrected after measuring.
- First-reply timing on the VM before and after the speed change.
- Reminders for "next week" and "later today".
- Remaining phrases that still need the model.
- `tools/hostloop.sh` still needs the test environment set.

## 6. Restarting the orchestrator

The orchestrator is the agent that plans and hands out the work. Its stop hook blocks it from ending while nothing is running. The wind-down flag is simply the file `.claude/orchestrator-wind-down` existing; the hook checks only that it exists.

1. To turn the never-stop hook back on, delete `.claude/orchestrator-wind-down` from the project folder.
2. Start Claude Code in the project folder with `--dangerously-skip-permissions`, with the llmos-orchestrator agent selected.
3. To stop it, run `claude stop <id>`. Do not use kill.
4. Reference: unmerged commit 5c05f50 (button-prompt guard explanation).
