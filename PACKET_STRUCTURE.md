# هيكل حزمة البيانات - 46 بايت (v4.0 - Final)

## نظرة عامة
**الإصدار**: v4.0 (Final - Tested & Working ✅)  
**حجم الحزمة**: **46 بايت**  
**معدل الإرسال**: **50 Hz** (كل 20ms)  
**البروتوكول**: Binary over UART/RFD900 @ **57600 baud**  
**الحالة**: ✅ **تم الاختبار بنجاح**

---

## الإعدادات النهائية

### ⚙️ UART Configuration:
```
TX Pico:
  UART0 @ 57600 baud (GP0=TX, GP1=RX)
    - TX: إرسال للراديو/RX الآخر
    - RX: استقبال من WIT Sensor
  UART1 @ 115200 baud (GP4/GP5)
    - Gimbal POD communication

RX Pico:
  UART0 @ 57600 baud (GP0=TX, GP1=RX)
    - RX: استقبال من الراديو/TX الآخر

WIT Sensor:
  Baud Rate: 57600 ✅
  Output Rate: 50Hz ✅
  Bandwidth: 20Hz
```

### 📊 الأداء:
```
حجم البيانات: 46 bytes × 50 Hz × 10 bits = 23,000 bps
Baudrate: 57600 baud
الاستخدام: 40% ✅ (مثالي!)
```

---

## البنية التفصيلية

### 🔹 Header (7 بايت)
| البايت | النوع | القيمة | الوصف |
|--------|-------|--------|-------|
| 0-1 | uint8[2] | 0xAA 0x55 | علامة البداية (Sync Pattern) |
| 2-3 | uint16 | 0-65535 | عداد الحزم (Packet Counter) |
| 4-5 | uint16 | 0-65535 | الطابع الزمني (Timestamp ms % 65536) |
| 6 | uint8 | Flags | أعلام الحالة (Status Flags) |

**Flags (البايت 6):**
- **Bit 0** (0x01): بيانات WIT Angles صالحة
- **Bit 1** (0x02): بيانات POD صالحة
- **Bit 2** (0x04): Pressure Height > 1m
- **Bit 3** (0x08): GPS Latitude صالحة (GPS has lock)
- **Bit 4-7**: محجوز (Reserved)

**أمثلة FLAGS:**
```
0x01 = WIT فقط
0x02 = POD فقط
0x03 = WIT + POD ✅
0x07 = WIT + POD + Pressure ✅ (الوضع الحالي)
0x0F = WIT + POD + Pressure + GPS ✅ (مثالي!)
```

---

### 🎮 بيانات الجيمبال - POD Data (13 بايت)

#### الزوايا النسبية (Relative Angles) - 6 بايت
| البايت | النوع | المقياس | النطاق | الدقة | الوصف |
|--------|-------|---------|--------|-------|-------|
| 7-8 | int16 | ÷100 | ±327.67° | 0.01° | **Relative AngleX**: زاوية المحور X النسبية |
| 9-10 | int16 | ÷100 | ±327.67° | 0.01° | **Relative AngleY**: زاوية المحور Y النسبية |
| 11-12 | int16 | ÷100 | ±327.67° | 0.01° | **Relative AngleZ**: زاوية المحور Z النسبية |

**مثال حقيقي من البيانات:**
```
CE 00 77 00 3D FF
→ AngleX = 206/100 = 2.06°
→ AngleY = 119/100 = 1.19°
→ AngleZ = -195/100 = -1.95°
```

#### التقريب (Zoom) - 1 بايت
| البايت | النوع | المقياس | النطاق | الدقة | الوصف |
|--------|-------|---------|--------|-------|-------|
| 13 | uint8 | ×2.55 | 0-100% | ~0.39% | **Zoom**: مستوى التقريب |

#### الزوايا المطلقة (Absolute Angles) - 6 بايت
| البايت | النوع | المقياس | النطاق | الدقة | الوصف |
|--------|-------|---------|--------|-------|-------|
| 14-15 | int16 | ÷100 | ±327.67° | 0.01° | **Absolute Roll**: زاوية الميلان المطلقة |
| 16-17 | int16 | ÷100 | ±327.67° | 0.01° | **Absolute Pitch**: زاوية الانحدار المطلقة |
| 18-19 | int16 | ÷100 | ±327.67° | 0.01° | **Absolute Yaw**: زاوية الاتجاه المطلقة |

**مثال حقيقي:**
```
FF FF 00 00 02 00
→ Roll = -1/100 = -0.01°
→ Pitch = 0/100 = 0.00°
→ Yaw = 2/100 = 0.02°
```

---

### 🛩️ بيانات المركبة - WIT Sensor Data (24 بايت - 9 قيم)

#### زوايا المركبة (Vehicle Angles) - 6 بايت
| البايت | النوع | المقياس | النطاق | الدقة | الوصف |
|--------|-------|---------|--------|-------|-------|
| 20-21 | int16 | ÷100 | ±327.67° | 0.01° | **Angle X**: زاوية المركبة على المحور X |
| 22-23 | int16 | ÷100 | ±327.67° | 0.01° | **Angle Y**: زاوية المركبة على المحور Y |
| 24-25 | int16 | ÷100 | ±327.67° | 0.01° | **Angle Z**: زاوية المركبة على المحور Z |

**مثال حقيقي:**
```
01 00 08 00 39 2C
→ Angle X = 1/100 = 0.01°
→ Angle Y = 8/100 = 0.08°
→ Angle Z = 11321/100 = 113.21° (Compass heading)
```

#### إحداثيات GPS - 12 بايت 🛰️
| البايت | النوع | المقياس | النطاق | الدقة | الوصف |
|--------|-------|---------|--------|-------|-------|
| 26-29 | **int32** | ÷10,000,000 | ±214.7° | **~1.1 cm** | **Latitude**: خط العرض |
| 30-33 | **int32** | ÷10,000,000 | ±214.7° | **~1.1 cm** | **Longitude**: خط الطول |
| 34-37 | **int32** | ÷100 | ±21,474,836 m | 0.01 m (1 cm) | **GPS Altitude**: الارتفاع من GPS |

**مثال (GPS has lock):**
```
القاهرة:
40 E2 01 00 C0 27 1C 00
→ Lat: 123456 / 10000000 = 30.0123456°
→ Lon: 1845184 / 10000000 = 31.1845184°
```

**الوضع الحالي (GPS not locked):**
```
00 00 00 00 00 00 00 00
→ Lat: 0° (waiting for GPS fix)
→ Lon: 0°
```

#### بيانات إضافية - 6 بايت
| البايت | النوع | المقياس | النطاق | الدقة | الوصف |
|--------|-------|---------|--------|-------|-------|
| 38-39 | int16 | ÷100 | ±327.67 m | 0.01 m | **Pressure Height**: الارتفاع من الضغط |
| 40-41 | int16 | ÷100 | ±327.67 m/s | 0.01 m/s | **GPS Speed**: السرعة من GPS |
| 42-43 | int16 | ÷100 | ±327.67° | 0.01° | **Heading**: الاتجاه |

**مثال حقيقي:**
```
CF 2A 00 00 F8 05
→ Pressure Height = 10959/100 = 109.59m ✅
→ GPS Speed = 0/100 = 0.00 m/s
→ Heading = 1528/100 = 15.28° ✅
```

---

### ✅ التحقق من الصحة (2 بايت)

| البايت | النوع | الخوارزمية | الوصف |
|--------|-------|-----------|-------|
| 44-45 | uint16 | CRC16-CCITT | التحقق من سلامة البيانات (Initial: 0x1D0F, Poly: 0x1021) |

---

## مثال حقيقي من النظام العامل

### حزمة فعلية تم استقبالها:

```
AA 55 15 01 6F DB 07 CE 00 77 00 3D FF 00 FF FF 00 00 02 00 
01 00 08 00 39 2C 00 00 00 00 00 00 00 00 00 00 00 00 CF 2A 
00 00 F8 05 F4 4B
```

### فك التشفير:

```
Header:
  AA 55          = Sync
  15 01          = Counter = 277
  6F DB          = Timestamp = 56175 ms
  07             = FLAGS = 0x07 (WIT + POD + Pressure)

POD Data:
  CE 00 77 00 3D FF = Relative (2.06°, 1.19°, -1.95°)
  00             = Zoom = 0%
  FF FF 00 00 02 00 = Absolute (-0.01°, 0.00°, 0.02°)

WIT Data:
  01 00 08 00 39 2C = Angles (0.01°, 0.08°, 113.21°)
  00 00 00 00       = Latitude = 0° (GPS not locked)
  00 00 00 00       = Longitude = 0°
  00 00 00 00       = GPS Alt = 0m
  CF 2A             = Pressure Height = 109.59m ✅
  00 00             = GPS Speed = 0 m/s
  F8 05             = Heading = 15.28° ✅

CRC:
  F4 4B          = CRC16 ✅
```

---

## ملاحظات مهمة

### 🔄 تحويل القيم

#### من الحساس إلى الحزمة (TX):

```python
# زوايا (جميع الزوايا - 2 خانة عشرية)
angle = 113.21  # درجة
packed_value = int(113.21 * 100)  # = 11321 = 0x2C39 (int16 little-endian)

# GPS Latitude/Longitude (7 خانات عشرية)
latitude = 30.0444196  # درجة
packed_lat = int(30.0444196 * 10000000)  # = 300444196 = 0x11E9E684 (int32)

# GPS Altitude (2 خانة عشرية)
gps_alt = 109.59  # متر
packed_alt = int(109.59 * 100)  # = 10959 = 0x00002ACF (int32)

# Zoom (0-100%)
zoom = 50.0  # نسبة مئوية
zoom_byte = int(50.0 * 2.55)  # = 127 = 0x7F (uint8)
```

#### من الحزمة إلى القيمة (RX):

```python
# فك تشفير الزاوية (int16)
raw_value = struct.unpack('<h', bytes([0x39, 0x2C]))[0]  # = 11321
angle = raw_value / 100.0  # = 113.21°

# فك تشفير GPS Coordinates (int32)
lat_raw = struct.unpack('<i', bytes([0x40, 0xE2, 0x01, 0x00]))[0]  # = 123456
latitude = lat_raw / 10000000.0  # = 0.0123456° (أو 30.xxx إذا GPS locked)

# فك تشفير GPS Altitude (int32)
alt_raw = struct.unpack('<i', bytes([0xCF, 0x2A, 0x00, 0x00]))[0]  # = 10959
gps_alt = alt_raw / 100.0  # = 109.59 m

# فك تشفير Zoom (uint8)
zoom_byte = 127
zoom_percent = zoom_byte / 2.55  # = 49.8%
```

---

### 📊 دقة GPS

#### الدقة النظرية:
```
1 درجة = 10,000,000 وحدة
1 وحدة = 0.0000001 درجة = 10 نانو درجة

عند خط الاستواء:
1 درجة longitude ≈ 111.32 km
0.0000001° ≈ 1.11 cm

الدقة الفعلية: ~1.1 cm ✅
```

#### أمثلة GPS (عندما يحصل على lock):
```python
# القاهرة
Lat: 30.0444196° → 300444196 (int32)
Lon: 31.2357116° → 312357116 (int32)

# دبي
Lat: 25.2048493° → 252048493 (int32)
Lon: 55.2707828° → 552707828 (int32)

# الرياض
Lat: 24.7135517° → 247135517 (int32)
Lon: 46.6752957° → 466752957 (int32)
```

---

## استكشاف الأخطاء

### ❌ GPS = 0 دائماً (الحالة الحالية)

**السبب**: WIT لم يحصل على GPS satellite lock

**الحل**:
1. ضع WIT Sensor في **مكان مفتوح** (قرب نافذة أو outdoor)
2. انتظر **1-3 دقائق** للحصول على GPS fix
3. راقب **FLAGS** - عندما تصبح `0x0F` أو `0x0B` معناه GPS locked
4. تحقق من GPS antenna متصل بشكل صحيح

### ✅ النظام يعمل لكن GPS لا يعمل

```
الحالة الحالية:
FLAGS = 0x07 (WIT + POD + Pressure) ✅
GPS = 0x00 (waiting for satellite lock) ⏳

عند نجاح GPS:
FLAGS = 0x0F (WIT + POD + Pressure + GPS) ✅
Lat/Lon ≠ 0 ✅
```

### 🔧 CRC Errors

إذا ظهرت أخطاء CRC:
- تحقق من **baudrate** متطابق (57600)
- تحقق من **GND** مشترك بين TX و RX
- تحقق من جودة الأسلاك/الراديو
- قلل **معدل الإرسال** إذا لزم الأمر (من 50Hz إلى 20Hz)

---

## WIT Sensor Frame IDs

البروتوكول المستخدم لقراءة بيانات WIT @ 57600 baud:

| Frame ID | البيانات | wit_data المقابل | الحالة |
|----------|---------|------------------|--------|
| **0x53** | Angles (Roll, Pitch, Yaw) | [0:3] | ✅ Working |
| **0x57** | GPS Coordinates (Lon, Lat) | [3:5] | ⏳ Waiting for lock |
| **0x58** | GPS Alt, Speed | [5, 7] | ⏳ Waiting for lock |
| **0x54** | Heading (Yaw) | [8] | ✅ Working |
| **0x56** | Pressure/Altitude | [6] | ✅ Working |

---

## معادلات التحويل السريعة

```python
# ═══ TX Side ═══
# POD Data (7 values)
pod_data[0:3]  # Relative AngleX, Y, Z (degrees, ÷100)
pod_data[3:6]  # Absolute Roll, Pitch, Yaw (degrees, ÷100)
pod_data[6]    # Zoom (0-100%, ×2.55)

# WIT Data (9 values)
wit_data[0:3]  # Angles X, Y, Z (degrees, ÷100)
wit_data[3]    # Latitude (degrees, ÷10,000,000) ⏳
wit_data[4]    # Longitude (degrees, ÷10,000,000) ⏳
wit_data[5]    # GPS Altitude (m, ÷100) ⏳
wit_data[6]    # Pressure Height (m, ÷100) ✅
wit_data[7]    # GPS Speed (m/s, ÷100) ⏳
wit_data[8]    # Heading (degrees, ÷100) ✅

# ═══ RX Side ═══
# Unpacking example (from real data)
wit_angle_z = struct.unpack('<h', pkt[24:26])[0] / 100.0  # = 113.21°
wit_pres_h = struct.unpack('<h', pkt[38:40])[0] / 100.0   # = 109.59m
wit_heading = struct.unpack('<h', pkt[42:44])[0] / 100.0  # = 15.28°
```

---

## التغييرات من v3.0 إلى v4.0

### ✅ التحديثات:
- **Baudrate**: 9600 → **57600** (زيادة 6x)
- **WIT Sensor**: 9600 → **57600** (متطابق الآن)
- **GPS Data**: إضافة Latitude, Longitude, GPS Altitude (12 بايت)
- **حجم الحزمة**: 34 → **46 بايت** (+12)
- **الأداء**: 239% استخدام → **40% استخدام** ✅
- **الحالة**: تم الاختبار بنجاح ✅

### 🎯 النتيجة:
```
نظام كامل وعامل بكفاءة عالية
فقط GPS يحتاج sky view للحصول على lock
```

---

**تم التحديث**: 2025-12-29  
**الإصدار**: 4.0 Final  
**الحالة**: ✅ Tested & Working  
**المؤلف**: TX/RX System v4.0 - GPS Enhanced
