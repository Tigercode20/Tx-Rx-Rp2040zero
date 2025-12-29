from machine import UART, Pin
import struct
import time

print("Starting sensor reader with RF transmission...")

# إعدادات الحساسات
uart_wit = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))
uart_pod = UART(1, baudrate=115200, tx=Pin(4), rx=Pin(5))

# إعداد RF Module (مثال: HC-12 أو LoRa)
# استخدم UART مختلف وأي Pins متاحة
try:
    uart_rf = UART(2, baudrate=9600, tx=Pin(8), rx=Pin(9))  # عدّل حسب وحدتك
    print("RF Module initialized on TX=Pin(8), RX=Pin(9), 9600 baud")
except Exception as e:
    print(f"RF init error: {e}")
    uart_rf = None

# دوال مساعدة
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

# الحالات الافتراضية
wit = {"ax":0, "ay":0, "az":0, "pres_h":0, "gps_h":0, "lon":0, "lat":0, "head":0, "speed":0}
pod = {"rx":0, "ry":0, "rz":0, "ar":0, "ap":0, "ay":0, "z":1.0}

print("Starting main loop...")
last_req = 0

try:
    while True:
        curr = time.ticks_ms()
        
        # إرسال طلب كل 50ms
        if time.ticks_diff(curr, last_req) > 50:
            uart_pod.write(get_request_packet())
            last_req = curr

        # قراءة WIT
        if uart_wit.any():
            raw = uart_wit.read()
            for i in range(len(raw)-10):
                if raw[i] == 0x55:
                    f = raw[i:i+11]
                    t = f[1]
                    d = f[2:10]
                    if t == 0x53:
                        v = struct.unpack('<hhh', d[:6])
                        wit["ax"], wit["ay"], wit["az"] = v[0]*180/32768, v[1]*180/32768, v[2]*180/32768
                    elif t == 0x56:
                        wit["pres_h"] = struct.unpack('<i', d[4:8])[0] / 100.0
                    elif t == 0x57:
                        lon, lat = struct.unpack('<ii', d)
                        wit["lon"], wit["lat"] = lon/1e7, lat/1e7
                    elif t == 0x58:
                        h, y, v = struct.unpack('<hhi', d)
                        wit["gps_h"], wit["head"], wit["speed"] = h/10, y/10, v/1000

        # قراءة Pod
        if uart_pod.any():
            p_raw = uart_pod.read()
            if len(p_raw) >= 72 and p_raw[0] == 0x8A:
                pod["rx"] = struct.unpack('<h', p_raw[12:14])[0]*0.01
                pod["ry"] = struct.unpack('<h', p_raw[14:16])[0]*0.01
                pod["rz"] = struct.unpack('<h', p_raw[16:18])[0]*0.01
                pod["ar"] = struct.unpack('<h', p_raw[18:20])[0]*0.01
                pod["ap"] = struct.unpack('<h', p_raw[20:22])[0]*0.01
                pod["ay"] = struct.unpack('<H', p_raw[22:24])[0]*0.01
                pod["z"] = struct.unpack('<H', p_raw[59:61])[0]*0.1

        # إعداد البيانات للإرسال
        data_line = f"{pod['rx']},{pod['ry']},{pod['rz']},{pod['ar']},{pod['ap']},{pod['ay']},{pod['z']}," \
                    f"{wit['ax']},{wit['ay']},{wit['az']},{wit['pres_h']},{wit['gps_h']},{wit['lon']}," \
                    f"{wit['lat']},{wit['head']},{wit['speed']}\n"
        
        # إرسال عبر RF
        if uart_rf:
            uart_rf.write(data_line)
        
        # إرسال عبر USB أيضاً (للمراقبة المحلية)
        print(data_line, end='')
        
        time.sleep(0.02)
        
except KeyboardInterrupt:
    print("\nStopped by user")
except Exception as e:
    print(f"Error: {e}")
finally:
    print("Program ended")
