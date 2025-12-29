from machine import UART, Pin
import struct, time, rp2

# -------- PIO UART لـ RFD900 TX (GP8) --------
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def uart_tx():
    pull(block) .side(1)
    set(x, 9) .side(0) [7]
    label("bitloop")
    out(pins, 1) [6]
    jmp(x_dec, "bitloop") [6]

class PIOUART:
    def __init__(self, sm_id, pin_num, baud=9600):
        self.pin = Pin(pin_num, Pin.OUT, value=1)
        self.sm = rp2.StateMachine(sm_id, uart_tx, freq=8*baud,
                                   sideset_base=self.pin, out_base=self.pin)
        self.sm.active(1)
    
    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        for byte in data:
            self.sm.put((byte << 1) | 0x200)

# -------- CRC16 لـ POD الأصلية --------
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

# -------- CRC16 CCITT للبروتوكول الباينري --------
def crc16_ccitt(data):
    crc = 0x1D0F
    poly = 0x1021
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

# -------- الأجهزة --------
uart_wit = UART(0, 9600, tx=Pin(0), rx=Pin(1))       # WIT
uart_pod = UART(1, 115200, tx=Pin(4), rx=Pin(5))     # D-80AI
uart_rf  = PIOUART(0, 8, 9600)                       # RFD900
led = Pin(25, Pin.OUT)

# -------- المتغيرات الحية --------
pod_data = [0.0]*7  # rx, ry, rz, ar, ap, ay, z
wit_data = [0.0]*6  # ax, ay, az, pres_h, gps_h, head
packet_cnt = 0
last_flags = 0
pod_buf = bytearray()
last_req = 0

print("BINARY TX v2.0 | 28B@50Hz | RFD900 Ready")

# -------- طلب بيانات POD --------
def get_pod_request():
    packet = bytearray([0xA8, 0xE5, 0x48, 0x00, 0x02])
    packet.extend(bytearray(32))       # main frame (32 بايت صفر)
    sub_frame = bytearray(32)
    sub_frame[0] = 0x01
    packet.extend(sub_frame)
    packet.append(0x00)
    crc = calc_crc16(packet)
    packet.append((crc >> 8) & 0xFF)
    packet.append(crc & 0xFF)
    return packet

# -------- بناء الحزمة الباينري (28 بايت) --------
def build_binary_packet():
    global packet_cnt, last_flags
    ts = int(time.ticks_ms() % 65536)
    
    # Flags: bit0=WIT, bit1=POD, bit2=GPS/height
    flags = 0
    if any(abs(x) > 0.01 for x in wit_data):
        flags |= 1
    if any(abs(x) > 0.1 for x in pod_data[:6]):
        flags |= 2
    if abs(wit_data[3]) > 1:
        flags |= 4
    last_flags = flags
    
    pkt = bytearray(28)
    # Sync
    pkt[0:2] = b'\xAA\x55'
    # Counter + Timestamp
    struct.pack_into('<HH', pkt, 2, packet_cnt, ts)
    # Flags
    pkt[6] = flags
    
    # POD: 6x int16 (*100) + zoom (0-255)
    pod_scaled = [int(x*100) for x in pod_data[:6]]
    struct.pack_into('<hhhhhh', pkt, 7, *pod_scaled)
    zoom_byte = int(pod_data[6]*2.55)
    if zoom_byte < 0:   zoom_byte = 0
    if zoom_byte > 255: zoom_byte = 255
    pkt[13] = zoom_byte
    
    # WIT: 6x int16 (*100)
    wit_scaled = [int(x*100) for x in wit_data]
    struct.pack_into('<hhhhhh', pkt, 14, *wit_scaled)
    
    # CRC
    crc = crc16_ccitt(pkt[:26])
    struct.pack_into('<H', pkt, 26, crc)
    
    packet_cnt = (packet_cnt + 1) & 0xFFFF
    return pkt

# -------- الحلقة الرئيسية --------
while True:
    now = time.ticks_ms()
    
    # طلب POD كل 20ms (50Hz)
    if time.ticks_diff(now, last_req) > 20:
        uart_pod.write(get_pod_request())
        last_req = now
    
    # --- قراءة WIT ---
    if uart_wit.any():
        raw = uart_wit.read()
        for i in range(len(raw) - 10):
            if raw[i] == 0x55:
                f = raw[i:i+11]
                if len(f) == 11 and (sum(f[:10]) & 0xFF) == f[10]:
                    t = f[1]
                    d = f[2:10]
                    if t == 0x53:  # Angles
                        v = struct.unpack('<hhh', d[:6])
                        wit_data[0] = v[0]*180/32768
                        wit_data[1] = v[1]*180/32768
                        wit_data[2] = v[2]*180/32768
                    elif t == 0x56:  # Pressure height
                        wit_data[3] = struct.unpack('<i', d[4:8])[0] / 100.0
                    elif t == 0x58:  # Heading & speed
                        h, y, s = struct.unpack('<hhi', d)
                        wit_data[5] = h/10.0      # heading
                        wit_data[4] = s/1000.0    # speed
    
    # --- قراءة POD ---
    if uart_pod.any():
        pod_buf.extend(uart_pod.read())
        while len(pod_buf) >= 72:
            if pod_buf[0] == 0x8A and pod_buf[1] == 0x5E:
                frame = pod_buf[:72]
                pod_data[0], pod_data[1], pod_data[2] = struct.unpack('<hhh', frame[12:18])
                pod_data[3], pod_data[4] = struct.unpack('<hh', frame[18:22])
                pod_data[5] = struct.unpack('<H', frame[22:24])[0]
                pod_data[6] = struct.unpack('<H', frame[59:61])[0] * 0.1
                # scaling
                for i in range(6):
                    pod_data[i] = pod_data[i] * 0.01
                pod_buf = pod_buf[72:]
            else:
                pod_buf = pod_buf[1:]
    
    # --- إرسال حزمة باينري 50Hz عبر RF + طباعة HEX ---
    packet = build_binary_packet()
    uart_rf.write(packet)
    led.value(1)
    
    hex_str = ' '.join('{:02X}'.format(b) for b in packet)
    print("CNT=%5d FLAGS=%d (0x%02X) T=%5d | %s" %
          (packet_cnt, last_flags, last_flags, now & 0xFFFF, hex_str))
    
    led.value(0)
    time.sleep_ms(20)
