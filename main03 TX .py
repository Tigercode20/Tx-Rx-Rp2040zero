from machine import UART, Pin
import struct, time, rp2

# ═══════════════════════════════════════════════════════════════════
# بنية البيانات المرسلة - 46 بايت (محدّث v4.0!)
# ═══════════════════════════════════════════════════════════════════
# البايت 0-1:   Header (0xAA 0x55)
# البايت 2-3:   Packet Counter (uint16)
# البايت 4-5:   Timestamp (uint16)
# البايت 6:     Flags
# ────────────────────────────────────────────────────────
# بيانات الجيمبال (POD) - 13 بايت:
# البايت 7-8:   Relative AngleX (int16 ÷ 100) - 2 خانة عشرية
# البايت 9-10:  Relative AngleY (int16 ÷ 100) - 2 خانة عشرية
# البايت 11-12: Relative AngleZ (int16 ÷ 100) - 2 خانة عشرية
# البايت 13:    Zoom (uint8, 0-100 → 0-255)
# البايت 14-15: Absolute Roll (int16 ÷ 100) - 2 خانة عشرية
# البايت 16-17: Absolute Pitch (int16 ÷ 100) - 2 خانة عشرية
# البايت 18-19: Absolute Yaw (int16 ÷ 100) - 2 خانة عشرية
# ────────────────────────────────────────────────────────
# بيانات الحساس (WIT) - 24 بايت (9 قيم):
# البايت 20-21: Angle X (int16 ÷ 100) - 2 خانة عشرية
# البايت 22-23: Angle Y (int16 ÷ 100) - 2 خانة عشرية
# البايت 24-25: Angle Z (int16 ÷ 100) - 2 خانة عشرية
# البايت 26-29: Latitude (int32 ÷ 10,000,000) - 7 خانات عشرية ✅ جديد!
# البايت 30-33: Longitude (int32 ÷ 10,000,000) - 7 خانات عشرية ✅ جديد!
# البايت 34-37: GPS Altitude (int32 ÷ 100) - 2 خانة عشرية ✅ جديد!
# البايت 38-39: Pressure Height (int16 ÷ 100) - 2 خانة عشرية
# البايت 40-41: GPS Speed (int16 ÷ 100) - 2 خانة عشرية
# البايت 42-43: Heading (int16 ÷ 100) - 2 خانة عشرية
# ────────────────────────────────────────────────────────
# البايت 44-45: CRC16-CCITT
# ═══════════════════════════════════════════════════════════════════

# ────────────────────────────────────────────────────────
# 1. تعريف محرك الـ PIO لمحاكاة UART TX على طرف (GP8)
# ────────────────────────────────────────────────────────
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def uart_tx():
    pull(block)            .side(1)       # الانتظار حتى تتوفر بيانات
    set(x, 9)              .side(0) [7]   # إرسال Start bit
    label("bitloop")
    out(pins, 1)                    [6]   # إخراج بت واحد
    jmp(x_dec, "bitloop")           [6]   # تكرار العملية

class PIOUART:
    def __init__(self, sm_id, pin_num, baud=9600):
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
            data = data.encode()
        for byte in data:
            self.sm.put((byte << 1) | 0x200)

# ────────────────────────────────────────────────────────
# 2. دوال CRC
# ────────────────────────────────────────────────────────
def calc_crc16_pod(data):
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

def crc16_ccitt_binary(data):
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

# ────────────────────────────────────────────────────────
# 3. إعداد الأجهزة
# ────────────────────────────────────────────────────────
# UART0: يُستخدم لكل من:
#   - TX (GP0): إرسال البيانات للراديو/الطرف الآخر @ 57600 baud
#   - RX (GP1): استقبال بيانات من حساس WIT @ 9600 baud
# ⚠️ يجب استخدام نفس UART instance لكليهما!
# ملاحظة: WIT يعمل على 9600 حسب الإعدادات، لكن UART سيعمل على 57600
# إذا كانت هناك مشاكل في استقبال WIT، غيّر إعداداته إلى 57600

uart0 = UART(0, baudrate=57600, tx=Pin(0), rx=Pin(1))
uart_rf = uart0   # الراديو يستخدم TX @ 57600
uart_wit = uart0  # WIT يستخدم RX @ 57600 (يُفضل ضبط WIT على 57600)

# UART1: الجيمبال POD (TX/RX @ 115200 baud)
uart_pod = UART(1, baudrate=115200, tx=Pin(4), rx=Pin(5))

# ملاحظة: يمكنك الآن مسح كلاس PIOUART و uart_tx الخاص بالـ PIO لتنظيف الكود.
led = Pin(25, Pin.OUT)

# ────────────────────────────────────────────────────────
# 4. المتغيرات
# ────────────────────────────────────────────────────────
pod_data = [0.0]*7  # Relative(3) + Absolute(3) + Zoom(1)
wit_data = [0.0]*9  # Angles(3) + GPS(3) + Others(3)
                    # [0:3] = AngleX, AngleY, AngleZ
                    # [3] = Latitude
                    # [4] = Longitude
                    # [5] = GPS Altitude
                    # [6] = Pressure Height
                    # [7] = GPS Speed
                    # [8] = Heading
packet_cnt = 0
last_flags = 0
pod_buffer = bytearray()
wit_buffer = bytearray()  # ✅ إضافة buffer للـ WIT
last_pod_req_time = 0

DEBUG_MODE = True  # ✅ TRUE = يطبع HEX للـ debugging

print("BINARY TX v4.0 | 46B@50Hz | RFD900 Ready | With GPS Data")
if DEBUG_MODE:
    print("⚠️  DEBUG MODE ENABLED - HEX output active")
else:
    print("✅ PRODUCTION MODE - Binary only")

def get_pod_request_packet():
    packet = bytearray([0xA8, 0xE5, 0x48, 0x00, 0x02])
    packet.extend(bytearray(32)) 
    sub_frame = bytearray(32)
    sub_frame[0] = 0x01
    packet.extend(sub_frame)
    packet.append(0x00)
    crc = calc_crc16_pod(packet)
    packet.append((crc >> 8) & 0xFF)
    packet.append(crc & 0xFF)
    return packet

def build_telemetry_packet():
    global packet_cnt, last_flags
    ts = int(time.ticks_ms() % 65536)
    
    # Flags
    flags = 0
    if any(abs(x) > 0.01 for x in wit_data[:3]): flags |= 1  # Angles valid
    if any(abs(x) > 0.1 for x in pod_data[:6]): flags |= 2   # POD valid
    if abs(wit_data[6]) > 1: flags |= 4  # Pressure Height > 1m
    if abs(wit_data[3]) > 0.0001: flags |= 8  # GPS Latitude valid
    last_flags = flags
    
    pkt = bytearray(46)  # ✅ زيادة من 34 إلى 46 بايت
    pkt[0:2] = b'\xAA\x55'
    struct.pack_into('<HH', pkt, 2, packet_cnt, ts)
    pkt[6] = flags
    
    # POD Data: Relative(X,Y,Z) + Zoom + Absolute(Roll,Pitch,Yaw)
    # pod_data[0:3] = Relative AngleX, AngleY, AngleZ
    # pod_data[3:6] = Absolute Roll, Pitch, Yaw
    # pod_data[6] = Zoom
    
    # البايت 7-12: Relative Angles (X, Y, Z)
    rel_scaled = [int(x*100) for x in pod_data[:3]]
    struct.pack_into('<hhh', pkt, 7, *rel_scaled)
    
    # البايت 13: Zoom
    zoom_byte = int(pod_data[6]*2.55)
    if zoom_byte < 0: zoom_byte = 0
    if zoom_byte > 255: zoom_byte = 255
    pkt[13] = zoom_byte
    
    # البايت 14-19: Absolute Angles (Roll, Pitch, Yaw)
    abs_scaled = [int(x*100) for x in pod_data[3:6]]
    struct.pack_into('<hhh', pkt, 14, *abs_scaled)
    
    # البايت 20-43: WIT Data (9 قيم)
    # wit_data[0:3] = Angles (int16 ÷ 100)
    # wit_data[3:6] = GPS (Lat, Lon, Alt) - int32
    # wit_data[6:9] = Pressure, Speed, Heading (int16 ÷ 100)
    
    # البايت 20-25: Angles (X, Y, Z)
    angles_scaled = [int(x*100) for x in wit_data[:3]]
    struct.pack_into('<hhh', pkt, 20, *angles_scaled)
    
    # البايت 26-29: Latitude (int32 ÷ 10,000,000)
    lat_scaled = int(wit_data[3] * 10000000)
    struct.pack_into('<i', pkt, 26, lat_scaled)
    
    # البايت 30-33: Longitude (int32 ÷ 10,000,000)
    lon_scaled = int(wit_data[4] * 10000000)
    struct.pack_into('<i', pkt, 30, lon_scaled)
    
    # البايت 34-37: GPS Altitude (int32 ÷ 100)
    gps_alt_scaled = int(wit_data[5] * 100)
    struct.pack_into('<i', pkt, 34, gps_alt_scaled)
    
    # البايت 38-43: Pressure Height, GPS Speed, Heading (int16 ÷ 100)
    others_scaled = [int(x*100) for x in wit_data[6:9]]
    struct.pack_into('<hhh', pkt, 38, *others_scaled)
    
    # البايت 44-45: CRC
    crc = crc16_ccitt_binary(pkt[:44])
    struct.pack_into('<H', pkt, 44, crc)
    
    packet_cnt = (packet_cnt + 1) & 0xFFFF
    return pkt, ts

# ────────────────────────────────────────────────────────
# 5. الحلقة الرئيسية
# ────────────────────────────────────────────────────────
while True:
    curr_time = time.ticks_ms()
    
    # طلب POD كل 20ms
    if time.ticks_diff(curr_time, last_pod_req_time) > 20:
        uart_pod.write(get_pod_request_packet())
        last_pod_req_time = curr_time
    
    # قراءة WIT (محسّن لتجنب البطء ✅)
    if uart_wit.any():
        # ✅ قراءة محدودة (128 بايت كحد أقصى)
        chunk = uart_wit.read(128)
        if chunk:
            wit_buffer.extend(chunk)
        
        # ✅ حماية من تضخم البافر
        if len(wit_buffer) > 300:
            wit_buffer = wit_buffer[-150:]
        
        # ✅ معالجة frame واحد فقط في كل دورة (لتجنب البطء)
        frame_processed = False
        i = 0
        while i < len(wit_buffer) - 10 and not frame_processed:
            if wit_buffer[i] == 0x55:
                frame = wit_buffer[i:i+11]
                if len(frame) == 11 and (sum(frame[:10]) & 0xFF) == frame[10]:
                    type_id, data = frame[1], frame[2:10]
                    
                    # 0x53: Angles (X, Y, Z) → wit_data[0:3]
                    if type_id == 0x53:
                        v = struct.unpack('<hhh', data[:6])
                        wit_data[0:3] = [x*180/32768 for x in v]
                        frame_processed = True
                    
                    # 0x57: GPS Coordinates (Lat, Lon) → wit_data[3:5]
                    elif type_id == 0x57:
                        lon_raw, lat_raw = struct.unpack('<ii', data[:8])
                        wit_data[3] = lat_raw / 10000000.0  # Latitude
                        wit_data[4] = lon_raw / 10000000.0  # Longitude  
                        frame_processed = True
                    
                    # 0x58: GPS Altitude, Speed → wit_data[5, 7]
                    elif type_id == 0x58:
                        gps_h_raw, gps_speed_raw = struct.unpack('<hh', data[:4])
                        wit_data[5] = gps_h_raw / 10.0      # GPS Altitude
                        wit_data[7] = gps_speed_raw / 1000.0  # GPS Speed
                        frame_processed = True
                    
                    # 0x54: Heading (Yaw) → wit_data[8]
                    elif type_id == 0x54:
                        yaw_raw = struct.unpack('<h', data[:2])[0]
                        wit_data[8] = yaw_raw * 180 / 32768.0  # Heading
                        frame_processed = True
                    
                    # 0x56: Pressure/Altitude → wit_data[6]
                    elif type_id == 0x56:
                        pres_raw = struct.unpack('<i', data[4:8])[0]
                        wit_data[6] = pres_raw / 100.0  # Pressure Height
                        frame_processed = True
                    
                    # إزالة الـ frame المعالج
                    if frame_processed:
                        wit_buffer = wit_buffer[i+11:]
                        break
            i += 1
        
        # إزالة البيانات غير الصالحة من بداية البافر
        if not frame_processed and len(wit_buffer) > 0 and wit_buffer[0] != 0x55:
            wit_buffer = wit_buffer[1:]

    # قراءة POD (Gimbal Data)
    if uart_pod.any():
        pod_buffer.extend(uart_pod.read())
        while len(pod_buffer) >= 72:
            if pod_buffer[0] == 0x8A and pod_buffer[1] == 0x5E:
                f = pod_buffer[:72]
                # البايت 12-18: Relative Angles (AngleX, AngleY, AngleZ)
                v1 = struct.unpack('<hhh', f[12:18])
                pod_data[0:3] = [x * 0.01 for x in v1]  # Relative X, Y, Z
                
                # البايت 18-22: Absolute Angles (Roll, Pitch)
                v2 = struct.unpack('<hh', f[18:22])
                pod_data[3:5] = [x * 0.01 for x in v2]  # Absolute Roll, Pitch
                
                # البايت 22-24: Absolute Yaw
                v3 = struct.unpack('<H', f[22:24])[0]
                pod_data[5] = v3 * 0.01  # Absolute Yaw
                
                # البايت 59-61: Zoom Level
                pod_data[6] = struct.unpack('<H', f[59:61])[0] * 0.1  # Zoom
                
                pod_buffer = pod_buffer[72:]
            else:
                pod_buffer = pod_buffer[1:]

    # إرسال الحزمة
    binary_pkt, ts = build_telemetry_packet()
    uart_rf.write(binary_pkt)
    led.value(1)
    
    # ✅ DEBUG: نفس الـ format اللي البرنامج يفهمه
    if DEBUG_MODE:
        hex_view = ' '.join('{:02X}'.format(b) for b in binary_pkt)
        # هذا الـ format متوافق مع parse_rp_bridge_hex_string()
        print("CNT=%5d FLAGS=%d (0x%02X) T=%5d | %s" %
              (packet_cnt, last_flags, last_flags, ts, hex_view))
    
    led.value(0)
    time.sleep_ms(20)

