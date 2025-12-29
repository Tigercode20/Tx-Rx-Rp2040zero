from machine import UART, Pin
import time

# UART1 @ 9600, RX على GP5
u = UART(1, 9600, rx=Pin(5))

print("UART1 RAW TEST (RX=GP5):")

while True:
    if u.any():
        data = u.read()
        print("RAW:", data)
    time.sleep_ms(50)
