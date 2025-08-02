from rpi_ws281x import PixelStrip, Color
from evdev import InputDevice, ecodes  # <-- dodany import dla evdev
import RPi.GPIO as GPIO
import time
import threading  # <-- dodany import dla threading

# --- Konfiguracja paska ---
LED_COUNT = 22
LED_PIN = 18
LED_DMA = 10
LED_FREQ_HZ = 1000000   # częstotliwość
LED_BRIGHTNESS = 255
LED_INVERT = False
LED_CHANNEL = 0

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

# --- Inicjalizacja stripu ---
strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# --- Flaga stanu paska ---
led_enabled = True
lock = threading.Lock()
brightness_level = 100  # początkowo 100%
current_effect = None   # nazwa ostatnio uruchomionej funkcji

def scale(value):
    return int(value * (brightness_level / 100))


def show_red_even():
    for i in range(0, LED_COUNT, 2):
        set_led(i, scale(255), 0, 0)
    for i in range(1, LED_COUNT, 2):
        set_led(i, 0, 0, 0)
    strip.show()

def show_green_even():
    for i in range(0, LED_COUNT, 2):
        set_led(i, 0, 0, scale(255))
    for i in range(1, LED_COUNT, 2):
        set_led(i, 0, 0, 0)
    strip.show()

def show_blue_even():
    for i in range(0, LED_COUNT, 2):
        set_led(i, 0, scale(255), 0)
    for i in range(1, LED_COUNT, 2):
        set_led(i, 0, 0, 0)
    strip.show()
    
def show_orange_even():
    for i in range(0, LED_COUNT, 2):
        set_led(i, scale(255), 0, scale(70))
    for i in range(1, LED_COUNT, 2):
        set_led(i, 0, 0, 0)
    strip.show()
#RED, BLUE, GREEN
def show_lgr_even():
    for i in range(0, LED_COUNT, 2):
        set_led(i, 0, scale(75), scale(255))
    for i in range(1, LED_COUNT, 2):
        set_led(i, 0, 0, 0)
    strip.show()

def show_lbl_even():
    for i in range(0, LED_COUNT, 2):
        set_led(i, 0, scale(255), 0)
    for i in range(1, LED_COUNT, 2):
        set_led(i, 0, 0, 0)
    strip.show()

def show_ww_odd():
    for i in range(LED_COUNT):
        if i % 2 == 1:
            set_led(i, scale(255), 0, 0)  # WW = R kanał
        else:
            set_led(i, 0, 0, 0)
    strip.show()

def show_cw_odd():
    for i in range(LED_COUNT):
        if i % 2 == 1:
            set_led(i, 0, scale(255), 0)  # CW = G kanał
        else:
            set_led(i, 0, 0, 0)
    strip.show()

def show_ww_cw_blue_even():
    for i in range(0, LED_COUNT, 2):
        set_led(i, scale(255), scale(255), 0)  # WW + CW
    for i in range(1, LED_COUNT, 2):
        set_led(i, 0, 0, 0)
    strip.show()

def set_led(i, r, g, b):
    strip.setPixelColor(i, Color(r, g, b))

def clear():
    for i in range(LED_COUNT):
        set_led(i, 0, 0, 0)
    strip.show()

# --- Etap 1: Wąż RGB na parzystych indeksach ---
def snake_rgb(delay=0.03):
    # 1. Do przodu - zielony
    for i in range(0, LED_COUNT, 2):  # RGB = parzyste
        set_led(i, 0, scale(255), 0)  # Zielony
        strip.show()
        time.sleep(delay)

    # 2. Do tyłu - czerwony
    for i in range(LED_COUNT - 2, -1, -2):
        set_led(i, scale(255), 0, 0)  # Czerwony
        strip.show()
        time.sleep(delay)

    # 3. Do przodu - niebieski
    for i in range(0, LED_COUNT, 2):
        set_led(i, 0, 0, scale(255))  # Niebieski
        strip.show()
        time.sleep(delay)

    # 4. Do tyłu - biały
    for i in range(LED_COUNT - 2, -1, -2):
        set_led(i, scale(255), scale(255), scale(255))  # Biały
        strip.show()
        time.sleep(delay)


# --- Etap 2: Wygaśnięcie RGB ---
def fade_out_rgb(delay=0.02):
    for brightness in range(scale(255), -1, -15):
        for i in range(0, LED_COUNT, 2):
            set_led(i, brightness, brightness, brightness)
        strip.show()
        time.sleep(delay)
    for i in range(0, LED_COUNT, 2):
        set_led(i, 0, 0, 0)
    strip.show()

# --- Etap 3: CW na nieparzystych indeksach ---
def only_cw():
    for i in range(LED_COUNT):
        if i % 2 == 1:  # nieparzyste indeksy = CW/WW
            set_led(i, 0, scale(255), 0)  # CW = kanał G
        else:
            set_led(i, 0, 0, 0)  # RGB wygaszone
    strip.show()

# --- Etap 4: WW na nieparzystych indeksach ---
def only_ww():
    for i in range(LED_COUNT):
        if i % 2 == 1:  # nieparzyste indeksy = CW/WW
            set_led(i, scale(255), 0, 0)  # WW = kanał R
        else:
            set_led(i, 0, 0, 0)  # RGB wygaszone
    strip.show()
    
# --- Etap 5: CW i WW naprzemiennie na nieparzystych indeksach ---
def alternate_white(delay=0.02):
    for i in range(1, LED_COUNT, 2):
        set_led(i, scale(255), scale(255), 0)  # WW (R) + CW (G) = żółty
    for i in range(0, LED_COUNT, 2):
        set_led(i, 0, 0, 0)  # RGB = wygaszone
    strip.show()
    time.sleep(delay)

# --- Etap 6: Wszystkie LED na max ---
def all_max():
    for i in range(LED_COUNT):
        set_led(i, scale(255), scale(255), scale(255))
    strip.show()
    
    # --- Etap 7: Tylko RGB ---
def rgb_only_on():
    for i in range(0, LED_COUNT, 2):  # Parzyste indeksy = RGB
        set_led(i, scale(255), scale(255), scale(255))
    for i in range(1, LED_COUNT, 2):  # Nieparzyste = CW/WW = wyłączone
        set_led(i, 0, 0, 0)
    strip.show()
    
        # --- Etap 8: Tylko RGB + CW ---
def rgb_cw_only_on():
    for i in range(0, LED_COUNT, 2):  # Parzyste indeksy = RGB
        set_led(i, scale(255), scale(255), scale(255))
    for i in range(1, LED_COUNT, 2):  # Nieparzyste = CW/WW = wyłączone
        set_led(i, 0, scale(255), 0)
    strip.show()
    
    # --- Etap 9: Tylko RGB + WW ---
def rgb_ww_only_on():
    for i in range(0, LED_COUNT, 2):  # Parzyste indeksy = RGB
        set_led(i, scale(255), scale(255), scale(255))
    for i in range(1, LED_COUNT, 2):  # Nieparzyste = CW/WW = wyłączone
        set_led(i, scale(255), 0, 0)
    strip.show()
    
    # --- Obsługa pilota IR ---
def ir_listener(device_path='/dev/input/event0'):
    global led_enabled, brightness_level, current_effect

    dev = InputDevice(device_path)
    print(f"Nasłuchiwanie IR na {device_path}...")

    for event in dev.read_loop():
        if event.type == ecodes.EV_MSC and event.code == ecodes.MSC_SCAN:
            sc = event.value
            print(f"[IR] Otrzymano kod: {hex(sc)}")

            with lock:
                if sc == IR_ON:
                    led_enabled = True
                    run_effect("cw")
                    print("LED: ON")
                elif sc == IR_OFF:
                    led_enabled = False
                    clear()
                    print("LED: OFF")
                elif not led_enabled:
                    print("LED wyłączone — ignoruję polecenie.")
                elif sc == IR_RED:
                    print("Czerwone diody na parzystych indeksach")
                    run_effect("red")
                elif sc == IR_GREEN:
                    print("Zielone diody na parzystych indeksach")
                    run_effect("green")
                elif sc == IR_BLUE:
                    print("Niebieskie diody na parzystych indeksach")
                    run_effect("blue")
                elif sc == IR_WW:
                    print("WW diody na nieparzystych")
                    run_effect("ww")
                elif sc == IR_WW_CW_BLUE:
                    print("WW+CW")
                    run_effect("alternate_white")
                elif sc == IR_CW:
                    print("CW diody na nieparzystych")
                    run_effect("cw")
                elif sc == IR_ORANGE:
                    print("Pomarańczowy kolor")
                    run_effect("orange")
                elif sc == IR_LGR:
                    print("Jasny zielony kolor")
                    run_effect("lgr")
                elif sc == 0xef1d:  # Przyciemnienie
                    if brightness_level > 10:
                        brightness_level -= 10
                        print(f"Przyciemniono do {brightness_level}%")
                        if current_effect:
                            run_effect(current_effect)
                    else:
                        print("Minimalna jasność (10%)")
                elif sc == 0xef1c:  # Rozjaśnienie
                    if brightness_level < 100:
                        brightness_level += 10
                        print(f"Rozjaśniono do {brightness_level}%")
                        if current_effect:
                            run_effect(current_effect)
                    else:
                        print("Maksymalna jasność (100%)")
    
                else:
                    print("Nieznany kod — brak akcji")

def run_effect(name):
    global current_effect
    current_effect = name
    if name == "red":
        show_red_even()
    elif name == "green":
        show_green_even()
    elif name == "blue":
        show_blue_even()
    elif name == "ww":
        show_ww_odd()
    elif name == "cw":
        show_cw_odd()
    elif name == "orange":
        show_orange_even()
    elif name == "lgr":
        show_lgr_even()        
    elif name == "ww_cw_blue":
        show_ww_cw_blue_even()
    elif name == "alternate_white":
        alternate_white()
    elif name == "all_max":
        all_max()


# --- Program główny ---
try:
    """time.sleep(2)"""
    """clear()"""
    snake_rgb()
    snake_rgb()
    snake_rgb()
    clear()
    ir_listener('/dev/input/event0')  # <-- dostosuj ścieżkę jeśli trzeba
    
    """time.sleep(1)
    fade_out_rgb()
    only_cw()
    time.sleep(2)
    only_ww()
    time.sleep(2)
    alternate_white()
    time.sleep(2)
    all_max()
    time.sleep(2)
    rgb_only_on()
    time.sleep(2)
    rgb_ww_only_on()
    time.sleep(2)
    rgb_cw_only_on()
    time.sleep(2)
    only_cw()"""
    

except KeyboardInterrupt:
      clear()

finally:
    GPIO.cleanup()
