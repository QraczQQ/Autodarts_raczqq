import RPi.GPIO as GPIO
import time

# Ustawienia
LED_PIN = 27         # GPIO27 (pin 13)
TEMP_THRESHOLD = 65  # próg temperatury w °C

# Konfiguracja GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_str = f.read()
            return int(temp_str) / 1000.0  # Konwersja z milikelwinów do °C
    except FileNotFoundError:
        print("Nie znaleziono pliku z temperaturą.")
        return 0

try:
    while True:
        temp = get_cpu_temp()
        print(f"Aktualna temperatura: {temp:.1f}°C")

        if temp >= TEMP_THRESHOLD:
            GPIO.output(LED_PIN, GPIO.HIGH)  # Zapal diodę
        else:
            GPIO.output(LED_PIN, GPIO.LOW)   # Zgaś diodę

        time.sleep(5)  # Sprawdzaj co 5 sekund

except KeyboardInterrupt:
    print("Zatrzymano ręcznie.")
finally:
    GPIO.cleanup()