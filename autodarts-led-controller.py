#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
os.environ.setdefault("SDL_AUDIODRIVER", "pulseaudio")

import time
import signal
import threading
import subprocess
import select
from queue import Queue, Empty
import re

from rpi_ws281x import PixelStrip, Color, ws
from evdev import InputDevice, ecodes

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ========= USTAWIENIA =========
# --- LED strip ---
LED_COUNT   = 28
LED_PIN     = 18
LED_DMA     = 10
LED_FREQ_HZ = 800_000
LED_INVERT  = False
LED_CHANNEL = 0
STRIP_TYPE  = ws.WS2811_STRIP_BRG   # whites: Color(WW,0,CW) -> WW=R, CW=B

# ile LED ma działać dla WSZYSTKICH efektów poza snake
ACTIVE_COUNT_NON_SNAKE = 22

# zakres, na którym działa dart-caller (LED 23..28 -> indeksy 22..27)
DART_START = 22
DART_END   = 28   # exclusive

# --- IR kody ---
IR_ON           = 0xef1f
IR_OFF          = 0xef1e
IR_RED          = 0xef00
IR_GREEN        = 0xef01
IR_BLUE         = 0xef02
IR_WW           = 0xef0c
IR_WW_CW_BLUE   = 0xef0d
IR_CW           = 0xef0e
IR_ORANGE       = 0xef04
IR_LGR          = 0xef05
IR_LBL          = 0xef06
IR_DIM          = 0xef1d
IR_BRIGHT       = 0xef1c
IR_WBAL_UP      = 0xef0f   # nowość: więcej CW
IR_WBAL_DOWN    = 0xef13   # nowość: więcej WW

# --- Presety jasności (w %) ---
PRESET_LEVELS = [10, 25, 50, 75, 100]
preset_index = len(PRESET_LEVELS) - 1  # start 100%
brightness_level = PRESET_LEVELS[preset_index]

# --- ENV dla dart-caller (opcjonalnie .env) ---
EMAIL = os.getenv("AUTODARTS_EMAIL", "")
PASSWORD = os.getenv("AUTODARTS_PASSWORD", "")
BOARD_ID = os.getenv("AUTODARTS_BOARD_ID", "")
MEDIA_PATH = os.getenv("MEDIA_PATH", "")
MEDIA_PATH_SHARED = os.getenv("MEDIA_PATH_SHARED", "")

# ========= INICJALIZACJA =========
strip = PixelStrip(
    LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT,
    255, LED_CHANNEL, strip_type=STRIP_TYPE
)
strip.begin()

state_lock = threading.Lock()
effect_queue: "Queue[dict]" = Queue()
running = True
led_enabled = True
current_effect = "idle"
# --- dc_idle: wątek i flaga stopu
dc_idle_thread = None
dc_idle_stop = threading.Event()


# Bufor klatki (biblioteka nie zwraca bieżących kolorów)
current_frame = [(0,0,0)] * LED_COUNT

# uchwyty
ir_dev = None
dc_proc = None

# ========= BALANS BIELI (WW↔CW) =========
WHITE_BALANCE = 0.5   # 0.0 = 100% WW, 1.0 = 100% CW
WHITE_STEP = 0.1
dart_mode = "idle"      # tryb segmentu 23..28: 'green','yellow','gameshot','bull_cw','off',...
prev_dart_mode = None  # <— NOWE: zapamiętany tryb sprzed Takeout

def whites_from_balance(brightness=255):
    """Zwraca (WW, CW) wg WHITE_BALANCE i jasności 0..255."""
    ww = int((1.0 - WHITE_BALANCE) * brightness)
    cw = int(WHITE_BALANCE * brightness)
    return ww, cw

def white_balance_up():
    global WHITE_BALANCE
    WHITE_BALANCE = min(1.0, round(WHITE_BALANCE + WHITE_STEP, 2))
    print(f"[WBAL] -> {WHITE_BALANCE:.2f}")
    refresh_whites_after_balance()

def white_balance_down():
    global WHITE_BALANCE
    WHITE_BALANCE = max(0.0, round(WHITE_BALANCE - WHITE_STEP, 2))
    print(f"[WBAL] -> {WHITE_BALANCE:.2f}")
    refresh_whites_after_balance()

def refresh_whites_after_balance():
    """Odświeża miejsca, gdzie używamy WW+CW:
       - efekty 1..22, jeśli aktywne to 'ww_cw_odd' lub 'all_max'
       - segment dart-caller 23..28 w trybach 'yellow' i 'gameshot'
    """
    # 1) Efekty 1..22
    if current_effect in ("ww_cw_odd", "alternate_white", "all_max"):
        # wykonaj ponownie bieżący efekt (korzysta z WHITE_BALANCE)
        func = EFFECTS.get(current_effect)
        if func:
            try:
                func()
                strip.show()
            except Exception as e:
                print(f"[WBAL] refresh effects error: {e}")

    # 2) Segment dart-caller 23..28
    if dart_mode in ("yellow", "gameshot"):
        ww, cw = whites_from_balance(255)
        set_range_odd_whites(ww, cw)

# ========= HELPERY OGÓLNE =========
def pct_to_brightness(pct: int) -> int:
    pct = max(0, min(100, pct))
    gamma = 2.2
    return int((pct / 100) ** gamma * 255)

def apply_brightness(show=True):
    strip.setBrightness(pct_to_brightness(brightness_level))
    if show:
        strip.show()

def set_led_raw(i, r, g, b):
    strip.setPixelColor(i, Color(r, g, b))

def draw_frame(frame, show=True):
    for i, (r, g, b) in enumerate(frame):
        set_led_raw(i, r, g, b)
        current_frame[i] = (r, g, b)
    if show:
        strip.show()

def clear_all_28():
    draw_frame([(0,0,0)] * LED_COUNT, show=True)

def mask_frame(frame, n):
    f = frame[:]
    for i in range(n, len(f)):
        f[i] = (0,0,0)
    return f

def draw_frame_22(frame, show=True):
    draw_frame(mask_frame(frame, ACTIVE_COUNT_NON_SNAKE), show=show)

def frame_fill_even_odd(mode: str, rgb_even=(0,0,0), rgb_odd=(0,0,0)):
    out = []
    for i in range(LED_COUNT):
        if mode == 'even':
            out.append(rgb_even if i % 2 == 0 else (0,0,0))
        elif mode == 'odd':
            out.append(rgb_odd if i % 2 == 1 else (0,0,0))
        else:
            out.append(rgb_even)
    return out

def lerp(a, b, t): return int(a + (b - a) * t)

def crossfade_to_frame(target_frame, duration=0.5, steps=24):
    if steps <= 0 or duration <= 0:
        draw_frame(target_frame, show=True); return
    delay = duration / steps
    start = current_frame[:]
    for s in range(1, steps+1):
        t = s / steps
        blended = [(lerp(sr,tr,t), lerp(sg,tg,t), lerp(sb,tb,t))
                   for (sr,sg,sb),(tr,tg,tb) in zip(start, target_frame)]
        draw_frame(blended, show=True)
        time.sleep(delay)

# ========= PREVIEW (CROSS-FADE) =========
def preview_frame(name: str):
    """Podgląd do cross-fade. Snake = pełne 28; reszta maskowana do 22."""
    ww, cw = whites_from_balance(255)
    PREVIEWS = {
        "red":  frame_fill_even_odd('even', (255,0,0)),
        "green":frame_fill_even_odd('even', (0,255,0)),
        "blue": frame_fill_even_odd('even', (0,0,255)),
        "orange": frame_fill_even_odd('even', (255,70,0)),
        "lgr": frame_fill_even_odd('even', (0,75,255)),
        "lbl": frame_fill_even_odd('even', (0,255,0)),
        # whites na nieparzystych: WW=R, CW=B
        "ww":   frame_fill_even_odd('odd',  rgb_odd=(255,0,0)),
        "cw":   frame_fill_even_odd('odd',  rgb_odd=(0,0,255)),
        "ww_cw_odd": frame_fill_even_odd('odd', rgb_odd=(ww,0,cw)),
        "ww_cw_blue": frame_fill_even_odd('odd', rgb_odd=(ww,0,cw)),
        "alternate_white": frame_fill_even_odd('odd', rgb_odd=(ww,0,cw)),
        # ALL MAX: parzyste biel RGB; nieparzyste WW+CW wg balansu
        "all_max": [(255,255,255) if (i % 2 == 0) else (ww,0,cw) for i in range(LED_COUNT)],
        "snake_combo": [(0,0,0)] * LED_COUNT,
        "idle": [(0,0,0)] * LED_COUNT,
    }
    f = PREVIEWS.get(name, [(0,0,0)] * LED_COUNT)
    if name not in ("snake_combo", "snake"):
        f = mask_frame(f, ACTIVE_COUNT_NON_SNAKE)
    return f

# ========= EFEKTY =========
def snake_rgb_all(delay=0.03):
    for i in range(0, LED_COUNT, 2):
        frame = current_frame[:]; frame[i] = (0,255,0)
        draw_frame(frame); time.sleep(delay)
    for i in range(LED_COUNT - 2, -1, -2):
        frame = current_frame[:]; frame[i] = (255,0,0)
        draw_frame(frame); time.sleep(delay)
    for i in range(0, LED_COUNT, 2):
        frame = current_frame[:]; frame[i] = (0,0,255)
        draw_frame(frame); time.sleep(delay)
    for i in range(LED_COUNT - 2, -1, -2):
        frame = current_frame[:]; frame[i] = (255,255,255)
        draw_frame(frame); time.sleep(delay)
        
def snake_rgb_range(start=DART_START, end=DART_END, delay=0.03, cycles=1, final="clear"):
    """
    Snake RGB tylko w [start, end). final: "clear" | "restore" | None
      - clear    -> gasi zakres po animacji
      - restore  -> ustawia: even=RGB biel, odd=WW+CW wg balansu
      - None     -> zostawia ostatnią klatkę
    """
    def _wipe_range(buf):
        for j in range(start, min(end, LED_COUNT)):
            buf[j] = (0, 0, 0)

    for _ in range(cycles):
        for i in range(start, end):
            frame = current_frame[:]; _wipe_range(frame)
            frame[i] = (0, 255, 0);   draw_frame(frame); time.sleep(delay)
        for i in range(end - 1, start - 1, -1):
            frame = current_frame[:]; _wipe_range(frame)
            frame[i] = (255, 0, 0);  draw_frame(frame); time.sleep(delay)
        for i in range(start, end):
            frame = current_frame[:]; _wipe_range(frame)
            frame[i] = (0, 0, 255);  draw_frame(frame); time.sleep(delay)
        for i in range(end - 1, start - 1, -1):
            frame = current_frame[:]; _wipe_range(frame)
            frame[i] = (255, 255, 255); draw_frame(frame); time.sleep(delay)

    # --- finalizacja ---
    if final == "clear":
        clear_range(start, end)
    elif final == "restore":
        clear_range(start, end)
        set_range_even_rgb(255, 255, 255, start, end)
        ww, cw = whites_from_balance(255)
        set_range_odd_whites(ww, cw, start, end)



def only_cw_scaled_limit(raw_0_255, limit=22):
    frame = [(0,0,0)] * LED_COUNT
    upto = min(limit, LED_COUNT)
    for i in range(upto):
        if i % 2 == 1:
            frame[i] = (0, 0, raw_0_255)  # CW=B
    draw_frame(frame)

def fade_cw_cycles(limit=22):
    steps_up = 50; steps_down = 30
    inc = max(1, 256 // steps_up)
    dec = max(1, 256 // steps_down)
    for b in range(0, 256, inc):
        only_cw_scaled_limit(b, limit=limit); time.sleep(0.02)
    for b in range(255, -1, -dec):
        only_cw_scaled_limit(b, limit=limit); time.sleep(0.04)
    for b in range(0, 129, inc):
        only_cw_scaled_limit(b, limit=limit); time.sleep(0.02)

# statyczne (maskowane do 22)
def effect_red_even():        draw_frame_22(frame_fill_even_odd('even', (255,0,0)))
def effect_green_even():      draw_frame_22(frame_fill_even_odd('even', (0,255,0)))
def effect_blue_even():       draw_frame_22(frame_fill_even_odd('even', (0,0,255)))
def effect_orange_even():     draw_frame_22(frame_fill_even_odd('even', (255,70,0)))
def effect_lgr_even():        draw_frame_22(frame_fill_even_odd('even', (0,75,255)))
def effect_lbl_even():        draw_frame_22(frame_fill_even_odd('even', (0,255,0)))
def effect_ww_odd():          draw_frame_22(frame_fill_even_odd('odd',  rgb_odd=(255,0,0)))   # WW=R
def effect_cw_odd():          draw_frame_22(frame_fill_even_odd('odd',  rgb_odd=(0,0,255)))   # CW=B
def effect_ww_cw_odd():
    ww, cw = whites_from_balance(255)
    draw_frame_22(frame_fill_even_odd('odd',  rgb_odd=(ww,0,cw)))

def effect_all_max():
    ww, cw = whites_from_balance(255)
    frame = [(255,255,255) if (i % 2 == 0) else (ww,0,cw) for i in range(LED_COUNT)]
    draw_frame_22(frame)

def effect_snake_combo():
    snake_rgb_all()
    snake_rgb_all()
    fade_cw_cycles(limit=22)
    only_cw_scaled_limit(128, limit=22)

EFFECTS = {
    "red": effect_red_even,
    "green": effect_green_even,
    "blue": effect_blue_even,
    "orange": effect_orange_even,
    "lgr": effect_lgr_even,
    "lbl": effect_lbl_even,
    "ww": effect_ww_odd,
    "cw": effect_cw_odd,
    "ww_cw_odd": effect_ww_cw_odd,
    "ww_cw_blue": effect_ww_cw_odd,
    "alternate_white": effect_ww_cw_odd,
    "all_max": effect_all_max,
    "snake_combo": effect_snake_combo,
    "idle": lambda: None,
}

# ========= WORKER EFEKTÓW =========
def effects_worker():
    global current_effect
    while running:
        try:
            job = effect_queue.get(timeout=0.1)
        except Empty:
            continue
        name = job.get("name")
        do_fade = job.get("fade", True)
        fade_time = job.get("fade_time", 0.5)
        with state_lock:
            current_effect = name
            enabled = led_enabled
            func = EFFECTS.get(name)
        if not enabled:
            clear_all_28()
            continue
        try:
            if do_fade:
                target = preview_frame(name)
                crossfade_to_frame(target, duration=fade_time, steps=max(1, int(fade_time*48)))
            if func:
                func()
                strip.show()
        except Exception as e:
            print(f"[effects] {name} failed: {e}")

def set_effect(name, fade=True, fade_time=0.5):
    try:
        while True:
            effect_queue.get_nowait()
    except Empty:
        pass
    effect_queue.put({"name": name, "fade": fade, "fade_time": fade_time})

# ========= IR LISTENER =========
def enable_leds(enable: bool):
    global led_enabled
    with state_lock:
        led_enabled = enable
    if enable:
        print("LED: ON")
        apply_brightness(show=False)
    else:
        print("LED: OFF")
        clear_all_28()

def clear_and_flag():
    clear_all_28()
    try:
        with open("/tmp/led_disable.flag", "w") as f:
            f.write("off")
    except Exception as e:
        print(f"Nie mogę zapisać flagi: {e}")

def ir_listener(device_path='/dev/input/event0'):
    global ir_dev
    ir_dev = InputDevice(device_path)
    print(f"Nasłuchiwanie IR na {device_path}...")
    try:
        ir_dev.grab()
    except Exception:
        pass

    poller = select.poll()
    poller.register(ir_dev.fileno(), select.POLLIN)

    debounce_time = 0.4
    last_time = 0.0
    last_code = None

    code_to_action = {
        IR_ON:  lambda: (enable_leds(True), set_effect("snake_combo", fade=True, fade_time=0.6)),
        IR_OFF: lambda: (enable_leds(False), clear_all_28()),
        IR_RED: lambda: (print("Czerwone parzyste (1..22)"), set_effect("red")),
        IR_GREEN: lambda: (print("Zielone parzyste (1..22)"), set_effect("green")),
        IR_BLUE: lambda: (print("Niebieskie parzyste (1..22)"), set_effect("blue")),
        IR_WW: lambda: (print("WW nieparzyste (1..22)"), set_effect("ww")),
        IR_WW_CW_BLUE: lambda: (print("WW+CW (1..22)"), set_effect("ww_cw_odd")),
        IR_CW: lambda: (print("CW nieparzyste (1..22)"), set_effect("cw")),
        IR_ORANGE: lambda: (print("Pomarańczowy even (1..22)"), set_effect("orange")),
        IR_LGR: lambda: (print("LGR even (1..22)"), set_effect("lgr")),
        IR_LBL: lambda: (print("LBL even (1..22)"), set_effect("lbl")),
        IR_DIM: lambda: preset_prev_action(),
        IR_BRIGHT: lambda: preset_next_action(),
        # balans bieli:
        IR_WBAL_UP:   lambda: white_balance_up(),
        IR_WBAL_DOWN: lambda: white_balance_down(),
    }

    try:
        while running:
            events = poller.poll(200)
            if not events:
                continue
            for _ in events:
                for event in ir_dev.read():
                    if event.type == ecodes.EV_MSC and event.code == ecodes.MSC_SCAN:
                        sc = event.value
                        now = time.time()
                        if (now - last_time) < debounce_time and sc == last_code:
                            continue
                        last_time, last_code = now, sc
                        print(f"[IR] Kod: {hex(sc)}")
                        action = code_to_action.get(sc)
                        action() if action else print("Nieznany kod — brak akcji")
    except OSError:
        pass
    finally:
        try:
            ir_dev.ungrab()
        except Exception:
            pass
        try:
            ir_dev.close()
        except Exception:
            pass
        ir_dev = None

# ========= PRESETY JASNOŚCI =========
def preset_prev_action():
    global preset_index, brightness_level
    if preset_index > 0:
        preset_index -= 1
    brightness_level = PRESET_LEVELS[preset_index]
    print(f"Preset jasności: {brightness_level}%")
    apply_brightness()

def preset_next_action():
    global preset_index, brightness_level
    if preset_index < len(PRESET_LEVELS) - 1:
        preset_index += 1
    brightness_level = PRESET_LEVELS[preset_index]
    print(f"Preset jasności: {brightness_level}%")
    apply_brightness()

# ========= DART-CALLER: zakres 23..28 =========
def set_range_even_rgb(r, g, b, start=DART_START, end=DART_END):
    for i in range(start, min(end, LED_COUNT)):
        if i % 2 == 0:
            strip.setPixelColor(i, Color(r, g, b))
    strip.show()

def set_range_odd_whites(ww, cw, start=DART_START, end=DART_END):
    for i in range(start, min(end, LED_COUNT)):
        if i % 2 == 1:
            strip.setPixelColor(i, Color(ww, 0, cw))  # WW=R, CW=B
    strip.show()

def clear_range(start, end):
    for i in range(start, min(end, LED_COUNT)):
        strip.setPixelColor(i, Color(0,0,0))
    strip.show
    
def set_range_even_rgb_scaled(r, g, b, scale, start=DART_START, end=DART_END):
    """Ustaw even w [start,end) kolorem (r,g,b)*scale (0..1)."""
    rs = int(r * scale); gs = int(g * scale); bs = int(b * scale)
    for i in range(start, min(end, LED_COUNT)):
        if i % 2 == 0:
            strip.setPixelColor(i, Color(rs, gs, bs))
    strip.show()

def clear_range_odd(start=DART_START, end=DART_END):
    """Zgaś odd w [start,end) — na idle nie świecimy whites."""
    for i in range(start, min(end, LED_COUNT)):
        if i % 2 == 1:
            strip.setPixelColor(i, Color(0,0,0))
    strip.show()
 
def restore_dart_mode_after_takeout():
    global dart_mode, prev_dart_mode
    # domyślnie wyczyść segment
    clear_range(DART_START, DART_END)

    if prev_dart_mode == "gameshot":
        dc_gameshot()
    elif prev_dart_mode == "green":
        dc_green()
    elif prev_dart_mode == "busted":
        dc_busted()
    elif prev_dart_mode == "idle" or prev_dart_mode == "off" or prev_dart_mode is None:
        # wróć do „ciszy” – Twój wybór: idle w segmencie lub zostaw ciemno
        dc_idle_start()   # albo po prostu zostaw clear_range(...)
    else:
        # nieznany – nic nie rób (zostanie wyczyszczone)
        pass

    prev_dart_mode = None


def _dc_idle_worker(delay=0.02, steps=80):
    """
    'Oddychanie' na even w 23..28:
    - jasność sinusoidalna
    - miks przejść między kolorami z palety
    - odd (whites) wyłączone na czas idle
    """
    import math
    palette = [
        (255,   0,   0),  # red
        (255, 255,   0),  # yellow
        (0,   255,   0),  # green
        (0,   255, 255),  # cyan
        (0,     0, 255),  # blue
        (255,   0, 255),  # magenta
        (255, 255, 255),  # white
    ]
    # upewnij się, że odd są zgaszone
    clear_range_odd(DART_START, DART_END)

    idx = 0
    while not dc_idle_stop.is_set():
        c0 = palette[idx % len(palette)]
        c1 = palette[(idx + 1) % len(palette)]
        # przejście c0 -> c1 z oddechem
        for t in range(steps):
            if dc_idle_stop.is_set():
                break
            # progres przejścia koloru
            p = t / (steps - 1)
            r = int(c0[0] + (c1[0] - c0[0]) * p)
            g = int(c0[1] + (c1[1] - c0[1]) * p)
            b = int(c0[2] + (c1[2] - c0[2]) * p)
            # oddech (0..1): (1 - cos)/2
            breath = (1.0 - math.cos(2 * math.pi * p)) * 0.5
            # lekki offset, żeby nie gasło do zera:
            scale = 0.12 + 0.88 * breath
            set_range_even_rgb_scaled(r, g, b, scale, DART_START, DART_END)
            time.sleep(delay)
        idx += 1

def dc_idle_start():
    """Uruchom dc_idle w tle (jeśli już nie działa)."""
    global dc_idle_thread, dart_mode
    dart_mode = "idle"
    if dc_idle_thread and dc_idle_thread.is_alive():
        return
    dc_idle_stop.clear()
    dc_idle_thread = threading.Thread(target=_dc_idle_worker, daemon=True)
    dc_idle_thread.start()

def dc_idle_stop_fn(clear_segment=False):
    """Zatrzymaj dc_idle (opcjonalnie zgaś 23..28)."""
    global dc_idle_thread
    dc_idle_stop.set()
    if dc_idle_thread:
        try:
            dc_idle_thread.join(timeout=0.5)
        except Exception:
            pass
    dc_idle_thread = None
    if clear_segment:
        clear_range(DART_START, DART_END)


def dc_green():
    global dart_mode
    dart_mode = "green"
    clear_range(DART_START, DART_END)
    set_range_even_rgb(0, 255, 0)

def dc_yellow_takeout():
    global dart_mode, prev_dart_mode
    prev_dart_mode = dart_mode          # <— zapamiętaj
    dart_mode = "yellow"
    clear_range(DART_START, DART_END)
    set_range_even_rgb(255, 255, 0)


def dc_busted():
    global dart_mode
    dart_mode = "busted"
    clear_range(DART_START, DART_END)
    set_range_even_rgb(255, 0, 0)

def dc_gameshot():
    global dart_mode
    dart_mode = "gameshot"
    snake_rgb_range(DART_START, DART_END, delay=0.03, cycles=1, final="clear")

def dc_bull():
    global dart_mode
    dart_mode = "bull_cw"
    for _ in range(6):
        for i in range(DART_START, DART_END):
            strip.setPixelColor(i, Color(255,0,0))
        strip.show(); time.sleep(0.08)
        clear_range(DART_START, DART_END); time.sleep(0.08)
    # po fleszach: CW na nieparzystych (tu nie używamy balansu: to czyste CW)
    set_range_odd_whites(0, 255)

def dart_caller_thread():
    global dc_proc, running
    cmd = [
        "python3", "/home/raczqq/darts-caller/darts-caller.py",
        "-U", EMAIL, "-P", PASSWORD, "-B", BOARD_ID,
        "-M", MEDIA_PATH, "-MS", MEDIA_PATH_SHARED,
        "-V","0.5","-C","en-US-Joey-Male",
        "-R","1","-RL","1","-RG","1",
        "-CCP","2","-CBA","1","-E","2",
        "-PCC","1","-PCCYO","1","-A","0.8",
        "-AAC","0","-DL","10","-DLLA","1",
        "-DLN","en-US-Joey-Male","-ROVP","0",
        "-LPB","1","-WEBDH","0","-HP","8079",
        "-DEB","0"
    ]
    try:
        dc_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        print(f"[dart-caller] nie mogę uruchomić: {e}")
        return

    print("[dart-caller] start")
    try:
        for line in dc_proc.stdout:
            if not running:
                break
            s = line.strip()
            if not s: 
                continue
            print("[DC]", s)

            # mapowanie zdarzeń -> tylko LED 23..28
            if re.search(r"(Matchon|Gameon|Next player)", s, re.I):
                dc_idle_stop_fn(clear_segment=True)
                dc_green()
            elif re.search(r"Takeout Started", s, re.I):
                dc_idle_stop_fn(clear_segment=True)
                dc_yellow_takeout()
            elif re.search(r"Takeout Finished", s, re.I):
                restore_dart_mode_after_takeout()   # <— zamiast samego clear/idle
            elif re.search(r"(Gameshot and match|Gameshot)", s, re.I):
                dc_idle_stop_fn(clear_segment=True)
                dc_gameshot()
                clear_range(DART_START, DART_END); dart_mode = "off"
                dc_idle_start()
            elif re.search(r"Busted", s, re.I):
                dc_idle_stop_fn(clear_segment=True)
                dc_busted()
            elif re.search(r'sound-file-key\s+"(?:bullseye|bull)"', s, re.I):
                dc_idle_stop_fn(clear_segment=True)
                dc_bull()
            elif re.search(r"match ended", s, re.I):
                dc_idle_start()
                #clear_range(DART_START, DART_END); dart_mode = "off"

    except Exception as e:
        print(f"[dart-caller] loop err: {e}")
    finally:
        print("[dart-caller] stop")
        try:
            if dc_proc and dc_proc.poll() is None:
                dc_proc.terminate()
                dc_proc.wait(timeout=2)
        except Exception:
            try:
                dc_proc.kill()
            except Exception:
                pass
        dc_proc = None

# ========= START/STOP =========
def on_exit(*_):
    global running, ir_dev, dc_proc
    print("Zamykanie...")
    running = False
    try:
        if ir_dev: ir_dev.close()
    except Exception:
        pass
    try:
        if dc_proc and dc_proc.poll() is None:
            dc_proc.terminate()
            dc_proc.wait(timeout=2)
    except Exception:
        try:
            dc_proc.kill()
        except Exception:
            pass
    try:
        clear_all_28()
    except Exception:
        pass

if __name__ == "__main__":
    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    # wątek efektów
    worker = threading.Thread(target=effects_worker, daemon=True)
    worker.start()

    # startowy stan jak po uruchomieniu: snake_combo
    apply_brightness(show=False)
    set_effect("snake_combo", fade=False)

    # wątek dart-caller
    dc_thread = threading.Thread(target=dart_caller_thread, daemon=True)
    dc_thread.start()

    # IR w wątku głównym (blokujące)
    try:
        ir_listener('/dev/input/event0')
    finally:
        on_exit()
        try: worker.join(timeout=1.0)
        except Exception: pass
        try: dc_thread.join(timeout=1.0)
        except Exception: pass
