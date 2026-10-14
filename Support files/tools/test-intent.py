#!/usr/bin/env python3
"""Host-side unit test of the deterministic shortcuts in llmos/intent.py:
the handful of utterances the OS routes itself instead of trusting a small
model with. Run: python3 tools/test-intent.py  (no VM needed)."""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))   # the model catalog
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True      # the host has no lists; the VM checks the real store

CASES = {
    # 1.7.0: everyday wordings found by the use-case run and the XFCE parity check
    "music": ("play_media", {"query": "chill instrumental music mix"}),
    "play something": ("play_media", {"query": "chill instrumental music mix"}),
    "start a video call": ("browse", {"site": "https://meet.google.com/new"}),
    "play the video call song": None,
    "i deleted something by accident": ("show_files", {"path": "~/.Trash"}),
    "open the recycle bin": ("show_files", {"path": "~/.Trash"}),
    "install spotify": ("install_app", {"packages": "spotify"}),
    "i need zoom": None,
    "uninstall spotify": ("remove_software", {"name": "spotify"}),
    "unzip ~/Downloads/photos.zip": ("extract_archive", {"path": "~/Downloads/photos.zip"}),
    "edit the file ~/notes.txt": ("open_file", {"path": "~/notes.txt", "edit": True}),
    "print the file ~/a.pdf": ("print_file", {"path": "~/a.pdf"}),
    "print recipe.pdf": ("print_file", {"path": "recipe.pdf"}),
    "print 2 copies double sided": ("which_file", {"request": "print 2 copies double sided"}),
    "set ~/Pictures/beach.jpg as my wallpaper": ("set_wallpaper", {"subject": "~/Pictures/beach.jpg"}),
    "make a spreadsheet for my budget": ("make_spreadsheet", {"name": "Budget", "rows": [["Item", "Amount"], ["Rent", ""], ["Food", ""], ["Bills", ""], ["Other", ""], ["Total", "=SUM(B2:B5)"]]}),
    "make a spreadsheet": ("make_spreadsheet", {"name": "Spreadsheet", "rows": [["Item", "Amount"], ["", ""], ["Total", "=SUM(B2:B2)"]]}),
    "create a spreadsheet to track my plants": ("make_spreadsheet", {"name": "Plants", "rows": [["Item", "Amount"], ["", ""], ["Total", "=SUM(B2:B2)"]]}),
    "snip": ("screenshot", {"area": True}),
    "screenshot this window": ("screenshot", {}),
    "set my time zone to paris": ("change_setting", {"setting": "timezone", "value": "paris"}),
    "use dark mode": ("set_appearance", {"theme": "dark"}),
    "make browser dark": ("set_appearance", {"theme": "dark"}),
    "keep the screen on": ("change_setting", {"setting": "screen_off", "value": "never"}),
    "sleep after 30 minutes": ("change_setting", {"setting": "sleep_after", "value": "30"}),
    "closing the lid should do nothing": ("change_setting", {"setting": "lid", "value": "nothing"}),
    "do not disturb": ("change_setting", {"setting": "do_not_disturb", "value": "on"}),
    "turn on night light": ("change_setting", {"setting": "night_light", "value": "on"}),
    "change my password": ("set_passphrase", {}),
    "don’t turn off the screen": ("change_setting", {"setting": "screen_off", "value": "never"}),
    "show all my programs": ("manage_apps", {"action": "list"}),
    "sort by date": ("show_files", {"sort": "date"}),
    "show my biggest files": ("biggest_files", {"folder": "~"}),
    "show the biggest files on the computer": ("biggest_files", {}),
    "find the largest files on my computer": ("biggest_files", {}),
    "what's taking up the most space": ("biggest_files", {"folder": "~"}),
    "what's taking up space": ("biggest_files", {"folder": "~"}),
    "what's taking up space on my computer": ("biggest_files", {}),
    "find the biggest file in Downloads": ("biggest_files", {"folder": "~/Downloads"}),
    "what's the largest file in my documents?": ("biggest_files", {"folder": "~/Documents"}),
    "find the biggest file": ("biggest_files", {"folder": "~"}),
    "biggest files": ("biggest_files", {"folder": "~"}),
    "largest files in downloads": ("biggest_files", {"folder": "~/Downloads"}),
    "biggest files in my documents": ("biggest_files", {"folder": "~/Documents"}),
    "the biggest file was a movie": None,
    # recently saved files: the period the words name (last_saved since=...)
    "what was i working on yesterday": ("last_saved", {"since": "yesterday"}),
    "What Was I Working On Yesterday?": ("last_saved", {"since": "yesterday"}),
    "find the file i was working on yesterday": ("last_saved", {"since": "yesterday"}),
    "files i changed today": ("last_saved", {"since": "today"}),
    "what did i work on today": ("last_saved", {"since": "today"}),
    "recent files": ("last_saved", {"since": "week"}),
    "show recent files": ("last_saved", {"since": "week"}),
    "my recent files": ("last_saved", {"since": "week"}),
    "files from this week": ("last_saved", {"since": "week"}),
    "i was working yesterday on my car": None,
    "recent news": None,
    # open the newest saved file (last_saved open=true); with yesterday/today the window too
    "open my last file": ("last_saved", {"open": True}),
    "Open The Last File": ("last_saved", {"open": True}),
    "open the last file": ("last_saved", {"open": True}),
    "open the file I was just working on": ("last_saved", {"open": True}),
    "open the file i was working on": ("last_saved", {"open": True}),
    "reopen my last file": ("last_saved", {"open": True}),
    "reopen my last document": ("last_saved", {"open": True}),
    "open what I was working on yesterday": ("last_saved", {"open": True, "since": "yesterday"}),
    "open what i was working on today": ("last_saved", {"open": True, "since": "today"}),
    "delete the biggest files": None,
    "biggest files are slow": None,
    "send me the biggest file": None,
    "what's my biggest file": ("biggest_files", {"folder": "~"}),
    "show the largest files in my pictures folder": ("biggest_files", {"folder": "~/Pictures"}),
    "zip my documents folder": ("compress_files", {"path": "~/Documents"}),
    "zip these": ("which_file", {"request": "zip these"}),
    "make this a jpg": ("which_file", {"request": "make this a jpg"}),
    "save it as png": ("which_file", {"request": "save it as png"}),
    "convert ~/a.docx to pdf": ("convert_to_pdf", {"path": "~/a.docx"}),
    # convert a named file to a format: image -> edit_image save_as, pdf -> convert_to_pdf, audio/video -> convert_media
    "convert photo.png to jpg": ("edit_image", {"path": "photo.png", "save_as": "photo.jpg"}),
    "turn ~/Documents/report.docx into a pdf": ("convert_to_pdf", {"path": "~/Documents/report.docx"}),
    "make cat.webp a png": ("edit_image", {"path": "cat.webp", "save_as": "cat.png"}),
    "save notes.txt as a pdf": ("convert_to_pdf", {"path": "notes.txt"}),
    "convert \"my photo.png\" to jpeg": ("edit_image", {"path": "my photo.png", "save_as": "my photo.jpg"}),
    "convert ~/Music/song.wav to mp3": ("convert_media", {"files": ["~/Music/song.wav"], "to": "mp3"}),
    "convert this to jpg": ("which_file", {"request": "convert this to jpg"}),
    "turn this photo into a jpg": ("which_file", {"request": "turn this photo into a jpg"}),
    "save this as a pdf": ("which_file", {"request": "save this as a pdf"}),
    "change the wallpaper to beach.jpg": ("set_wallpaper", {"subject": "beach.jpg"}),
    "convert 5 miles to km": None,
    "convert 100 usd to eur": None,
    "turn the volume to 50": None,
    "make the text bigger": ("set_appearance", {"scale": "bigger"}),
    "convert my life to art": None,
    "photo.png to jpg": None,
    "put this on the desktop": ("which_file", {"request": "put this on the desktop"}),
    "rename notes.txt to todo.txt": ("rename_file", {"name": "notes.txt", "to": "todo.txt"}),
    "rename it to budget.xlsx": ("rename_file", {"name": "it", "to": "budget.xlsx"}),
    "call it Budget instead": ("rename_file", {"name": "it", "to": "Budget"}),
    "rename it to Budget": ("rename_file", {"name": "it", "to": "Budget"}),
    "rename it": ("which_file", {"request": "rename it"}),
    "summarize this doc": ("which_file", {"request": "summarize this doc"}),
    "read this pdf to me": ("which_file", {"request": "read this pdf to me"}),
    "split this pdf": ("which_file", {"request": "split this pdf"}),
    "sign this pdf": ("which_file", {"request": "sign this pdf"}),
    "call it budget.xlsx": ("rename_file", {"name": "it", "to": "budget.xlsx"}),
    "name it Taxes": ("rename_file", {"name": "it", "to": "Taxes"}),
    "is paypa1.com safe?": ("check_site", {"address": "paypa1.com"}),
    "delete all my files": ("delete_file", {"path": "~", "contents": True}),
    "change the font to arial size 14": ("set_appearance", {"font": "arial", "scale": "115"}),
    "full trust": ("change_setting", {"setting": "autonomy", "value": "hands-off"}),
    "ask me before risky things": ("change_setting", {"setting": "autonomy", "value": "balanced"}),
    "follow instructions in web pages too": ("change_setting", {"setting": "guard_untrusted", "value": "off"}),
    # email account spelled out -> every field passed through
    "set up my email: address jordan@localhost, password test, imap_host 127.0.0.1, imap_port 143, imap_ssl false, "
    "smtp_host 127.0.0.1, smtp_port 25, smtp_security none":
        ("mail_setup", {"address": "jordan@localhost", "password": "test", "imap_host": "127.0.0.1", "imap_port": 143,
                        "imap_ssl": False, "smtp_host": "127.0.0.1", "smtp_port": 25, "smtp_security": "none"}),
    "set up my email: address me@gmail.com, password abcd efgh ijkl mnop":
        ("mail_setup", {"address": "me@gmail.com", "password": "abcd efgh ijkl mnop"}),
    "Set up my email account: email bob@example.org, password hunter2, imap server imap.example.org port 993, "
    "smtp server smtp.example.org port 587, name Bob":
        ("mail_setup", {"address": "bob@example.org", "password": "hunter2", "imap_host": "imap.example.org",
                        "imap_port": 993, "smtp_host": "smtp.example.org", "smtp_port": 587, "name": "Bob"}),
    "configure email: user alice@fastmail.com pass s3cret smtp security ssl":
        ("mail_setup", {"address": "alice@fastmail.com", "password": "s3cret", "smtp_security": "ssl"}),
    "set up my email": None,
    "add my email address to the signature": None,
    "what's in my inbox?": None,
    # the look
    "make everything green with square corners": ("set_appearance", {"theme": "green", "corners": "square"}),
    "make everything purple": ("set_appearance", {"theme": "purple"}),
    "Make the background dark blue": ("set_appearance", {"background": "dark blue"}),
    "turn the text green, with rounded corners": ("set_appearance", {"color": "green", "corners": "rounded"}),
    "paint the background #112233": ("set_appearance", {"background": "#112233"}),
    "make the frames orange": ("set_appearance", {"accent": "orange"}),
    "square corners": ("set_appearance", {"corners": "square"}),
    "no sharp corners": ("set_appearance", {"corners": "rounded"}),
    "make everything default": ("set_appearance", {"theme": "default"}),
    "make everything bigger": ("set_appearance", {"scale": "bigger"}),
    "bigger text please": ("set_appearance", {"scale": "bigger"}),
    "make the text smaller": ("set_appearance", {"scale": "smaller"}),
    "zoom out": ("set_appearance", {"scale": "smaller"}),
    "normal text size": ("set_appearance", {"scale": "default"}),
    "make it cosier": None,
    "turn it off": None,
    "make everything faded": ("restyle", {"description": "make everything faded"}),
    # boring tasks: right and at once
    "write down: dentist on friday at 3": ("note_add", {"text": "dentist on friday at 3", "list": "notes"}),
    "show my notes": ("notes_show", {"list": "notes"}),
    "delete the note about the dentist": ("note_remove", {"item": "dentist", "list": "notes"}),
    "set a 3 minute timer": ("schedule_task", {"when": "in 3 minutes", "task": "3 minutes", "kind": "timer"}),
    "set an alarm for 7am": ("schedule_task", {"when": "7am", "task": "Alarm", "kind": "reminder"}),
    "what reminders do i have": ("manage_tasks", {"action": "list"}),
    "open todo.txt": ("open_file", {"path": "todo.txt"}),
    "make a text file called todo on my desktop": ("write_file", {"path": "~/Desktop/todo.txt", "content": "", "append": True}),
    "sort my downloads by newest": ("show_files", {"path": "~/Downloads", "sort": "date"}),
    "turn the volume down a bit": ("set_volume", {"delta": -10}),
    "make the screen a little dimmer": ("set_brightness", {"delta": -15}),
    "email craig@example.com saying the meeting moved to 3pm": ("mail_send", {"to": "craig@example.com", "subject": "The meeting moved to 3pm", "body": "The meeting moved to 3pm."}),
    "send craig@localhost an email saying hello": ("mail_send", {"to": "craig@localhost", "subject": "Hello", "body": "Hello."}),
    "send bob@example.org a quick email saying the report is ready": ("mail_send", {"to": "bob@example.org", "subject": "The report is ready", "body": "The report is ready."}),
    "send alice@fastmail.com an email that the meeting moved": ("mail_send", {"to": "alice@fastmail.com", "subject": "The meeting moved", "body": "The meeting moved."}),
    "shut the computer down at 11pm every night": ("schedule_task", {"when": "every night at 11pm", "task": "shut the computer down"}),
    "change the theme to dark": None,
    "set the display to sleep": None,
    "make a folder called projects in my home": ("make_folder", {"name": "projects", "where": "home"}),
    "make everything green?": None,
    "make the text larger please": ("set_appearance", {"scale": "bigger"}),
    "turn off animations": ("set_appearance", {"motion": "off"}),
    "turn the animations back on": ("set_appearance", {"motion": "full"}),
    "fewer animations": ("set_appearance", {"motion": "reduced"}),
    "reduce motion": ("set_appearance", {"motion": "reduced"}),
    "no animations please": ("set_appearance", {"motion": "off"}),
    "animations off": ("set_appearance", {"motion": "off"}),
    "full animations": ("set_appearance", {"motion": "full"}),
    "turn animations on": ("set_appearance", {"motion": "full"}),
    "are animations on?": None,
    "animate a cat walking": None,
    # memory
    "remember that I like short answers": ("remember", {"fact": "User like short answers"}),
    "my name is Jordan": ("remember", {"fact": "User's name is Jordan"}),
    "call me a taxi": None,
    "remember to buy milk": ("note_add", {"text": "buy milk", "list": "to-do"}),
    "what do you remember about me?": None,
    # scheduling
    "in 1 minute, tell me one real fact about the Moon": ("schedule_task", {"when": "in 1 minute", "task": "tell me one real fact about the Moon"}),
    "every morning at 8 give me the weather": ("schedule_task", {"when": "every morning at 8", "task": "give me the weather"}),
    "what time is it in 2 hours?": None,
    # media and windows
    "play some lofi hip hop": ("play_media", {"query": "lofi hip hop"}),
    "pull up a YouTube video of a lofi hip hop live stream and play it on the screen":
        ("play_media", {"query": "a lofi hip hop live stream"}),
    "play chess with me": ("browse", {"site": "https://lichess.org"}),
    "open a terminal window on the screen": ("open_app", {"command": "foot", "graphical": True}),
    "open the settings": ("show_panel", {"panel": "settings"}),
    "show me my scheduled tasks": ("show_panel", {"panel": "tasks"}),
    "open the models panel": ("show_panel", {"panel": "models"}),
    "show recent actions": ("show_panel", {"panel": "audit"}),
    "open the settings for the router": None,
    # photos and wallpapers
    "show me a photo of the Matterhorn": ("show_image", {"subject": "the Matterhorn"}),
    "Show me a picture of a red panda": ("show_image", {"subject": "a red panda"}),
    "use a photo of the Alps as my wallpaper": ("set_wallpaper", {"subject": "the Alps"}),
    "set my wallpaper to a photo of Kyoto in autumn": ("set_wallpaper", {"subject": "Kyoto in autumn"}),
    "remove the wallpaper": ("set_wallpaper", {"subject": "none"}),
    "show me a photo of what?": None,
    # models by spoken name (resolved against the catalog)
    "download gemma 4 e2b": ("manage_models", {"action": "download", "model": "gemma-4-e2b"}),
    "use gemma 4 e2b": ("manage_models", {"action": "use", "model": "gemma-4-e2b"}),
    "switch to ministral 8b": ("manage_models", {"action": "use", "model": "ministral-3-8b"}),
    "remove granite 3b": ("manage_models", {"action": "remove", "model": "granite-4.2-3b"}),
    "download gemma": None,
    "use the bathroom": None,
    "install htop": ("install_app", {"packages": "htop"}),
    # files and screenshots
    "show my files": ("show_files", {"path": "~"}),
    "where did it save": ("last_saved", {}),
    "where did that go": ("last_saved", {}),
    "where's the file you just made": ("last_saved", {}),
    "show my recent files": ("last_saved", {"since": "week"}),
    "open the document I've been working on": ("show_files", {"path": "~", "sort": "date"}),
    "open the file I’ve been working on": ("show_files", {"path": "~", "sort": "date"}),
    "find my report": ("find_files", {"query": "report"}),
    "open my downloads folder": ("show_files", {"path": "~/Downloads"}),
    "show me my files in ~/projects": ("show_files", {"path": "~/projects"}),
    "what's in ~/projects?": ("show_files", {"path": "~/projects"}),
    "take a screenshot": ("screenshot", {}),
    "open the file ~/Documents/notes.txt": ("open_file", {"path": "~/Documents/notes.txt"}),
    "delete the file /root/Downloads/report.pdf": ("delete_file", {"path": "/root/Downloads/report.pdf"}),
    "delete the folder Test": ("delete_file", {"path": "Test"}),
    "delete the file called notes.txt": ("delete_file", {"path": "notes.txt"}),
    "remove my folder old-stuff": ("delete_file", {"path": "old-stuff"}),
    "open the file cabinet": None,
    "show my files to Bob": None,
    "remove the folder ..": None,
    "remove the folder .": None,
    # lists, notes, trash
    "add milk to my shopping list": ("note_add", {"text": "milk", "list": "shopping"}),
    "put call the dentist on my to-do list": ("note_add", {"text": "call the dentist", "list": "to-do"}),
    "note that the plumber comes Tuesday": ("note_add", {"text": "the plumber comes Tuesday", "list": "notes"}),
    "show my shopping list": ("notes_show", {"list": "shopping"}),
    "what's on my to-do list?": ("notes_show", {"list": "to-do"}),
    "show my lists": ("notes_show", {}),
    "tick off item a1b2c3": ("note_done", {"item": "a1b2c3", "done": True}),
    "mark milk as done": ("note_done", {"item": "milk", "done": True}),
    "untick item a1b2c3": ("note_done", {"item": "a1b2c3", "done": False}),
    "remove milk from my shopping list": ("note_remove", {"item": "milk", "list": "shopping"}),
    "clear my shopping list": ("note_remove", {"item": "all", "list": "shopping"}),
    "add a list of numbers": None,
    "empty the trash": ("empty_trash", {}),
    "show the trash": ("show_files", {"path": "~/.Trash"}),
    "restore report.pdf from the trash": ("restore_file", {"name": "report.pdf"}),
    "put back notes.txt": ("restore_file", {"name": "notes.txt"}),
    # timers and reminders
    "set a timer for 10 minutes": ("schedule_task", {"when": "in 10 minutes", "task": "10 minutes", "kind": "timer"}),
    "timer 90 seconds": ("schedule_task", {"when": "in 90 seconds", "task": "90 seconds", "kind": "timer"}),
    "remind me in 20 minutes to stretch": ("schedule_task", {"when": "in 20 minutes", "task": "stretch", "kind": "reminder"}),
    "remind me in 1 hour": ("schedule_task", {"when": "in 1 hour", "task": "1 hour", "kind": "timer"}),
    "check my email": None,
    "check the weather every morning at 7": ("schedule_task", {"when": "every morning at 7", "task": "check the weather"}),
    "the build is done": None,
    "restore the default colors": None,
    "add go to the bank to my to-do list": ("note_add", {"text": "go to the bank", "list": "to-do"}),
    "note that I am vegetarian": ("remember", {"fact": "User is vegetarian"}),
    # auto-lock
    "lock after 10 minutes of inactivity": ("change_setting", {"setting": "autolock", "value": "10"}),
    "auto-lock after 1 hour": ("change_setting", {"setting": "autolock", "value": "60"}),
    "turn off auto-lock": ("change_setting", {"setting": "autolock", "value": "off"}),
    "never lock automatically": ("change_setting", {"setting": "autolock", "value": "off"}),
    "set up a passphrase": ("set_passphrase", {}),
    "encrypt my data": ("set_passphrase", {}),
    "protect my files with a password": ("set_passphrase", {}),
    "what's my password?": None,
    # brightness and volume
    "brightness 60": ("set_brightness", {"percent": 60}),
    "set the brightness to 80%": ("set_brightness", {"percent": 80}),
    "turn the screen down": ("set_brightness", {"delta": -15}),
    "brighter": ("set_brightness", {"delta": 15}),
    "volume 30": ("set_volume", {"percent": 30}),
    "turn the volume up": ("set_volume", {"delta": 10}),
    "change the volume up": ("set_volume", {"delta": 10}),
    "set the music up": ("set_volume", {"delta": 10}),
    "put the sound down": ("set_volume", {"delta": -10}),
    "quieter": ("set_volume", {"delta": -10}),
    "mute": ("set_volume", {"mute": True}),
    "unmute the sound": ("set_volume", {"mute": False}),
    "turn the sound off": ("set_volume", {"mute": True}),
    "is the volume up?": None,
    # a panel of the computer's own state
    "show me my disk, memory and scheduled tasks in one panel": ("system_panel", {"items": ["disk", "memory", "scheduled", "tasks"]}),
    "show me disk and battery in a window": ("system_panel", {"items": ["disk", "battery"]}),
    "system status": ("system_panel", {"items": []}),
    "show me my photos in one panel": None,
    # policies, language, power (exact meanings, never left to the model)
    "ask me each time before using the internet": ("change_setting", {"setting": "internet", "value": "ask"}),
    "turn the internet off": ("change_setting", {"setting": "internet", "value": "no"}),
    "no internet": ("change_setting", {"setting": "internet", "value": "no"}),
    "allow internet use": ("change_setting", {"setting": "internet", "value": "yes"}),
    "turn the internet back on": ("change_setting", {"setting": "internet", "value": "yes"}),
    "use tor": ("change_setting", {"setting": "tor", "value": "on"}),
    "route everything through tor": ("change_setting", {"setting": "tor", "value": "on"}),
    "stop using tor": ("change_setting", {"setting": "tor", "value": "off"}),
    "switch to hands-on mode": ("change_setting", {"setting": "autonomy", "value": "hands-on"}),
    "switch back to hands-off": ("change_setting", {"setting": "autonomy", "value": "hands-off"}),
    # where it thinks (the settings panel's phrases and natural variants) -> the brain setting / the online model
    "think only on this computer": ("change_setting", {"setting": "brain", "value": "local"}),
    "stop using the online model": ("change_setting", {"setting": "brain", "value": "local"}),
    "never use claude again": ("change_setting", {"setting": "brain", "value": "local"}),
    "ask me before going online for big tasks": ("change_setting", {"setting": "brain", "value": "ask"}),
    "ask me before using claude": ("change_setting", {"setting": "brain", "value": "ask"}),
    "use the online model for everything": ("change_setting", {"setting": "brain", "value": "cloud"}),
    "let claude do everything": ("change_setting", {"setting": "brain", "value": "cloud"}),
    "set up the online model": ("online_model", {"action": "set up"}),
    "connect my claude account": ("online_model", {"action": "sign in", "provider": "claude"}),
    # signing in (the connect panel's buttons say these): the service's key page opens, nothing to type
    "sign in to Claude": ("online_model", {"action": "sign in", "provider": "claude"}),
    "sign in to ChatGPT": ("online_model", {"action": "sign in", "provider": "chatgpt"}),
    "please log into my OpenAI account": ("online_model", {"action": "sign in", "provider": "chatgpt"}),
    "Log in with Anthropic.": ("online_model", {"action": "sign in", "provider": "claude"}),
    "connect to chat gpt": ("online_model", {"action": "sign in", "provider": "chatgpt"}),
    "connect another online service": ("online_model", {"action": "set up", "provider": "other"}),
    "sign in to my bank": None, "log into gmail": None, "connect to the wifi": None,
    "forget the online model": ("online_model", {"action": "forget"}),
    "ask me before using the internet": ("change_setting", {"setting": "internet", "value": "ask"}),   # still the internet rule
    # desk layouts (the settings panel's phrases and what the owner would say)
    "give me a clean desk": ("set_appearance", dict(intent._LAYOUT_PRESETS["clean"])),
    "give me a windows style desk": ("set_appearance", dict(intent._LAYOUT_PRESETS["windows"])),
    "give me a mac style desk": ("set_appearance", dict(intent._LAYOUT_PRESETS["mac"])),
    "I want a windows 7 clone desktop": ("set_appearance", dict(intent._LAYOUT_PRESETS["windows"])),
    "I want Mac OS Mojave": ("set_appearance", dict(intent._LAYOUT_PRESETS["mac"])),
    "make it look like a mac": ("set_appearance", dict(intent._LAYOUT_PRESETS["mac"])),
    "give me a traditional desktop": ("set_appearance", dict(intent._LAYOUT_PRESETS["windows"])),
    "back to the normal desk": ("set_appearance", dict(intent._LAYOUT_PRESETS["clean"])),
    "make it clean": None,                      # tidy up? a colour? not a layout without a desk word
    # online model: switch, set up, forget (do not collide with local "use <model>")
    "use the online model claude-opus-5-5": ("online_model", {"action": "use", "model": "claude-opus-5-5"}),
    "switch the online model to opus": ("online_model", {"action": "use", "model": "opus"}),
    "use claude haiku online": ("online_model", {"action": "use", "model": "claude haiku"}),
    "use gemma 4 e2b": ("manage_models", {"action": "use", "model": "gemma-4-e2b"}),   # still local
    "use the browser online": None,                 # "online" but not a known online model -> model decides
    # the agentic refresh + adding a Hugging Face repo
    "check for new models": ("check_new_models", {}),
    "check for new and updated models": ("check_new_models", {}),
    "refresh the model list": ("check_new_models", {}),
    "are there any newer models": ("check_new_models", {}),
    "add the model mistralai/Ministral-3-8B-Instruct-2512-GGUF": ("add_model", {"repo": "mistralai/Ministral-3-8B-Instruct-2512-GGUF"}),
    "add the model TheOrg/Some-Model-GGUF Some-Model-Q4_K_M.gguf": ("add_model", {"repo": "TheOrg/Some-Model-GGUF", "file": "Some-Model-Q4_K_M.gguf"}),
    # connectors (the apps of this OS)
    "show connectors": ("show_panel", {"panel": "connectors"}),
    "open the apps": ("manage_apps", {"action": "list"}),
    "open integrations": ("show_panel", {"panel": "connectors"}),
    "add a connector": ("manage_connectors", {"action": "add"}),
    "add a connector named weather that runs uvx mcp-server-weather": ("manage_connectors", {"action": "add", "name": "weather", "command": "uvx mcp-server-weather", "transport": "stdio"}),
    "add a connector named api at https://example.com/mcp": ("manage_connectors", {"action": "add", "name": "api", "url": "https://example.com/mcp", "transport": "http"}),
    "disable the connector weather": ("manage_connectors", {"action": "disable", "name": "weather"}),
    "enable the connector files": ("manage_connectors", {"action": "enable", "name": "files"}),
    "remove the connector weather": ("manage_connectors", {"action": "remove", "name": "weather"}),
    # conduct editor ("pop the hood" on the safety/conduct section)
    "edit the conduct": ("edit_conduct", {"action": "open"}),
    "edit the safety rules": ("edit_conduct", {"action": "open"}),
    "pop the hood": ("edit_conduct", {"action": "open"}),
    "customize the system prompt": ("edit_conduct", {"action": "open"}),
    "show me the conduct": ("edit_conduct", {"action": "open"}),
    "reset the conduct to default": ("edit_conduct", {"action": "reset"}),
    "reset the conduct": ("edit_conduct", {"action": "reset"}),
    # speech-to-text (voice) models
    "use the turbo voice model": ("manage_voice", {"action": "use", "model": "turbo"}),
    "download the turbo voice model": ("manage_voice", {"action": "download", "model": "turbo"}),
    "download the best speech model": ("manage_voice", {"action": "download", "model": "best"}),
    "switch to the small dictation model": ("manage_voice", {"action": "use", "model": "small"}),
    "remove the small voice model": ("manage_voice", {"action": "remove", "model": "small"}),
    "show the voice models": ("manage_voice", {"action": "list"}),
    "use gemma 4 e2b": ("manage_models", {"action": "use", "model": "gemma-4-e2b"}),   # still the language model
    "balanced mode": ("change_setting", {"setting": "autonomy", "value": "balanced"}),
    "ask before deleting things": ("change_setting", {"setting": "autonomy", "value": "balanced"}),
    "ask me before every change": ("change_setting", {"setting": "autonomy", "value": "hands-on"}),
    "don't ask me for permission": ("change_setting", {"setting": "autonomy", "value": "hands-off"}),
    "read your replies aloud": ("change_setting", {"setting": "speak_replies", "value": "on"}),
    "stop reading replies aloud": ("change_setting", {"setting": "speak_replies", "value": "off"}),
    "turn on focus mode": ("change_setting", {"setting": "focus_mode", "value": "on"}),
    "focus mode for 2 hours": ("change_setting", {"setting": "focus_mode", "value": "on", "minutes": 120}),
    "turn off focus mode": ("change_setting", {"setting": "focus_mode", "value": "off"}),
    "put everything in Chinese": ("set_appearance", {"language": "Chinese"}),
    "switch everything back to English": ("set_appearance", {"language": "English"}),
    "put the settings in Chinese but keep everything else in English": ("set_appearance", {"settings_language": "Chinese", "language": "English"}),
    "make everything purple": ("set_appearance", {"theme": "purple"}),
    "shut down the computer": ("system_power", {"action": "shutdown"}),
    "restart": ("system_power", {"action": "restart"}),
    "power off now": ("system_power", {"action": "shutdown"}),
    "turn off the lights": None,
    "ask me what I want": None,
    # replies need a mail account (none on the build host) -> model / no-account guard
    "reply to Alice that Friday at 7 works and I'll bring dessert": None,
    # review 2026-10-04: words after "speak", "use" or "switch to" are a language only when they name one
    "speak louder": None, "speak slower": None, "speak up": None, "use firefox": ("browse", {}), "switch to firefox": None,
    "use python": None, "use gemma": None, "talk to me in riddles": None, "put everything in bold": None,
    "speak spanish": ("set_appearance", {"language": "spanish"}),
    "speak in spanish": ("set_appearance", {"language": "spanish"}),
    "switch to german": ("set_appearance", {"language": "german"}),
    # the brief's own example, in the ways people say it; "settings in order" is not a language
    "settings in Chinese, rest in English": ("set_appearance", {"settings_language": "Chinese", "language": "English"}),
    "put the settings in Chinese and the rest of the OS in English": ("set_appearance", {"settings_language": "Chinese", "language": "English"}),
    "I want settings in Chinese and everything else in English": ("set_appearance", {"settings_language": "Chinese", "language": "English"}),
    "put the settings in order": None,
    # "no corners and everything to be rounded" (the brief): no corners means rounded
    "no corners": ("set_appearance", {"corners": "rounded"}),
    "make everything purple with no corners": ("set_appearance", {"theme": "purple", "corners": "rounded"}),
    # view wordings: bigger icons is icons; smaller icons has no safe mapping (leave it to the model)
    "bigger icons": ("show_files", {"path": "~", "view": "icons"}),
    "show them as icons": ("show_files", {"path": "~", "view": "icons"}),
    "show as a grid": ("show_files", {"path": "~", "view": "icons"}),
    "details view": ("show_files", {"path": "~", "view": "list"}),
    "smaller icons": None,
    # default app wordings with "by default" or "use X for Y"; a kind is required
    "open pdfs with evince by default": ("set_default_app", {"kind": "pdfs", "app": "evince"}),
    "use evince for pdfs": ("set_default_app", {"kind": "pdfs", "app": "evince"}),
    "open pdfs": None,
    "open firefox by default": None,
    # the app word must be a real program: no pronoun/determiner, 1-3 words
    "use my phone for music": None,
    "make me a playlist for videos": None,
    "use the default for pdfs": None,
    "use a different app for pdfs": None,
    "make it the default for videos": None,
    "make icons": None,
    "big icons are ugly": None,
}

bad = 0
for text, want in CASES.items():
    got = intent.match(text)
    if got != want:
        bad += 1
        print(f"MISMATCH {text!r}\n   got    {got}\n   wanted {want}")
print(f"intent shortcuts: {len(CASES) - bad}/{len(CASES)} as expected")

# an open app of the OS's own: close it, or read what it shows (the desk resolves the name to an installed app)
APP_CASES = {
    "close the calculator": ("close", "calculator"),
    "close the calculator app.": ("close", "calculator"),
    "quit my timer": ("close", "timer"),
    "close window": None,
    "close the window": None,
    "close all windows": None,
    "close this": None,
    "close the browser": None,                  # a program, not an app of the OS's: the old path
    "what does the calculator show": ("read", "calculator"),
    "What does the calculator show?": ("read", "calculator"),
    "what's on the calculator": ("read", "calculator"),
    "what is on my calculator?": ("read", "calculator"),
    "what's the calculator showing": ("read", "calculator"),
    "read the calculator": ("read", "calculator"),
    "what does it show": None,
    "what does the weather show": ("read", "weather"),
    "what time is it": None,
    "what's on the screen": None,
    "what's on the agenda": ("read", "agenda"),  # name-blind here: the desk finds no app called agenda and falls through
    "read this": None,
    "read the last answer": None,
}
app_bad = 0
for text, want in APP_CASES.items():
    got = intent.app_question(text)
    if got != want:
        app_bad += 1
        print(f"MISMATCH app_question {text!r}\n   got    {got}\n   wanted {want}")

# the reply: the display of the calculator (its labelled control), never a keypad label; generic apps: their text
calc_page = {"text": "7 + 2 =\n79\nC\n±\n%\n÷\n7\n8\n9\n×", "controls": ["display value: 79", "C", "±", "%", "÷", "7", "8", "9", "×"]}
REPLY_CASES = [
    ((calc_page, "Calculator"), "The calculator shows 79."),
    (({"text": "", "controls": ["display value: 9", "9", "="]}, "Calculator"), "The calculator shows 9."),
    (({"text": "0\nC\n7\n8\n9", "controls": ["display value: 0", "9"]}, "Calculator"), "The calculator shows 0."),
    (({"text": "Hello world\nSave", "controls": ["Save"]}, "Notes"), "The notes shows: Hello world Save."),
    (({"text": "", "controls": []}, "Notes"), "The notes shows nothing readable."),
    ((None, "Calculator"), "I could not read the calculator."),
    (({"none": True}, "Calculator"), "I could not read the calculator."),
]
reply_bad = 0
for (page, title), want in REPLY_CASES:
    got = intent.app_reading(page, title)
    if got != want:
        reply_bad += 1
        print(f"MISMATCH app_reading {title!r}\n   got    {got!r}\n   wanted {want!r}")
print(f"app questions: {len(APP_CASES) - app_bad}/{len(APP_CASES)} as expected; "
      f"readbacks: {len(REPLY_CASES) - reply_bad}/{len(REPLY_CASES)} as expected")

# typo fixes: common misspellings of command words are corrected before matching
TYPO_CASES = {
    "chang the volum up": "change the volume up",
    "opn firefox": "open firefox",
    "wat time is it": "what time is it",
    "remindme to feed the cat at 6": "remind me to feed the cat at 6",
    "what is the wattage": "what is the wattage",
    "Opn Firefox": "open Firefox",
    "join wifi Home password teh1234": "join wifi Home password teh1234",
    "send mum a message saying wat a day": "send mum a message saying wat a day",
    "set an alarm for 7 pls": "set an alarm for 7 pls",
    "join wifi teh-net": "join wifi teh-net",
    "rename the folder teh to docs": "rename the folder teh to docs",
}
tbad = 0
for text, want in TYPO_CASES.items():
    got = intent.fix_typos(text)
    if got != want:
        tbad += 1
        print(f"TYPO MISMATCH {text!r}\n   got    {got!r}\n   wanted {want!r}")
print(f"typos: {len(TYPO_CASES) - tbad}/{len(TYPO_CASES)} as expected")

# volume guards: "set it up" and "put it down" are not volume commands ("it" only follows turn/make)
GUARD_CASES = ["set it up", "put it down"]
gbad = 0
for text in GUARD_CASES:
    got = intent.match(text)
    if got and got[0] == "set_volume":
        gbad += 1
        print(f"GUARD MISMATCH {text!r}\n   got    {got!r}")
print(f"volume guards: {len(GUARD_CASES) - gbad}/{len(GUARD_CASES)} as expected")

# notes guards: "show my files as a list" and "show big icons" are not notes lists
NOTES_GUARD_CASES = ["show my files as a list", "show big icons"]
nbad = 0
for text in NOTES_GUARD_CASES:
    got = intent.match(text)
    if got and got[0] == "notes_show":
        nbad += 1
        print(f"NOTES GUARD MISMATCH {text!r}\n   got    {got!r}")
print(f"notes guards: {len(NOTES_GUARD_CASES) - nbad}/{len(NOTES_GUARD_CASES)} as expected")

# rename guards: "call it a day" and friends are not renames of "it"
RENAME_GUARD_CASES = ["call it a day", "call it a night", "call it quits", "let's call it even", "name it after my dog", "call it what you want instead"]
rbad = 0
for text in RENAME_GUARD_CASES:
    got = intent.match(text)
    if got and got[0] == "rename_file":
        rbad += 1
        print(f"RENAME GUARD MISMATCH {text!r}\n   got    {got!r}")
print(f"rename guards: {len(RENAME_GUARD_CASES) - rbad}/{len(RENAME_GUARD_CASES)} as expected")

# format guards: "make this bigger" and friends are not file conversions (the "which file" route is for formats only)
FORMAT_GUARD_CASES = ["make this bigger", "turn this off", "make it louder", "make it cosier", "make it look like a mac"]
fbad = 0
for text in FORMAT_GUARD_CASES:
    got = intent.match(text)
    if got and got[0] == "which_file":
        fbad += 1
        print(f"FORMAT GUARD MISMATCH {text!r}\n   got    {got!r}")
print(f"format guards: {len(FORMAT_GUARD_CASES) - fbad}/{len(FORMAT_GUARD_CASES)} as expected")

# doc guards: "read me a story" and friends are not file-document routes (the "which file" route is for "this <doc>" only)
DOC_GUARD_CASES = ["read me a story", "check my spelling", "translate this page", "summarize the news"]
dbad = 0
for text in DOC_GUARD_CASES:
    got = intent.match(text)
    if got and got[0] == "which_file":
        dbad += 1
        print(f"DOC GUARD MISMATCH {text!r}\n   got    {got!r}")
print(f"doc guards: {len(DOC_GUARD_CASES) - dbad}/{len(DOC_GUARD_CASES)} as expected")

# open-last guards: these must NOT open the newest saved file (last_saved open=true)
OPEN_LAST_GUARD_CASES = ["open my last email", "open the last tab", "open last week's photos folder", "what was my last file", "delete my last file"]
obad = 0
for text in OPEN_LAST_GUARD_CASES:
    got = intent.match(text)
    if got and got[0] == "last_saved" and got[1].get("open"):
        obad += 1
        print(f"OPEN LAST GUARD MISMATCH {text!r}\n   got    {got!r}")
print(f"open-last guards: {len(OPEN_LAST_GUARD_CASES) - obad}/{len(OPEN_LAST_GUARD_CASES)} as expected")
# default-app adversarial cases: the older phrasings keep their base behaviour (word shape only), the loose
# phrasings ("use X for Y", "open Y in X by default") need the program to be installed when a program menu exists.
# The host has no program menu, so the installed check is simulated with a temp folder holding only firefox.desktop.
import tempfile
from llmos import tools
_DA_SIM = {
    "always open pdfs in okular": ("set_default_app", {"kind": "pdfs", "app": "okular"}),
    "use okular for pdfs": None,
    "use firefox for web links": ("set_default_app", {"kind": "links", "app": "firefox"}),
    "use my phone for music": None,
}
_da_saved = tools.APP_DIRS
_da_dir = tempfile.mkdtemp(prefix="llmos-test-apps-")
with open(os.path.join(_da_dir, "firefox.desktop"), "w") as _f:
    _f.write("[Desktop Entry]\nName=Firefox\nExec=firefox\nType=Application\n")
dabad = 0
try:
    tools.APP_DIRS = [_da_dir]
    for text, want in _DA_SIM.items():
        got = intent.match(text)
        if got != want:
            dabad += 1
            print(f"DEFAULT APP MISMATCH {text!r}\n   got    {got!r}\n   wanted {want!r}")
finally:
    tools.APP_DIRS = _da_saved
    import shutil
    shutil.rmtree(_da_dir, ignore_errors=True)
print(f"default app (installed check): {len(_DA_SIM) - dabad}/{len(_DA_SIM)} as expected")
total = bad + app_bad + reply_bad + tbad + gbad + nbad + rbad + fbad + dbad + obad + dabad
if total:
    print(f"{total} FAILED")
else:
    print("all good")
sys.exit(1 if total else 0)
