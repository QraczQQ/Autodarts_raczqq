from rpi_ws281x import PixelStrip, Color, ws
from evdev import InputDevice, ecodes
import RPi.GPIO as GPIO
import time
import threading
import subprocess
import signal
from queue import Queue, Empty
from math import ceil
import select

# --- Konfiguracja paska ---
LED_COUNT = 28
LED_PIN = 18
LED_DMA = 10
LED_FREQ_HZ = 800_000
LED_INVERT = False
LED_CHANNEL = 0
STRIP_TYPE = ws.WS2811_STRIP_BRG

# --- Presety jasności (w %)
PRESET_LEVELS = [10, 25, 50, 75, 100]
preset_index = len(PRESET_LEVELS) - 1  # start na 100%
brightness_level = PRESET_LEVELS[preset_index]

# --- Kody IR ---
IR_ON = 0xef1f
IR_OFF = 0xef1e
IR_RED = 0xef00
IR_GREEN = 0xef01
IR_BLUE = 0xef02
IR_WW = 0xef0c
IR_WW_CW_BLUE = 0xef0d
IR_CW = 0xef0e
IR_ORANGE = 0xef04
IR_LGR = 0xef05
IR_LBL = 0xef06
IR_DIM = 0xef1d
IR_BRIGHT = 0xef1c

# --- Inicjalizacja stripu ---
strip = PixelStrip(
    LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT,
    255,  # sterownik na 0..255; realny poziom regulujemy setBrightness()
    LED_CHANNEL, strip_type=STRIP_TYPE
)
strip.begin()

# --- Stan / synchronizacja ---
state_lock = threading.Lock()
effect_queue: "Queue[tuple[str, dict]]" = Queue()
running = True
led_enabled = True
current_effect = "idle"
ACTIVE_COUNT_NON_SNAKE = 22  # ile diód ma być aktywnych dla WSZYSTKICH efektów poza snake

def mask_frame(frame, n):
    """Wyzeruj piksele >= n."""
    f = frame[:]  # kopia
    for i in range(n, len(f)):
        f[i] = (0, 0, 0)
    return f

def draw_frame_22(frame, show=True):
    """Rysuj tylko pierwsze 22 (resztę gaś)."""
    draw_frame(mask_frame(frame, ACTIVE_COUNT_NON_SNAKE), show=show)


# Bufor aktualnej klatki (trzymamy własny stan, bo biblioteka nie zwraca koloru)
current_frame = [(0, 0, 0)] * LED_COUNT

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
    """Rysuje całą klatkę i aktualizuje bufor current_frame."""
    for i, (r, g, b) in enumerate(frame):
        set_led_raw(i, r, g, b)
        current_frame[i] = (r, g, b)
    if show:
        strip.show()

def clear(show=True):
    draw_frame([(0, 0, 0)] * LED_COUNT, show=show)

# ---------- Narzędzia do generowania klatek ----------
def frame_fill_even_odd(mode: str, rgb_even=(0,0,0), rgb_odd=(0,0,0)):
    out = []
    for i in range(LED_COUNT):
        if mode == 'even':
            out.append(rgb_even if i % 2 == 0 else (0,0,0))
        elif mode == 'odd':
            out.append(rgb_odd if i % 2 == 1 else (0,0,0))
        else:  # 'all'
            out.append(rgb_even)
    return out

def preview_frame(name: str):
    """Podgląd klatki do cross-fade. Parzyste = RGB, nieparzyste = whites (WW=R, CW=B)."""
    PREVIEWS = {
        "red":  frame_fill_even_odd('even', (255,0,0)),
        "green":frame_fill_even_odd('even', (0,255,0)),
        "blue": frame_fill_even_odd('even', (0,0,255)),
        "orange": frame_fill_even_odd('even', (255,70,0)),
        "lgr": frame_fill_even_odd('even', (0,75,255)),
        "lbl": frame_fill_even_odd('even', (0,255,0)),
        # whites na nieparzystych:
        "ww":   frame_fill_even_odd('odd',  rgb_odd=(255,0,0)),     # WW = R
        "cw":   frame_fill_even_odd('odd',  rgb_odd=(0,0,255)),     # CW = B
        "ww_cw_odd":     frame_fill_even_odd('odd', rgb_odd=(255,0,255)), # WW+CW = R+B
        "ww_cw_blue":    frame_fill_even_odd('odd', rgb_odd=(255,0,255)),
        "alternate_white": frame_fill_even_odd('odd', rgb_odd=(255,0,255)),
        # ALL MAX: parzyste pełna biel RGB, nieparzyste WW+CW
        "all_max": [(255,255,255) if (i % 2 == 0) else (255,0,255) for i in range(LED_COUNT)],
        # snake może używać pełnych 28
        "snake_combo": [(0,0,0)] * LED_COUNT,
        "idle": [(0,0,0)] * LED_COUNT,
    }
    f = PREVIEWS.get(name, [(0,0,0)] * LED_COUNT)
    # tylko snake ma mieć pełne 28; resztę maskujemy do 22
    if name not in ("snake_combo", "snake"):
        f = mask_frame(f, ACTIVE_COUNT_NON_SNAKE)
    return f




def lerp(a, b, t):
    return int(a + (b - a) * t)

def crossfade_to_frame(target_frame, duration=0.5, steps=24):
    """Łagodne przejście z current_frame do target_frame."""
    if steps <= 0 or duration <= 0:
        draw_frame(target_frame, show=True)
        return
    delay = duration / steps
    start = current_frame[:]  # kopia
    for s in range(1, steps + 1):
        t = s / steps
        blended = [
            (lerp(sr, tr, t), lerp(sg, tg, t), lerp(sb, tb, t))
            for (sr, sg, sb), (tr, tg, tb) in zip(start, target_frame)
        ]
        draw_frame(blended, show=True)
        time.sleep(delay)

# ---------- Efekty ----------
def snake_rgb(delay=0.03):
    for i in range(0, LED_COUNT, 2):
        frame = current_frame[:]
        frame[i] = (0,255,0)
        draw_frame(frame); time.sleep(delay)
    for i in range(LED_COUNT - 2, -1, -2):
        frame = current_frame[:]
        frame[i] = (255,0,0)
        draw_frame(frame); time.sleep(delay)
    for i in range(0, LED_COUNT, 2):
        frame = current_frame[:]
        frame[i] = (0,0,255)
        draw_frame(frame); time.sleep(delay)
    for i in range(LED_COUNT - 2, -1, -2):
        frame = current_frame[:]
        frame[i] = (255,255,255)
        draw_frame(frame); time.sleep(delay)

# --- nowy snake na wszystkich 28 LED-ach ---
def snake_rgb_all(delay=0.03):
    # 1. Do przodu - zielony
    for i in range(0, LED_COUNT, 2):
        frame = current_frame[:]
        frame[i] = (0, 255, 0)
        draw_frame(frame); time.sleep(delay)
    # 2. Do tyłu - czerwony
    for i in range(LED_COUNT - 2, -1, -2):
        frame = current_frame[:]
        frame[i] = (255, 0, 0)
        draw_frame(frame); time.sleep(delay)
    # 3. Do przodu - niebieski
    for i in range(0, LED_COUNT, 2):
        frame = current_frame[:]
        frame[i] = (0, 0, 255)
        draw_frame(frame); time.sleep(delay)
    # 4. Do tyłu - biały
    for i in range(LED_COUNT - 2, -1, -2):
        frame = current_frame[:]
        frame[i] = (255, 255, 255)
        draw_frame(frame); time.sleep(delay)

def fade_out_even_rgb(delay=0.02, step=15):
    # wygaszanie tylko parzystych
    for b in range(255, -1, -step):
        frame = current_frame[:]
        for i in range(0, LED_COUNT, 2):
            frame[i] = (b, b, b)
        draw_frame(frame); time.sleep(delay)
    frame = current_frame[:]
    for i in range(0, LED_COUNT, 2):
        frame[i] = (0,0,0)
    draw_frame(frame)

def only_cw_scaled(raw_0_255):
    """CW na nieparzystych: Color(WW, 0, CW) -> CW = B."""
    frame = [(0,0,0)] * LED_COUNT
    for i in range(LED_COUNT):
        if i % 2 == 1:
            frame[i] = (0, 0, raw_0_255)  #   WW=R, G=0, CW=B
    draw_frame(frame)

def only_ww_scaled_limit(raw_0_255, limit=22):
    frame = [(0, 0, 0)] * LED_COUNT
    upto = min(limit, LED_COUNT)
    for i in range(upto):
        if i % 2 == 1:
            frame[i] = (raw_0_255, 0, 0)  # WW = R
    draw_frame(frame)  # cała klatka, więc >=limit jest zgaszone


# --- wersja only_cw_scaled ograniczona do pierwszych 22 LED-ów ---
def only_cw_scaled_limit(raw_0_255, limit=22):
    """
    CW na NIEPARZYSTYCH indeksach < limit.
    Reszta diod (>= limit) zgaszona.
    Założenia: STRIP_TYPE=BRG, whites: Color(WW,0,CW) -> CW = kanał B.
    """
    frame = [(0, 0, 0)] * LED_COUNT
    upto = min(limit, LED_COUNT)
    for i in range(upto):
        if i % 2 == 1:
            frame[i] = (0, 0, raw_0_255)  # jeśli u Ciebie CW=G, zmień na (0, raw_0_255, 0)
    draw_frame(frame)


def fade_cw_cycles(limit=22):
    steps_up = 50
    steps_down = 30
    inc = max(1, 256 // steps_up)
    dec = max(1, 256 // steps_down)

    # Rozjaśnianie
    for b in range(0, 256, inc):
        only_cw_scaled_limit(b, limit=limit); time.sleep(0.02)

    # Ściemnianie
    for b in range(255, -1, -dec):
        only_cw_scaled_limit(b, limit=limit); time.sleep(0.04)

    # Końcowe rozjaśnienie do ~50%
    for b in range(0, 129, inc):
        only_cw_scaled_limit(b, limit=limit); time.sleep(0.02)



def effect_all_max():
    # Parzyste (RGB): pełna biel; Nieparzyste (CW/WW): WW+CW
    frame = [(255,255,255) if (i % 2 == 0) else (255,255,0) for i in range(LED_COUNT)]
    draw_frame(frame)

# statyczne
def effect_red_even():        draw_frame_22(frame_fill_even_odd('even', (255,0,0)))
def effect_green_even():      draw_frame_22(frame_fill_even_odd('even', (0,255,0)))
def effect_blue_even():       draw_frame_22(frame_fill_even_odd('even', (0,0,255)))
def effect_orange_even():     draw_frame_22(frame_fill_even_odd('even', (255, 70, 0)))
def effect_lgr_even():        draw_frame_22(frame_fill_even_odd('even', (0,75,255)))
def effect_lbl_even():        draw_frame_22(frame_fill_even_odd('even', (0,255,0)))

def effect_ww_odd():          draw_frame_22(frame_fill_even_odd('odd',  rgb_odd=(255,0,0)))   # WW = R
def effect_cw_odd():          draw_frame_22(frame_fill_even_odd('odd',  rgb_odd=(0,0,255)))   # CW = B
def effect_ww_cw_odd():       draw_frame_22(frame_fill_even_odd('odd',  rgb_odd=(255,0,255))) # WW+CW = R+B

def effect_alternate_white(): draw_frame_22(frame_fill_even_odd('odd', (255,0,255)))

def effect_all_max():
    # Parzyste (RGB): biel RGB; Nieparzyste (whites): WW+CW (R+B)
    frame = [(255,255,255) if (i % 2 == 0) else (255,0,255) for i in range(LED_COUNT)]
    draw_frame_22(frame)


def effect_snake_combo():
    snake_rgb_all()
    snake_rgb_all()
    fade_cw_cycles()           # jak dotąd
    only_cw_scaled_limit(128)  # tylko pierwsze 22 LED-y; reszta 6 zgaszona

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
    "ww_cw_blue": effect_ww_cw_odd,       # alias z pilota
    "alternate_white": effect_ww_cw_odd,  # alias
    "all_max": effect_all_max,
    "snake_combo": effect_snake_combo,
    "idle": lambda: None,
}


# ---------- Worker efektów (z cross-fade’em) ----------
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
            clear(show=True)
            continue
        # cross-fade do podglądu efektu
        if do_fade:
            target = preview_frame(name)
            crossfade_to_frame(target, duration=fade_time, steps=ceil(fade_time * 48))
        # właściwy efekt
        if func:
            func()
            strip.show()

def set_effect(name, fade=True, fade_time=0.5):
    """Wrzuca efekt do kolejki z opcjonalnym cross-fadem."""
    # ostatnia wygrana – czyścimy kolejkę, żeby przejścia były responsywne
    try:
        while True:
            effect_queue.get_nowait()
    except Empty:
        pass
    effect_queue.put({"name": name, "fade": fade, "fade_time": fade_time})

# ---------- IR + presety ----------
ir_dev = None  # uchwyt globalny do zamknięcia w on_exit()

def ir_listener(device_path='/dev/input/event0'):
    global ir_dev
    ir_dev = InputDevice(device_path)
    print(f"Nasłuchiwanie IR na {device_path}...")
    ir_dev.grab()  # opcjonalnie

    poller = select.poll()
    poller.register(ir_dev.fileno(), select.POLLIN)

    debounce_time = 0.4
    last_time = 0.0
    last_code = None

    code_to_action = {
        IR_ON:  lambda: (enable_leds(True), set_effect("snake_combo", fade=True, fade_time=0.6)),
        IR_OFF: lambda: (enable_leds(False), clear_and_flag()),
        IR_RED: lambda: (print("Czerwone parzyste"), set_effect("red")),
        IR_GREEN: lambda: (print("Zielone parzyste"), set_effect("green")),
        IR_BLUE: lambda: (print("Niebieskie parzyste"), set_effect("blue")),
        IR_WW: lambda: (print("WW nieparzyste"), set_effect("ww")),
        IR_WW_CW_BLUE: lambda: (print("WW+CW (nieparzyste)"), set_effect("ww_cw_odd")),
        IR_CW: lambda: (print("CW nieparzyste"), set_effect("cw")),
        IR_ORANGE: lambda: (print("Pomarańczowy"), set_effect("orange")),
        IR_LGR: lambda: (print("Jasny zielony"), set_effect("lgr")),
        IR_LBL: lambda: (print("LBL"), set_effect("lbl")),
        IR_DIM: preset_prev_action,
        IR_BRIGHT: preset_next_action,
    }

    try:
        while running:
            events = poller.poll(200)  # ms; timeout pozwala sprawdzić running
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
        # pojawi się gdy zamkniemy urządzenie w on_exit() — to OK
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

def enable_leds(enable: bool):
    global led_enabled
    with state_lock:
        led_enabled = enable
    if enable:
        print("LED: ON")
        apply_brightness(show=False)
    else:
        print("LED: OFF")
        clear(show=True)

def clear_and_flag():
    clear(show=True)
    try:
        with open("/tmp/led_disable.flag", "w") as f:
            f.write("off")
    except Exception as e:
        print(f"Nie mogę zapisać flagi: {e}")

# --- Preset: poprzedni/następny ---
def preset_prev_action():
    global preset_index, brightness_level
    if preset_index > 0:
        preset_index -= 1
    print(f"Preset jasności: {PRESET_LEVELS[preset_index]}%")
    brightness_level = PRESET_LEVELS[preset_index]
    apply_brightness()

def preset_next_action():
    global preset_index, brightness_level
    if preset_index < len(PRESET_LEVELS) - 1:
        preset_index += 1
    print(f"Preset jasności: {PRESET_LEVELS[preset_index]}%")
    brightness_level = PRESET_LEVELS[preset_index]
    apply_brightness()

# ---------- Uruchomienie / sprzątanie ----------
proc = None  # uchwyt do subprocess

def launch_subprocess():
    global proc
    try:
        proc = subprocess.Popen(["python3", "/home/raczqq/darts-caller/dart-caller-listener.py"])
    except Exception as e:
        print(f"Nie mogę uruchomić listenera darta: {e}")

def on_exit(*_):
    global running, ir_dev, proc
    print("Zamykanie...")
    running = False

    # przerwij blokadę na wejściu
    try:
        if ir_dev:
            ir_dev.close()  # spowoduje OSError w pętli – i wyjście
    except Exception:
        pass

    # zatrzymaj proces potomny
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    # wyczyść LEDy i GPIO
    try:
        clear(show=True)
    except Exception:
        pass
    try:
        GPIO.cleanup()
    except Exception:
        pass
        
if __name__ == "__main__":
    signal.signal(signal.SIGINT, on_exit)   # Ctrl+C
    signal.signal(signal.SIGTERM, on_exit)  # systemd/kill

    worker = threading.Thread(target=effects_worker, daemon=True)
    worker.start()

    #launch_subprocess()
    apply_brightness(show=False)
    set_effect("snake_combo", fade=False)

    try:
        ir_listener('/dev/input/event0')
    finally:
        on_exit()
        # daj chwilę na domknięcie workera
        try:
            worker.join(timeout=1.0)
        except Exception:
            pass
