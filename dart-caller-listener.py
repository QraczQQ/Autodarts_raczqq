import subprocess
import time
import re
from rpi_ws281x import PixelStrip, Color
from dotenv import load_dotenv
import os
os.environ["SDL_AUDIODRIVER"] = "pulseaudio"


# Wczytaj dane z .env
load_dotenv()

email = os.getenv("AUTODARTS_EMAIL")
password = os.getenv("AUTODARTS_PASSWORD")
board_id = os.getenv("AUTODARTS_BOARD_ID")
media_path = os.getenv("MEDIA_PATH")
media_path_shared = os.getenv("MEDIA_PATH_SHARED")

# --- Konfiguracja LED ---
LED_COUNT = 8
LED_PIN = 13
LED_DMA = 10
LED_FREQ_HZ = 1000000
LED_BRIGHTNESS = 255
LED_INVERT = False
LED_CHANNEL = 1

# --- Inicjalizacja paska ---
strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# --- Pomocnicze funkcje ---
def scale(val, percent=50):
    return int(val * (percent / 100))

def set_led(i, r, g, b):
    strip.setPixelColor(i, Color(r, g, b))

def show_all(r, g, b):
    for i in range(0, LED_COUNT, 2):
        set_led(i, r, g, b)
    strip.show()

def clear():
    show_all(0, 0, 0)

def cw_50():
    show_all(0, 0, scale(255))  # CW = kanał G (zielony)

def yellow_takeout():
    show_all(scale(255), 0, scale(255))  # żółty
    time.sleep(2)
    #cw_50()

def busted():
    show_all(scale(255), 0, 0) #czerwony

def single_60():
    show_all(0, 0, scale(255)) #niebieski

def snake_rgb(delay=0.03):
    for _ in range(10):  # Wykonaj 10 razy cały efekt
        # 1. Do przodu - zielony
        for i in range(0, LED_COUNT, 2):
            set_led(i, 0, scale(255), 0)
            strip.show()
            time.sleep(delay)

        # 2. Do tyłu - czerwony
        for i in range(LED_COUNT - 2, -1, -2):
            set_led(i, scale(255), 0, 0)
            strip.show()
            time.sleep(delay)

        # 3. Do przodu - niebieski
        for i in range(0, LED_COUNT, 2):
            set_led(i, 0, 0, scale(255))
            strip.show()
            time.sleep(delay)

        # 4. Do tyłu - biały
        for i in range(LED_COUNT - 2, -1, -2):
            set_led(i, scale(255), scale(255), scale(255))
            strip.show()
            time.sleep(delay)

# --- Startowe CW 50% ---
cw_50()

# --- Nasłuchiwanie dart-caller ---
def listen_dart_caller():
    # Podmień dane logowania i BOARD_ID!
    #cmd = ["python3", "/home/raczqq/darts-caller/darts-caller.py", "-U", "mateusz.rakowski@gmail.com", "-P", "@Mat3usz1985", "-B", "f62ec6c3-465d-4539-a7d9-3cab057f2611", "-M", "media_path=/home/raczqq/speaker"]
    cmd = [
    "python3",
    "/home/raczqq/darts-caller/darts-caller.py",
    "-U", email,
    "-P", password,
    "-B", board_id,
    "-M", media_path,
    "-MS", media_path_shared,
    "-V", "0.5",
    "-C", "en-US-Joey-Male",
    "-R", "1",
    "-RL", "1",
    "-RG", "1",
    "-CCP", "2",
    "-CBA", "0",
    "-E", "0",
    "-PCC", "1",
    "-PCCYO", "1",
    "-A", "0.8",
    "-AAC", "0",
    "-DL", "10",
    "-DLLA", "1",
    "-DLN", "en-US-Joey-Male",
    "-ROVP", "0",
    "-LPB", "1",
    "-WEBDH", "0",
    "-HP", "8079",
    "-DEB", "0"
    # Mixer-related options left empty intentionally
    # "-MIF", "",
    # "-MIS", "",
    # "-MIC", "",
    # "-MIB", ""
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    for line in process.stdout:
        print("[DC]", line.strip())
        if "Next player" in line:
            cw_50()
        elif "Matchon" in line:
            cw_50()
        elif "Takeout Started" in line:
            yellow_takeout()
        elif "Takeout Finished" in line:
            clear()
        elif "Gameshot and match" in line:
            snake_rgb()
            clear()
        elif "Busted" in line:
            busted()
        elif "bull" in line:
            single_60()
try:
    listen_dart_caller()
except KeyboardInterrupt:
    print("Zatrzymano program.")
    clear()
