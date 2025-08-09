import time
from rpi_ws281x import PixelStrip, Color, ws

# --- konfiguracja LED ---
LED_COUNT = 22
LED_PIN = 18
LED_DMA = 10
LED_FREQ_HZ = 800_000   # dostosuj, jeśli trzeba
LED_BRIGHTNESS = 128       # umiarkowanie, łatwiej ocenić kolory
LED_INVERT = False
LED_CHANNEL = 0

# mapowanie nazw dla czytelnego wyniku
TYPE_LABELS = {
    #ws.WS2811_STRIP_RGB: "WS2811_STRIP_RGB",
    #ws.WS2811_STRIP_RBG: "WS2811_STRIP_RBG",
    #ws.WS2811_STRIP_GRB: "WS2811_STRIP_GRB",
    #ws.WS2811_STRIP_GBR: "WS2811_STRIP_GBR",
    ws.WS2811_STRIP_BRG: "WS2811_STRIP_BRG",
    #ws.WS2811_STRIP_BGR: "WS2811_STRIP_BGR",
}

TYPES = list(TYPE_LABELS.keys())

def clear(strip):
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()

def set_even_rgb(strip, rgb):
    r, g, b = rgb
    for i in range(LED_COUNT):
        if i % 2 == 0:  # parzyste = RGB
            strip.setPixelColor(i, Color(r, g, b))
        else:           # nieparzyste (CW/WW) wyłączone
            strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()

def set_odd_whites(strip, ww, cw):
    """WW=R, CW=G; B niewykorzystywany na nieparzystych."""
    for i in range(LED_COUNT):
        if i % 2 == 1:  # nieparzyste = CW/WW
            strip.setPixelColor(i, Color(ww, 0, cw))
        else:           # parzyste (RGB) wyłączone
            strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()

def show_rgb_sequence_even(strip):
    set_even_rgb(strip, (255, 0, 0))
    print("Powinno być: RED na PARZYSTYCH."); time.sleep(1.5)

    set_even_rgb(strip, (0, 255, 0))
    print("Powinno być: GREEN na PARZYSTYCH."); time.sleep(1.5)

    set_even_rgb(strip, (0, 0, 255))
    print("Powinno być: BLUE na PARZYSTYCH."); time.sleep(1.5)

def show_whites_sequence_odd(strip):
    set_odd_whites(strip, ww=255, cw=0)
    print("Powinno być: WW (ciepła biel) na NIEPARZYSTYCH."); time.sleep(1.5)

    set_odd_whites(strip, ww=0, cw=255)
    print("Powinno być: CW (zimna biel) na NIEPARZYSTYCH."); time.sleep(1.5)

    set_odd_whites(strip, ww=255, cw=255)
    print("Powinno być: WW+CW na NIEPARZYSTYCH."); time.sleep(1.5)

if __name__ == "__main__":
    selected_type = None

    for t in TYPES:
        print("="*60)
        print(f"Test STRIP_TYPE: {TYPE_LABELS[t]}")
        strip = PixelStrip(
            LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT,
            LED_BRIGHTNESS, LED_CHANNEL, strip_type=t
        )
        strip.begin()
        try:
            # 1) Test RGB na parzystych
            show_rgb_sequence_even(strip)
            ans_rgb = input("Czy kolejno było RED→GREEN→BLUE na PARZYSTYCH? [y/N]: ").strip().lower()
            if ans_rgb != "y":
                clear(strip); time.sleep(0.5)
                continue  # spróbuj następnego STRIP_TYPE

            # 2) Test CW/WW na nieparzystych (WW=R, CW=G)
            show_whites_sequence_odd(strip)
            ans_white = input("Czy kolejno było WW→CW→WW+CW na NIEPARZYSTYCH? [y/N]: ").strip().lower()
            if ans_white == "y":
                selected_type = t
                print("✅ Wygląda dobrze, kończę testy.")
                clear(strip)
                break  # PO OTRZYMANIU 'Y' POMIJAMY RESZTĘ TYPÓW
        finally:
            clear(strip)
            time.sleep(0.8)

    print("="*60)
    if selected_type is not None:
        print(f"✅ Poprawny STRIP_TYPE: {TYPE_LABELS[selected_type]}")
    else:
        print("❌ Nie znaleziono typu spełniającego oba testy (RGB parzyste oraz WW/CW nieparzyste).")
        print("Sprawdź okablowanie, częstotliwość, albo czy WW=Ciepła (R), CW=Zimna (G) na Twojej taśmie.")
