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
# ═══════════════════════════════════════════════════════════════════
# بنية البيانات المرسلة - 46 بايت (الإصدار v4.1 - نظام العرض القديم)
# ═══════════════════════════════════════════════════════════════════

# (HINT: PIO UART TX) - محرك خارجي لإرسال البيانات إذا احتجت GP8 مستقبلاً
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def uart_tx():
    pull(block)            .side(1)
    set(x, 9)              .side(0) [7]
    label("bitloop")
    out(pins, 1)                    [6]
    jmp(x_dec, "bitloop")           [6]

# (HINT: CRC الدوال الحسابية) - لضمان سلامة وصول البيانات للراديو
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

# ────────────────────────────────────────────────────────
# (HINT: HARDWARE SETUP) - إعدادات المنافذ والسرعة
# ────────────────────────────────────────────────────────
# (HINT: BAUD 115200) - تم الضبط ليتوافق مع إعدادات WIT الأخيرة في صورك
uart0 = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))
uart_rf = uart0   
uart_wit = uart0  

# (HINT: GIMBAL UART) - منفذ استقبال بيانات الجيمبال POD
uart_pod = UART(1, baudrate=115200, tx=Pin(4), rx=Pin(5))

led = Pin(25, Pin.OUT)

# ────────────────────────────────────────────────────────
# (HINT: VARIABLES) - مصفوفات تخزين البيانات قبل الإرسال
# ────────────────────────────────────────────────────────
pod_data = [0.0]*7 
wit_data = [0.0]*9 
packet_cnt = 0
last_flags = 0
pod_buffer = bytearray()
wit_buffer = bytearray()
last_pod_req_time = 0

DEBUG_MODE = True 

# (HINT: POD REQUEST) - توليد حزمة طلب الزوايا من الجيمبال
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

# (HINT: PACKET BUILDER) - تجميع 46 بايت النهائية للراديو
def build_telemetry_packet():
    global packet_cnt, last_flags
    ts = int(time.ticks_ms() % 65536)
    
    # (HINT: FLAGS) - تفعيل علامات الصحة للبيانات (بت رقم 8 للـ GPS)
    flags = 0
    if any(abs(x) > 0.01 for x in wit_data[:3]): flags |= 1  
    if any(abs(x) > 0.1 for x in pod_data[:6]): flags |= 2   
    if abs(wit_data[6]) > 1: flags |= 4  
    if abs(wit_data[3]) > 0.0001: flags |= 8  
    last_flags = flags
    
    pkt = bytearray(46)
    pkt[0:2] = b'\xAA\x55'
    struct.pack_into('<HH', pkt, 2, packet_cnt, ts)
    pkt[6] = flags
    
    # (HINT: PACKING POD) - وضع بيانات الجيمبال في الحزمة
    rel_scaled = [int(x*100) for x in pod_data[:3]]
    struct.pack_into('<hhh', pkt, 7, *rel_scaled)
    pkt[13] = max(0, min(255, int(pod_data[6]*2.55)))
    abs_scaled = [int(x*100) for x in pod_data[3:6]]
    struct.pack_into('<hhh', pkt, 14, *abs_scaled)
    
    # (HINT: PACKING WIT) - وضع بيانات الحساس والـ GPS في الحزمة
    angles_scaled = [int(x*100) for x in wit_data[:3]]
    struct.pack_into('<hhh', pkt, 20, *angles_scaled)
    struct.pack_into('<i', pkt, 26, int(wit_data[3] * 10000000))
    struct.pack_into('<i', pkt, 30, int(wit_data[4] * 10000000))
    struct.pack_into('<i', pkt, 34, int(wit_data[5] * 100))
    others_scaled = [int(x*100) for x in wit_data[6:9]]
    struct.pack_into('<hhh', pkt, 38, *others_scaled)
    
    # (HINT: FINAL CRC) - بايتات التحقق النهائية
    crc = crc16_ccitt_binary(pkt[:44])
    struct.pack_into('<H', pkt, 44, crc)
    
    packet_cnt = (packet_cnt + 1) & 0xFFFF
    return pkt, ts

# ────────────────────────────────────────────────────────
# (HINT: MAIN LOOP) - الحلقة البرمجية الرئيسية
# ────────────────────────────────────────────────────────
print("BINARY TX v4.1 | 46B | RFD900 Ready | GPS Tracking On")

while True:
    curr_time = time.ticks_ms()
    
    # (HINT: POD LOOP) - طلب بيانات الجيمبال كل 20 ملي ثانية
    if time.ticks_diff(curr_time, last_pod_req_time) > 20:
        uart_pod.write(get_pod_request_packet())
        last_pod_req_time = curr_time
    
    # (HINT: WIT DECODER) - معالجة زحام حزم WIT لمنع التجمد
    if uart_wit.any():
        chunk = uart_wit.read(512) 
        if chunk:
            wit_buffer.extend(chunk)
        
        if len(wit_buffer) > 800:
            wit_buffer = wit_buffer[-400:]
            
        i = 0
        while i <= len(wit_buffer) - 11:
            if wit_buffer[i] == 0x55:
                frame = wit_buffer[i:i+11]
                if (sum(frame[:10]) & 0xFF) == frame[10]:
                    type_id, data = frame[1], frame[2:10]
                    
                    if type_id == 0x53: # Angles
                        v = struct.unpack('<hhh', data[:6])
                        wit_data[0:3] = [x*180/32768 for x in v]
                    elif type_id == 0x57: # GPS Lat/Lon
                        lon_raw, lat_raw = struct.unpack('<ii', data[:8])
                        wit_data[3], wit_data[4] = lat_raw/10000000.0, lon_raw/10000000.0
                    elif type_id == 0x58: # GPS Alt/Speed
                        gps_h_raw, gps_speed_raw = struct.unpack('<hh', data[:4])
                        wit_data[5], wit_data[7] = gps_h_raw/10.0, gps_speed_raw/1000.0
                    elif type_id == 0x54: # Heading
                        yaw_raw = struct.unpack('<h', data[:2])[0]
                        wit_data[8] = yaw_raw * 180 / 32768.0
                    elif type_id == 0x56: # Pressure Altitude
                        pres_raw = struct.unpack('<i', data[4:8])[0]
                        wit_data[6] = pres_raw / 100.0
                    
                    wit_buffer = wit_buffer[i+11:]
                    i = 0 
                    continue
            i += 1

    # (HINT: POD DECODER) - قراءة حزمة الجيمبال
    if uart_pod.any():
        pod_buffer.extend(uart_pod.read())
        while len(pod_buffer) >= 72:
            if pod_buffer[0] == 0x8A and pod_buffer[1] == 0x5E:
                f = pod_buffer[:72]
                v1 = struct.unpack('<hhh', f[12:18])
                pod_data[0:3] = [x * 0.01 for x in v1]
                v2 = struct.unpack('<hh', f[18:22])
                pod_data[3:5] = [x * 0.01 for x in v2]
                pod_data[5] = struct.unpack('<H', f[22:24])[0] * 0.01
                pod_data[6] = struct.unpack('<H', f[59:61])[0] * 0.1
                pod_buffer = pod_buffer[72:]
            else:
                pod_buffer = pod_buffer[1:]

    # (HINT: RF OUTPUT) - إرسال البيانات النهائية
    binary_pkt, ts = build_telemetry_packet()
    uart_rf.write(binary_pkt)
    
    # (HINT: OLD DEBUG STYLE) - نظام العرض القديم (CNT, FLAGS, HEX)
    if DEBUG_MODE:
        hex_view = ' '.join('{:02X}'.format(b) for b in binary_pkt)
        print("CNT=%5d FLAGS=%d (0x%02X) T=%5d | %s" %
              (packet_cnt, last_flags, last_flags, ts, hex_view))

    time.sleep_ms(20)