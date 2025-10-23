#!/usr/bin/env python3
"""
Mobile Voice Assistant (single-file)
- Designed for Android + Termux (preferred).
- Fallback to Python libraries if Termux API not found.
- Features: wake-word, speech->text, TTS, basic commands:
    - time, date
    - search web
    - open URL / open app (Termux)
    - take quick notes
    - set a simple reminder
    - call / send SMS (Termux)
    - Wikipedia summary
    - exit / stop
Usage:
  1) Give execute permission: chmod +x mobile_assistant.py
  2) Run: python3 mobile_assistant.py
Notes:
  - Termux API improves UX (install: pkg install termux-api, and the Termux:API app from PlayStore if needed).
  - On fallback mode (no termux), install required pip packages listed in README below.
"""

import os
import shutil
import subprocess
import sys
import time
import threading
import webbrowser
from datetime import datetime

# Optional imports for fallback mode
try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import wikipedia
except Exception:
    wikipedia = None

# Config
WAKE_WORDS = ("hey jarvis", "ok jarvis", "jarvis")
NOTES_DIR = os.path.expanduser("~/assistant_notes")
REMINDERS = []  # (datetime, message)

# Environment detection
HAS_TERMUX_TTS = shutil.which("termux-tts-speak") is not None
HAS_TERMUX_STT = shutil.which("termux-speech-to-text") is not None
HAS_TERMUX_OPEN = shutil.which("termux-open") is not None
HAS_TERMUX_SMS = shutil.which("termux-sms-send") is not None
HAS_TERMUX_CALL = shutil.which("termux-telephony-call") is not None

# Fallback TTS engine if termux not available
_engine = None
if not HAS_TERMUX_TTS and pyttsx3:
    try:
        _engine = pyttsx3.init()
    except Exception:
        _engine = None

def tts(text, block=False):
    """Speak text using Termux TTS if available, else pyttsx3 fallback."""
    if text is None:
        return
    text = str(text)
    if HAS_TERMUX_TTS:
        # Termux TTS
        subprocess.Popen(["termux-tts-speak", text])
        if block:
            # A naive wait: estimate time by characters
            time.sleep(min(10, 0.04 * len(text) + 0.5))
    elif _engine:
        _engine.say(text)
        if block:
            _engine.runAndWait()
        else:
            _engine.startLoop(False)
    else:
        # As last resort print text (user can read)
        print("[TTS unavailable] " + text)

def listen_once(timeout=6, phrase_time_limit=8):
    """
    Capture a single user phrase:
    - If termux-speech-to-text available, call it (blocking until spoken/closed).
    - Else try SpeechRecognition with default mic (requires microphone access).
    Returns recognized text (lowercase) or None.
    """
    if HAS_TERMUX_STT:
        try:
            # termux-speech-to-text waits for user to speak then prints text to stdout
            # It launches a speech input UI; read result from stdout
            p = subprocess.run(["termux-speech-to-text"], capture_output=True, text=True, timeout=15)
            res = p.stdout.strip()
            return res.lower() if res else None
        except subprocess.TimeoutExpired:
            return None
        except Exception as e:
            print("Termux STT error:", e)
            return None

    # Fallback via SpeechRecognition
    if sr is None:
        print("No speech recognition available (install SpeechRecognition and PyAudio).")
        return None

    r = sr.Recognizer()
    mic = None
    try:
        mic = sr.Microphone()
    except Exception as e:
        print("Microphone not available:", e)
        return None

    with mic as source:
        r.adjust_for_ambient_noise(source, duration=0.7)
        try:
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except Exception as e:
            return None
    try:
        # Google Web Speech API (requires internet) - default recognizer
        text = r.recognize_google(audio)
        return text.lower()
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print("STT request failed:", e)
        return None

# Utility actions
def say_and_print(msg):
    print("Assistant:", msg)
    tts(msg)

def ensure_notes_dir():
    os.makedirs(NOTES_DIR, exist_ok=True)

def add_note(text):
    ensure_notes_dir()
    fname = os.path.join(NOTES_DIR, datetime.now().strftime("note_%Y%m%d_%H%M%S.txt"))
    with open(fname, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return fname

def open_url(url):
    if HAS_TERMUX_OPEN:
        subprocess.Popen(["termux-open-url", url])
    else:
        webbrowser.open(url)

def open_file_or_uri(uri):
    if HAS_TERMUX_OPEN:
        subprocess.Popen(["termux-open", uri])
    else:
        webbrowser.open(uri)

def send_sms(number, message):
    if HAS_TERMUX_SMS:
        subprocess.run(["termux-sms-send", "-n", number, message])
        return True
    else:
        return False

def make_call(number):
    if HAS_TERMUX_CALL:
        subprocess.run(["termux-telephony-call", number])
        return True
    else:
        return False

def schedule_reminder(rem_time: datetime, message: str):
    def worker(rem_time, message):
        now = datetime.now()
        wait = (rem_time - now).total_seconds()
        if wait > 0:
            time.sleep(wait)
        say_and_print("Reminder: " + message)
    t = threading.Thread(target=worker, args=(rem_time, message), daemon=True)
    t.start()
    REMINDERS.append((rem_time, message))

# Command parsing & handling
def handle_command(text):
    if not text:
        return

    txt = text.lower().strip()
    print("Heard:", txt)

    # Basic intents
    if any(ww in txt for ww in ("exit", "quit", "stop", "bye")):
        say_and_print("Goodbye! Stopping assistant.")
        sys.exit(0)

    if "time" in txt:
        now = datetime.now()
        say_and_print(now.strftime("The time is %I:%M %p."))
        return

    if "date" in txt:
        today = datetime.now().date().isoformat()
        say_and_print("Today's date is " + today)
        return

    if txt.startswith("search ") or txt.startswith("google "):
        q = txt.split(" ", 1)[1]
        say_and_print(f"Searching the web for {q}")
        open_url(f"https://www.google.com/search?q={q.replace(' ', '+')}")
        return

    if txt.startswith("open ") or txt.startswith("launch "):
        target = txt.split(" ", 1)[1]
        say_and_print(f"Opening {target}")
        # If it looks like a URL, open it; else try to open via termux-open
        if target.startswith("http"):
            open_url(target)
        else:
            # try as URL
            if "." in target and " " not in target:
                open_url("http://" + target)
            else:
                # attempt to open package or file via termux-open (best-effort)
                open_file_or_uri(target)
        return

    if txt.startswith("note ") or "take note" in txt:
        # capture full note content
        if txt.startswith("note "):
            note_text = text.split(" ", 1)[1]
        else:
            say_and_print("What would you like me to note?")
            note_text = listen_once() or ""
        if note_text:
            fname = add_note(note_text)
            say_and_print(f"Saved note to {fname}")
        else:
            say_and_print("No note recorded.")
        return

    if "remind me" in txt:
        # naive parse: "remind me in 10 minutes to check oven" or "remind me at 18:30 to call mom"
        say_and_print("Okay, when should I remind you? (say in 10 minutes / at 18:30 / in 1 hour)")
        when = listen_once() or ""
        say_and_print("What is the reminder message?")
        message = listen_once() or "Reminder"
        rem_time = None
        now = datetime.now()
        try:
            if when.startswith("in "):
                # parse minutes/hours
                when = when[3:].strip()
                if "minute" in when:
                    n = int(''.join(ch for ch in when if ch.isdigit()) or 0)
                    rem_time = now + timedelta(minutes=n)
                elif "hour" in when:
                    n = int(''.join(ch for ch in when if ch.isdigit()) or 0)
                    rem_time = now + timedelta(hours=n)
            elif when.startswith("at "):
                tstr = when.split(" ", 1)[1]
                # naive HH:MM
                hh, mm = map(int, tstr.split(":"))
                rem_time = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if rem_time < now:
                    rem_time = rem_time + timedelta(days=1)
        except Exception as e:
            print("Reminder parse error:", e)
            rem_time = None

        if rem_time:
            schedule_reminder(rem_time, message)
            say_and_print(f"Reminder set for {rem_time.isoformat()}")
        else:
            say_and_print("Couldn't parse time. Reminder not set.")
        return

    if txt.startswith("call "):
        number = txt.split(" ", 1)[1].strip()
        if make_call(number):
            say_and_print(f"Calling {number}")
        else:
            say_and_print("Call feature unavailable on this device.")
        return

    if txt.startswith("send sms to ") or txt.startswith("send message to "):
        # e.g. "send sms to +911234567890"
        parts = txt.split(" ", 3)
        if len(parts) >= 4:
            number = parts[3]
            say_and_print("What is the message?")
            message = listen_once() or ""
            if message and send_sms(number, message):
                say_and_print("Message sent.")
            else:
                say_and_print("Unable to send message.")
        else:
            say_and_print("Please say the command like: send sms to +91xxxxxxxxxx")
        return

    if "wikipedia" in txt or txt.startswith("who is ") or txt.startswith("what is "):
        query = txt.replace("wikipedia", "").strip()
        if query.startswith("who is ") or query.startswith("what is "):
            query = ' '.join(query.split(" ")[2:])
        if wikipedia:
            try:
                summary = wikipedia.summary(query, sentences=2)
                say_and_print(summary)
            except Exception as e:
                say_and_print("Couldn't fetch Wikipedia summary: " + str(e))
        else:
            say_and_print("Wikipedia library not installed. Opening web search.")
            open_url(f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}")
        return

    # Default fallback: open web search
    say_and_print("I didn't catch a specific command — searching the web for: " + txt)
    open_url("https://www.google.com/search?q=" + txt.replace(" ", "+"))

# Wake-word loop
def main_loop():
    say_and_print("Mobile assistant started. Say the wake word: " + WAKE_WORDS[0])
    while True:
        # Listen passively for short phrase
        spoken = listen_once(timeout=6, phrase_time_limit=6)
        if not spoken:
            continue
        spoken = spoken.lower()
        # If wake word present in phrase (or direct command), handle
        if any(ww in spoken for ww in WAKE_WORDS):
            say_and_print("Yes? How can I help?")
            cmd = listen_once(timeout=10, phrase_time_limit=12)
            handle_command(cmd)
        else:
            # If user speaks a direct command without wake word, optionally handle
            # To avoid accidental triggers, require wake word OR direct "assistant" command
            if spoken.startswith("assistant") or spoken.startswith("jarvis"):
                cmd = spoken.split(" ", 1)[1] if " " in spoken else None
                handle_command(cmd)
            else:
                # ignore or beep (not implemented)
                pass

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        say_and_print("Assistant stopped by user.")
        sys.exit(0)
              

