from machine import UART, Pin
import struct
import time
import rp2

# --- PIO UART for RF Module ---
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def uart_tx():
    # Transmit one byte: Start bit + 8 data bits + Stop bit
    pull(block)         .side(1)      # Wait for data, idle high
    set(x, 9)           .side(0) [7]  # Start bit (low), prepare for 10 bits total
    label("bitloop")
    out(pins, 1)                 [6]  # Shift out one bit
    jmp(x_dec, "bitloop")        [6]  # Loop for all bits
    # Note: Stop bit is sent as last shifted bit (always 1)

class PIOUART:
    def __init__(self, sm_id, pin_num, baud):
        self.pin = Pin(pin_num, Pin.OUT, value=1)
        self.sm = rp2.StateMachine(
            sm_id, 
            uart_tx, 
            freq=8*baud,
            sideset_base=self.pin,
            out_base=self.pin
        )
        self.sm.active(1)
    
    def write(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        for byte in data:
            # Add stop bit (shift in a 1 at the beginning)
            self.sm.put((byte << 1) | 0x200)

# --- Hardware Setup ---
uart_wit = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))
uart_pod = UART(1, baudrate=115200, tx=Pin(4), rx=Pin(5))
uart_rf = PIOUART(0, pin_num=8, baud=9600)

# --- Protocol Functions ---
def calc_crc16(data):
    crc = 0
    crc_table = [0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50a5, 0x60c6, 0x70e7,
                 0x8108, 0x9129, 0xa14a, 0xb16b, 0xc18c, 0xd1ad, 0xe1ce, 0xf1ef]
    for byte in data:
        da = (crc >> 12) & 0x0F
        crc = (crc << 4) & 0xFFFF
        crc ^= crc_table[da ^ (byte >> 4)]
        da = (crc >> 12) & 0x0F
        crc = (crc << 4) & 0xFFFF
        crc ^= crc_table[da ^ (byte & 0x0F)]
    return crc

def get_request_packet():
    packet = bytearray([0xA8, 0xE5, 0x48, 0x00, 0x02])
    packet.extend(bytearray(32))
    sub_frame = bytearray(32)
    sub_frame[0] = 0x01
    packet.extend(sub_frame)
    packet.append(0x00)
    crc = calc_crc16(packet)
    packet.append((crc >> 8) & 0xFF)
    packet.append(crc & 0xFF)
    return packet

# --- Data Storage ---
wit = {"ax":0, "ay":0, "az":0, "pres_h":0, "gps_h":0, "lon":0, "lat":0, "head":0, "speed":0}
pod = {"rx":0, "ry":0, "rz":0, "ar":0, "ap":0, "ay":0, "z":1.0}
pod_buffer = bytearray()
last_req = 0

print("Bridge Active: WIT(UART0) + POD(UART1) -> RF(PIO_GP8)")

# --- Main Loop ---
try:
    while True:
        curr = time.ticks_ms()
        
        # Request gimbal data every 50ms
        if time.ticks_diff(curr, last_req) > 50:
            uart_pod.write(get_request_packet())
            last_req = curr

        # Process WIT data
        if uart_wit.any():
            raw_wit = uart_wit.read()
            for i in range(len(raw_wit)-10):
                if raw_wit[i] == 0x55:
                    f = raw_wit[i:i+11]
                    if len(f) == 11 and (sum(f[:10]) & 0xFF) == f[10]:
                        t, d = f[1], f[2:10]
                        if t == 0x53:  # Angles
                            v = struct.unpack('<hhh', d[:6])
                            wit["ax"], wit["ay"], wit["az"] = v[0]*180/32768, v[1]*180/32768, v[2]*180/32768
                        elif t == 0x56:  # Pressure
                            wit["pres_h"] = struct.unpack('<i', d[4:8])[0] / 100.0
                        elif t == 0x57:  # GPS
                            lon, lat = struct.unpack('<ii', d)
                            wit["lon"], wit["lat"] = lon/1e7, lat/1e7
                        elif t == 0x58:  # Heading/Speed
                            h, y, v = struct.unpack('<hhi', d)
                            wit["gps_h"], wit["head"], wit["speed"] = h/10, y/10, v/1000

        # Process Pod data
        if uart_pod.any():
            pod_buffer.extend(uart_pod.read())
            while len(pod_buffer) >= 72:
                if pod_buffer[0] == 0x8A and pod_buffer[1] == 0x5E:
                    frame = pod_buffer[:72]
                    pod["rx"], pod["ry"], pod["rz"] = struct.unpack('<hhh', frame[12:18])
                    pod["rx"], pod["ry"], pod["rz"] = pod["rx"]*0.01, pod["ry"]*0.01, pod["rz"]*0.01
                    pod["ar"], pod["ap"] = struct.unpack('<hh', frame[18:22])
                    pod["ay"] = struct.unpack('<H', frame[22:24])[0]
                    pod["ar"], pod["ap"], pod["ay"] = pod["ar"]*0.01, pod["ap"]*0.01, pod["ay"]*0.01
                    pod["z"] = struct.unpack('<H', frame[59:61])[0] * 0.1
                    pod_buffer = pod_buffer[72:]
                else:
                    pod_buffer = pod_buffer[1:]

        # Format and transmit data
        data_line = "{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.1f},{:.2f},{:.2f},{:.2f},{:.2f},{:.1f},{:.7f},{:.7f},{:.1f},{:.2f}\n".format(
            pod['rx'], pod['ry'], pod['rz'], pod['ar'], pod['ap'], pod['ay'], pod['z'],
            wit['ax'], wit['ay'], wit['az'], wit['pres_h'], wit['gps_h'], 
            wit['lon'], wit['lat'], wit['head'], wit['speed']
        )
        
        uart_rf.write(data_line)
        print(data_line, end='')
        
        time.sleep(0.02)

except KeyboardInterrupt:
    print("\nStopped by user")
except Exception as e:
    print(f"Error: {e}")
    import sys
    sys.print_exception(e)
finally:
    print("Program ended")
