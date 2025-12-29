# How to Upload and Run on RP2040

## 📋 What This Code Does

[`sensor_reader.py`](file:///f:/Nemr/COMPINE/compine/sensor_reader.py) reads data from two sensors:
- **WIT Sensor** (UART0 on pins 0/1, 9600 baud) - IMU/GPS data
- **Pod Sensor** (UART1 on pins 4/5, 115200 baud) - Gimbal orientation/zoom

It combines the data and outputs it via USB every 20ms.

---

## 🚀 Method 1: Using Thonny IDE (Recommended)

**Easiest way to upload and test!**

### Steps:
1. Download and install [Thonny](https://thonny.org/)
2. Open Thonny → `Tools` → `Options` → `Interpreter`
3. Select: `MicroPython (Raspberry Pi Pico)`
4. Select port: `COM6`
5. Open [`sensor_reader.py`](file:///f:/Nemr/COMPINE/compine/sensor_reader.py) in Thonny
6. Press `F5` or click **Run** ▶️
7. Watch the output in the Shell window!

---

## 🔧 Method 2: Using Command Line (ampy)

**For quick uploads from terminal:**

```powershell
# Upload the file
ampy --port COM6 put sensor_reader.py

# Run it immediately
ampy --port COM6 run sensor_reader.py

# Or make it run on boot (save as main.py)
ampy --port COM6 put sensor_reader.py main.py

ampy --port COM6 put main.py
```

**To run from Antigravity terminal:**

```powershell
ampy --port COM6 run sensor_reader.py
```

---

## 📊 Expected Output

When running, you'll see CSV data like:

```
0.12,0.45,-0.03,1.2,0.8,45.3,1.0,0.0,0.0,0.0,1013.25,125.4,31.5678,30.1234,90.5,0.0
```

Format:
```
rx,ry,rz,ar,ap,ay,z,ax,ay,az,pres_h,gps_h,lon,lat,head,speed
```

Where:
- **rx, ry, rz**: Pod relative angles
- **ar, ap, ay**: Pod absolute angles  
- **z**: Pod zoom
- **ax, ay, az**: WIT angles
- **pres_h**: Barometric altitude
- **gps_h**: GPS altitude
- **lon, lat**: GPS coordinates
- **head, speed**: GPS heading and speed

---

## ⚡ Quick Commands (Copy & Paste)

### Upload and run once:
```powershell
ampy --port COM6 run f:\Nemr\COMPINE\compine\sensor_reader.py
```

### Upload as main.py (auto-run on power up):
```powershell
ampy --port COM6 put f:\Nemr\COMPINE\compine\sensor_reader.py main.py
```

### Stop running code on RP2040:
Press `Ctrl + C` in the terminal

---

## 🔍 Troubleshooting

**"Device is busy":**
- Close any other programs using COM6
- Unplug and replug RP2040
- Hold BOOTSEL button while plugging in, then try again

**No output:**
- Make sure sensors are connected to correct pins
- Check baud rates match sensor specs
- Verify sensors are powered

**Wrong COM port:**
```powershell
# List all ports
ampy --port COM6 ls
# If error, try COM10 or other ports
```
