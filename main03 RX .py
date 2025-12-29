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

# ────────────────────────────────────────────────────────
# 1. إعدادات الأجهزة (Hardware Setup)
# ────────────────────────────────────────────────────────
# UART0: استقبال من راديو/TX الآخر @ 57600 baud
uart_radio = UART(0, baudrate=57600, tx=Pin(0), rx=Pin(1))

led_ok = Pin(25, Pin.OUT)   # لمبة النجاح
led_err = Pin(16, Pin.OUT)  # لمبة الخطأ

# ────────────────────────────────────────────────────────
# 2. دالة CRC16-CCITT (مطابقة للمرسل)
# ────────────────────────────────────────────────────────
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
packet_count = 0
error_count = 0

print("=== BINARY RX->CSV BRIDGE (GP0/GP1) | 46 Bytes | With GPS Data v4.0 ===")

# ────────────────────────────────────────────────────────
# 3. الحلقة الرئيسية
# ────────────────────────────────────────────────────────
while True:
    if uart_radio.any():
        # قراءة البيانات المتاحة
        buf.extend(uart_radio.read())
        
        # حماية من تضخم البافر
        if len(buf) > 300:
            buf = buf[-100:]

        # البحث عن الحزمة ومعالجتها
        while len(buf) >= 46:  # ✅ تغيير من 34 إلى 46
            sync_pos = buf.find(b'\xAA\x55')
            
            if sync_pos == -1:
                buf = buf[-1:]
                break
            
            if sync_pos > 0:
                buf = buf[sync_pos:]
                continue
            
            if len(buf) < 46:  # ✅ تغيير من 34 إلى 46
                break
            
            pkt = buf[:46]  # ✅ تغيير من 34 إلى 46
            
            # فحص السلامة (CRC)
            calc_crc = crc16_ccitt(pkt[:44])  # ✅ تغيير من 32 إلى 44
            rx_crc = struct.unpack('<H', pkt[44:46])[0]  # ✅ تغيير من 32:34 إلى 44:46
            
            if calc_crc == rx_crc:
                # فك الحزمة
                counter, ts = struct.unpack('<HH', pkt[2:6])
                flags = pkt[6]
                
                # بيانات الجيمبال (POD) - Relative + Absolute + Zoom
                # البايت 7-12: Relative Angles (AngleX, AngleY, AngleZ)
                p_rel = struct.unpack('<hhh', pkt[7:13])
                pod_rel_x, pod_rel_y, pod_rel_z = p_rel[0]/100.0, p_rel[1]/100.0, p_rel[2]/100.0
                
                # البايت 13: Zoom Level
                pod_zoom = pkt[13] / 2.55
                
                # البايت 14-19: Absolute Angles (Roll, Pitch, Yaw)
                p_abs = struct.unpack('<hhh', pkt[14:20])
                pod_abs_roll, pod_abs_pitch, pod_abs_yaw = p_abs[0]/100.0, p_abs[1]/100.0, p_abs[2]/100.0
                
                # البايت 20-43: بيانات الحساس (WIT) - 9 قيم
                # البايت 20-25: Angles (X, Y, Z)
                w_angles = struct.unpack('<hhh', pkt[20:26])
                wit_ax, wit_ay, wit_az = w_angles[0]/100.0, w_angles[1]/100.0, w_angles[2]/100.0
                
                # البايت 26-29: Latitude (int32 ÷ 10,000,000) ✅ جديد!
                wit_lat = struct.unpack('<i', pkt[26:30])[0] / 10000000.0
                
                # البايت 30-33: Longitude (int32 ÷ 10,000,000) ✅ جديد!
                wit_lon = struct.unpack('<i', pkt[30:34])[0] / 10000000.0
                
                # البايت 34-37: GPS Altitude (int32 ÷ 100) ✅ جديد!
                wit_gps_alt = struct.unpack('<i', pkt[34:38])[0] / 100.0
                
                # البايت 38-43: Pressure Height, GPS Speed, Heading
                w_others = struct.unpack('<hhh', pkt[38:44])
                wit_pres_h = w_others[0] / 100.0
                wit_gps_speed = w_others[1] / 100.0
                wit_heading = w_others[2] / 100.0
                
                # ✅ طباعة بنفس format TX (للكمبيوتر)
                hex_view = ' '.join('{:02X}'.format(b) for b in pkt)
                print("CNT=%5d FLAGS=%d (0x%02X) T=%5d | %s" %
                      (counter, flags, flags, ts, hex_view))
                
                led_ok.toggle()
                packet_count += 1
                buf = buf[46:]  # ✅ تغيير من 34 إلى 46
            else:
                # CRC error
                led_err.toggle()
                error_count += 1
                buf = buf[1:]

    time.sleep_ms(5)
