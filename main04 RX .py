from machine import UART, Pin
import struct, time

# ═══════════════════════════════════════════════════════════════════
# بنية البيانات المستقبلة - 46 بايت (محدّث v4.0!)
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
# البايت 13:    Zoom (uint8, 0-255 → 0-100)
# البايت 14-15: Absolute Roll (int16 ÷ 100) - 2 خانة عشرية
# البايت 16-17: Absolute Pitch (int16 ÷ 100) - 2 خانة عشرية
# البايت 18-19: Absolute Yaw (int16 ÷ 100) - 2 خانة عشرية
# ────────────────────────────────────────────────────────
# بيانات الحساس (WIT) - 24 بايت (9 قيم):
# البايت 20-21: Angle X (int16 ÷ 100) - 2 خانة عشرية
# البايت 22-23: Angle Y (int16 ÷ 100) - 2 خانة عشرية
# البايت 24-25: Angle Z (int16 ÷ 100) - 2 خانة عشرية
# البايت 26-29: Latitude (int32 ÷ 10,000,000) - 7 خانات عشرية ✅
# البايت 30-33: Longitude (int32 ÷ 10,000,000) - 7 خانات عشرية ✅
# البايت 34-37: GPS Altitude (int32 ÷ 100) - 2 خانة عشرية ✅
# البايت 38-39: Pressure Height (int16 ÷ 100) - 2 خانة عشرية
# البايت 40-41: GPS Speed (int16 ÷ 100) - 2 خانة عشرية
# البايت 42-43: Heading (int16 ÷ 100) - 2 خانة عشرية
# ────────────────────────────────────────────────────────
# البايت 44-45: CRC16-CCITT
# ═══════════════════════════════════════════════════════════════════



from machine import UART, Pin
import struct, time

# ═══════════════════════════════════════════════════════════════════
# بنية البيانات المستقبلة - 46 بايت (الإصدار المستقر v4.1)
# ═══════════════════════════════════════════════════════════════════

# (HINT: HARDWARE SETUP) - إعدادات استقبال الراديو
# (HINT: BAUD 115200) - يجب أن يطابق سرعة المرسل لضمان القراءة الصحيحة
uart_radio = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))

led_ok = Pin(25, Pin.OUT)   # لمبة تومض عند نجاح استلام حزمة
led_err = Pin(16, Pin.OUT)  # لمبة تومض عند خطأ CRC

# (HINT: CRC CHECK) - دالة التحقق من سلامة البيانات المستلمة
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

buf = bytearray()
print("=== BINARY RX v4.1 | 46 Bytes | Baud: 115200 | GPS Support ON ===")

# (HINT: MAIN RECEIVE LOOP) - حلقة الاستقبال ومعالجة الحزم
while True:
    if uart_radio.any():
        # (HINT: READING) - قراءة البايتات القادمة من الراديو
        buf.extend(uart_radio.read())
        
        # (HINT: BUFFER LIMIT) - حماية الذاكرة من التضخم عند السرعات العالية
        if len(buf) > 800:
            buf = buf[-400:]

        # (HINT: PACKET SEARCH) - البحث عن بداية الحزمة AA 55
        while len(buf) >= 46:
            sync_pos = buf.find(b'\xAA\x55')
            
            if sync_pos == -1:
                buf = buf[-1:]
                break
            
            if sync_pos > 0:
                buf = buf[sync_pos:]
                continue
            
            if len(buf) < 46:
                break
            
            pkt = buf[:46]
            
            # (HINT: VALIDATION) - فحص الـ CRC للتأكد من عدم وجود تشويش
            calc_crc = crc16_ccitt(pkt[:44])
            rx_crc = struct.unpack('<H', pkt[44:46])[0]
            
            if calc_crc == rx_crc:
                # (HINT: UNPACKING) - فك شفرة البيانات (Counter, Flags, TS)
                counter, ts = struct.unpack('<HH', pkt[2:6])
                flags = pkt[6]
                
                # (HINT: DECODING POD) - استخراج زوايا وزووم الجيمبال
                p_rel = struct.unpack('<hhh', pkt[7:13])
                pod_rel_x, pod_rel_y, pod_rel_z = p_rel[0]/100.0, p_rel[1]/100.0, p_rel[2]/100.0
                pod_zoom = pkt[13] / 2.55
                p_abs = struct.unpack('<hhh', pkt[14:20])
                pod_abs_roll, pod_abs_pitch, pod_abs_yaw = p_abs[0]/100.0, p_abs[1]/100.0, p_abs[2]/100.0
                
                # (HINT: DECODING WIT) - استخراج زوايا وموقع الـ GPS
                w_angles = struct.unpack('<hhh', pkt[20:26])
                wit_ax, wit_ay, wit_az = w_angles[0]/100.0, w_angles[1]/100.0, w_angles[2]/100.0
                
                # (HINT: GPS DATA) - فك إحداثيات الموقع والارتفاع
                wit_lat = struct.unpack('<i', pkt[26:30])[0] / 10000000.0
                wit_lon = struct.unpack('<i', pkt[30:34])[0] / 10000000.0
                wit_gps_alt = struct.unpack('<i', pkt[34:38])[0] / 100.0
                
                # (HINT: SENSORS) - قراءة السرعة والضغط والبوصلة
                w_others = struct.unpack('<hhh', pkt[38:44])
                wit_pres_h = w_others[0] / 100.0
                wit_gps_speed = w_others[1] / 100.0
                wit_heading = w_others[2] / 100.0
                
                # (HINT: TERMINAL OUTPUT) - العرض بنظام الـ Hex القديم
                hex_view = ' '.join('{:02X}'.format(b) for b in pkt)
                print("CNT=%5d FLAGS=%d (0x%02X) T=%5d | %s" % (counter, flags, flags, ts, hex_view))
                
                # (HINT: ADDITIONAL LOG) - طباعة الموقع فقط إذا كان الـ GPS لاقط إشارة
                if flags & 8: 
                    print(" > GPS LOCK: Lat:%.6f, Lon:%.6f, Alt:%.1fm" % (wit_lat, wit_lon, wit_gps_alt))
                
                led_ok.toggle()
                buf = buf[46:]
            else:
                # (HINT: ERROR) - تفعيل لمبة الخطأ عند فشل الـ CRC
                led_err.toggle()
                buf = buf[1:]

    time.sleep_ms(5)