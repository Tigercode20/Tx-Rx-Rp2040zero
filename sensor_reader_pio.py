from machine import UART, Pin, Timer
import struct
import time
import rp2

# --- 1. إعداد PIO لعمل UART ثالث (للـ RF Module) ---
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def uart_tx():
    # Start bit
    pull()              .side(0) [7]
    # Data bits (8 bits)
    set(x, 7)           .side(0) [6]
    label("bitloop")
    out(pins, 1)                 [6]
    jmp(x_dec, "bitloop")        [6]
    # Stop bits
    nop()               .side(1) [6]

class PIOUART:
    def __init__(self, sm_id, pin, baud):
        self.pin = Pin(pin, Pin.OUT)
        self.sm = rp2.StateMachine(sm_id, uart_tx, freq=8 * baud, sideset_base=self.pin, out_base=self.pin)
        self.sm.active(1)
    
    def write(self, s):
        if isinstance(s, str):
            s = s.encode('utf-8')
        for byte in s:
            self.sm.put(byte)

# --- 2. إعدادات المنافذ Hardware ---
uart_wit = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))
uart_pod = UART(1, baudrate=115200, tx=Pin(4), rx=Pin(5))
# إنشاء UART2 عبر PIO على Pin 8 (لـ RF Module)
uart_rf = PIOUART(0, pin=8, baud=9600)

# --- 3. دوال البروتوكول ---
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
    packet = bytearray([0xA8, 0xE5, 0x48, 0x00, 0x02]) # Header A8E5, Length 72, Ver 0.2
    packet.extend(bytearray(32)) # Main frame empty
    sub_frame = bytearray(32)
    sub_frame[0] = 0x01 # Sub-frame header
    packet.extend(sub_frame)
    packet.append(0x00) # Null command order
    crc = calc_crc16(packet)
    packet.append((crc >> 8) & 0xFF)
    packet.append(crc & 0xFF)
    return packet

# --- 4. الحالات والبيانات ---
wit = {"ax":0, "ay":0, "az":0, "pres_h":0, "gps_h":0, "lon":0, "lat":0, "head":0, "speed":0}
pod = {"rx":0, "ry":0, "rz":0, "ar":0, "ap":0, "ay":0, "z":1.0}

last_req = 0
pod_buffer = bytearray()

print("Bridge Active: WIT(UART0) + POD(UART1) -> RF(PIO_GP8) + USB")

while True:
    curr = time.ticks_ms()
    
    # طلب بيانات الجيمبال كل 50ms (تردد 20Hz)
    if time.ticks_diff(curr, last_req) > 50:
        uart_pod.write(get_request_packet())
        last_req = curr

    # معالجة بيانات WIT Motion
    if uart_wit.any():
        raw_wit = uart_wit.read()
        for i in range(len(raw_wit)-10):
            if raw_wit[i] == 0x55:
                f = raw_wit[i:i+11]
                if (sum(f[:10]) & 0xFF) == f[10]: # Checksum validation
                    t, d = f[1], f[2:10]
                    if t == 0x53: # Angles
                        v = struct.unpack('<hhh', d[:6])
                        wit["ax"], wit["ay"], wit["az"] = v[0]*180/32768, v[1]*180/32768, v[2]*180/32768
                    elif t == 0x56: # Pressure/Height
                        wit["pres_h"] = struct.unpack('<i', d[4:8])[0] / 100.0
                    elif t == 0x57: # GPS
                        lon, lat = struct.unpack('<ii', d)
                        wit["lon"], wit["lat"] = lon/1e7, lat/1e7
                    elif t == 0x58: # Speed/Heading
                        h, y, v = struct.unpack('<hhi', d)
                        wit["gps_h"], wit["head"], wit["speed"] = h/10, y/10, v/1000

    # معالجة بيانات Pod (Gimbal)
    if uart_pod.any():
        pod_buffer.extend(uart_pod.read())
        while len(pod_buffer) >= 72:
            if pod_buffer[0] == 0x8A and pod_buffer[1] == 0x5E: # GCU Header
                frame = pod_buffer[:72]
                # استخراج الزوايا النسبية (12-17) والمطلقة (18-23)
                pod["rx"], pod["ry"], pod["rz"] = struct.unpack('<hhh', frame[12:18])
                pod["rx"], pod["ry"], pod["rz"] = pod["rx"]*0.01, pod["ry"]*0.01, pod["rz"]*0.01
                pod["ar"], pod["ap"] = struct.unpack('<hh', frame[18:22])
                pod["ay"] = struct.unpack('<H', frame[22:24])[0]
                pod["ar"], pod["ap"], pod["ay"] = pod["ar"]*0.01, pod["ap"]*0.01, pod["ay"]*0.01
                pod["z"] = struct.unpack('<H', frame[59:61])[0] * 0.1 # Zoom
                pod_buffer = pod_buffer[72:]
            else:
                pod_buffer = pod_buffer[1:]

    # تجميع وإرسال البيانات (CSV Format)
    data_line = "{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.1f},{:.2f},{:.2f},{:.2f},{:.2f},{:.1f},{:.7f},{:.7f},{:.1f},{:.2f}\n".format(
        pod['rx'], pod['ry'], pod['rz'], pod['ar'], pod['ap'], pod['ay'], pod['z'],
        wit['ax'], wit['ay'], wit['az'], wit['pres_h'], wit['gps_h'], 
        wit['lon'], wit['lat'], wit['head'], wit['speed']
    )
    
    uart_rf.write(data_line) # إرسال لاسلكي عبر PIO UART
    print(data_line, end='') # إرسال محلي عبر USB للـ Terminal
    
    time.sleep(0.02)
