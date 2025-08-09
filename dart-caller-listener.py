import subprocess
import time
import re
import threading
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
LED_DMA = 5
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

#def show_all(r, g, b):
#    for i in range(0, LED_COUNT, 2):
#        set_led(i, r, g, b)
#    strip.show()
def show_all(r, g, b, only_even=True):
    if only_even:
        indices = range(0, LED_COUNT, 2)  # parzyste
    else:
        indices = range(LED_COUNT)  # wszystkie
    for i in indices:
        set_led(i, r, g, b)
    strip.show()


#def clear():
#    show_all(0, 0, 0)
def clear():
    show_all(0, 0, 0, only_even=False)  # wyczyść wszystkie

def clear_all():
    for i in range(LED_COUNT):
        set_led(i, 0, 0, 0)
    strip.show()

def green():
    show_all(0, 0, scale(255))  #zielony

def yellow_takeout():
    show_all(scale(255), 0, scale(255))  # żółty

def busted():
    show_all(scale(255), 0, 0) #czerwony

#def blue():
    #show_all(0, 0, scale(255)) #niebieski
def blue():
    # 1. Szybki czerwony wybuch (wszystkie diody)
    for _ in range(8):  # liczba mignięć
        for i in range(LED_COUNT):
            set_led(i, scale(255), 0, 0)  # czerwony
        strip.show()
        time.sleep(0.1)

        for i in range(LED_COUNT):
            set_led(i, 0, 0, 0)  # off
        strip.show()
        time.sleep(0.1)

    # 2. CW - zielony tylko na nieparzystych indeksach (1, 3, 5, 7...)
    for i in range(1, LED_COUNT, 2):
        set_led(i, 0, scale(255), 0)  # zielony
    strip.show()


def start_loop():
    thread = threading.Thread(target=start, daemon=True)
    thread.start()

running = True
def start(delay=0.01, steps=50):
    global running
    while running:
        #if os.path.exists("/tmp/led_disable.flag"):
        #    clear_all()
        #    break
        # Rozjaśnianie
        for i in range(steps):
            if not running:
                break
            brightness = int((i / (steps - 1)) * 255)
            show_all(0, 0, scale(brightness))
            strip.show()
            time.sleep(delay)

        # Przyciemnianie
        for i in range(steps - 1, -1, -1):
            if not running:
                break
            brightness = int((i / (steps - 1)) * 255)
            show_all(0, 0, scale(brightness))
            strip.show()
            time.sleep(delay)

        # Rozjaśnianie
        for i in range(steps):
            if not running:
                break
            brightness = int((i / (steps - 1)) * 255)
            show_all(0, scale(brightness), 0)
            strip.show()
            time.sleep(delay)

        # Przyciemnianie
        for i in range(steps - 1, -1, -1):
            if not running:
                break
            brightness = int((i / (steps - 1)) * 255)
            show_all(0, scale(brightness), 0)
            strip.show()
            time.sleep(delay)


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

# --- Startowe ---
#start_loop()

# --- Nasłuchiwanie dart-caller ---
def listen_dart_caller():
    global running
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
    "-CBA", "1",
    "-E", "2",
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

    last_effect = None  # zapamiętuje ostatnią funkcję efektu
    last_effect_before_takeout = None

    for line in process.stdout:
        print("[DC]", line.strip())
        if "Matchon" in line or "Gameon" in line or "Next player" in line:
            running = False
            last_effect = green
            green()
        elif "Takeout Started" in line:
            running = False
            last_effect_before_takeout = last_effect
            last_effect = yellow_takeout
            yellow_takeout()
        elif "Takeout Finished" in line:
            clear_all()  # lub clear(), ale clear_all daje pełne czyszczenie
            if last_effect_before_takeout:
                last_effect = last_effect_before_takeout
                last_effect()
                running = True
        elif "Gameshot and match" in line or "Gameshot" in line:
            last_effect = start_loop
            snake_rgb()
            #clear()
            running = True
            start_loop()
        elif "Busted" in line:
            running = False
            last_effect = busted
            busted()
        elif 'sound-file-key "bullseye"' in line or 'sound-file-key "bull"' in line:
            blue()
            clear_all()
            if last_effect:
                last_effect()
        elif "match ended" in line.strip().lower():
            running = True
            last_effect = start_loop
            start_loop()
try:
    start_loop()
    listen_dart_caller()
except KeyboardInterrupt:
    print("Zatrzymano program.")
    running = False
    clear()
