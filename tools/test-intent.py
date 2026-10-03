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

CASES = {
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
    "make everything green with square corners": ("set_appearance", {"color": "green", "accent": "green", "corners": "square"}),
    "make everything purple": ("set_appearance", {"color": "purple", "accent": "purple"}),
    "Make the background dark blue": ("set_appearance", {"background": "dark blue"}),
    "turn the text green, with rounded corners": ("set_appearance", {"color": "green", "corners": "rounded"}),
    "paint the background #112233": ("set_appearance", {"background": "#112233"}),
    "make the frames orange": ("set_appearance", {"accent": "orange"}),
    "square corners": ("set_appearance", {"corners": "square"}),
    "no sharp corners": ("set_appearance", {"corners": "rounded"}),
    "make everything default": ("set_appearance", {"color": "default", "accent": "default"}),
    "make everything bigger": ("set_appearance", {"scale": "bigger"}),
    "bigger text please": ("set_appearance", {"scale": "bigger"}),
    "make the text smaller": ("set_appearance", {"scale": "smaller"}),
    "zoom out": ("set_appearance", {"scale": "smaller"}),
    "normal text size": ("set_appearance", {"scale": "default"}),
    "make it cosier": None,
    "turn it off": None,
    "make everything faded": None,
    "change the theme to dark": None,
    "set the display to sleep": None,
    "make a folder called projects in my home": None,
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
    "play chess with me": None,
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
    "remove granite 3b": ("manage_models", {"action": "remove", "model": "granite-4.1-3b"}),
    "download gemma": None,
    "use the bathroom": None,
    "install htop": None,
    # files and screenshots
    "show my files": ("show_files", {"path": "~"}),
    "open my downloads folder": ("show_files", {"path": "~/Downloads"}),
    "show me my files in ~/projects": ("show_files", {"path": "~/projects"}),
    "what's in ~/projects?": ("show_files", {"path": "~/projects"}),
    "take a screenshot": ("screenshot", {}),
    "open the file ~/Documents/notes.txt": ("open_file", {"path": "~/Documents/notes.txt"}),
    "delete the file /root/Downloads/report.pdf": ("delete_file", {"path": "/root/Downloads/report.pdf"}),
    "open the file cabinet": None,
    "show my files to Bob": None,
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
    "set a timer for 10 minutes": ("schedule_task", {"when": "in 10 minutes", "task": "tell me that my 10 minutes timer is done (just that, one line)"}),
    "timer 90 seconds": ("schedule_task", {"when": "in 90 seconds", "task": "tell me that my 90 seconds timer is done (just that, one line)"}),
    "remind me in 20 minutes to stretch": ("schedule_task", {"when": "in 20 minutes", "task": "remind me to stretch"}),
    "remind me in 1 hour": ("schedule_task", {"when": "in 1 hour", "task": "tell me that my 1 hour timer is done (just that, one line)"}),
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
    "make everything purple": ("set_appearance", {"color": "purple", "accent": "purple"}),
    "shut down the computer": ("system_power", {"action": "shutdown"}),
    "restart": ("system_power", {"action": "restart"}),
    "power off now": ("system_power", {"action": "shutdown"}),
    "turn off the lights": None,
    "ask me what I want": None,
    # replies need a mail account (none on the build host) -> model / no-account guard
    "reply to Alice that Friday at 7 works and I'll bring dessert": None,
}

bad = 0
for text, want in CASES.items():
    got = intent.match(text)
    if got != want:
        bad += 1
        print(f"MISMATCH {text!r}\n   got    {got}\n   wanted {want}")
print(f"intent shortcuts: {len(CASES) - bad}/{len(CASES)} as expected")
sys.exit(1 if bad else 0)
