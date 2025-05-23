import sys
import time
import gc
import machine
import ujson

import pycom
from network import WLAN

# Append shield libs
sys.path.append('/flash/shields')
from lib.L76GNSS import L76GNSS
from lib.pycoproc_1 import Pycoproc
from lib.LIS2HH12 import LIS2HH12
from lib.client import connect


# Configuration
WIFI_SSID = 'stop using our Telenet'
WIFI_PASS = '1020304050'
HOST = 'iot.philippevoet.dev'
PORT = 443
POST_PATH = '/location'
SLEEP_INTERVAL = 0.01  # seconds
GPS_TIMEOUT = 60  # seconds
GPS_BUFFER = 512
DEBUG = True

WS_HOST = 'wss://iot.philippevoet.dev'  

ANOMALY_THRESHOLD_MAGNITUDE = 1.5  # g
ROLLING_WINDOW_SIZE = 7
Z_SCORE_THRESHOLD = 2.5

accel_mag_window = []

ORIENT_THRESHOLD = 45  
orient_window = []


prev_ax, prev_ay, prev_az = 0,0,0.98

def log(msg, *args):
    if args:
        msg = msg.format(*args)
    print('[{}] {}'.format(time.time(), msg))

def connect_wifi(ssid, password, timeout=30):
    wlan = WLAN(mode=WLAN.STA)
    wlan.connect(ssid=ssid, auth=(WLAN.WPA2, password))
    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout:
            raise RuntimeError('WiFi connection timeout')
        machine.idle()
    log('WiFi connected: {}', wlan.ifconfig())
    return wlan
"""""
def join_lorawan(app_eui, app_key):                                             
    lora = LoRa(mode=LoRa.LORAWAN, region=LoRa.EU868)                           
    log('LoRa DevEUI: {}', binascii.hexlify(lora.mac()).upper().decode())       
                                                                                
    lora.join(activation=LoRa.OTAA, auth=(app_eui, app_key), timeout=0)         
    for _ in range(30):                                                         
        if lora.has_joined():                                                   
            log("LoRaWAN joined")                                               
            return lora                                                         
        log("Waiting for LoRaWAN join...")                                      
        time.sleep(2)                                                           
    raise RuntimeError("LoRaWAN join failed")  
"""


def send_location_ws(lat, lon):
    try:
        ws = connect(WS_HOST)
        payload = ujson.dumps({"type": "location", "latitude": lat, "longitude": lon})
        ws.send(payload)
        ws.close()
    except Exception as e:
        log("WebSocket error: {}", e)

def send_sensor_data_ws(x_speed,y_speed,z_speed,roll, pitch):
    try:
        ws= connect(WS_HOST)
        payload = ujson.dumps({"type": "sensors", "value": {  "accelerometer" : {"x" : x_speed, "y" : y_speed, "z" : z_speed},
                "pitch" : pitch,
                "roll" : roll 
        }})
        ws.send(payload)
        
        ws.close()
        
    except Exception as e:
        log("WebSocket error: {}", e)

def send_notification(message):
    try:
        ws= connect(WS_HOST)
        payload = ujson.dumps({ "type" : "notification" , "message" : message})
        ws.send(payload)
        _ , _ , data_b = ws.read_frame()
        data = ujson.loads(data_b.decode('utf-8'))

        if data.get("redlight"):
            pycom.rgbled(0xFF00)  # Red
        
        ws.close()
       
    except Exception as e:
        log("WebSocket error: {}", e)
    
def init_sensors():
    py = Pycoproc(Pycoproc.PYTRACK)
    time.sleep(1)
    gps = L76GNSS(py, timeout=GPS_TIMEOUT, buffer=GPS_BUFFER)
    # gps.dump_nmea()
    accel = LIS2HH12(py)
    return gps, accel




def get_coordinates(gps, debug=False, max_wait=5):
    start = time.time()
    while time.time() - start < max_wait:
        coords = gps.coordinates(debug=debug)
        lat, lon = coords[0], coords[1]
        if lat is not None and lon is not None:
            return lat, lon
        
    return None, None


def detect_anomaly(ax, ay, az):
    global accel_mag_window

    magnitude = (ax**2 + ay**2 + az**2)**0.5
    accel_mag_window.append(magnitude)
    if len(accel_mag_window) < ROLLING_WINDOW_SIZE:
        return False  # Not enough data yet

    if len(accel_mag_window) > ROLLING_WINDOW_SIZE:
        accel_mag_window.pop(0)

    if magnitude > ANOMALY_THRESHOLD_MAGNITUDE:
        send_notification("Anomaly: High acceleration magnitude")
        return True

    mean = sum(accel_mag_window) / len(accel_mag_window)
    std = (sum((x - mean) ** 2 for x in accel_mag_window) / len(accel_mag_window)) ** 0.5
    if std > 0:
        z = abs((magnitude - mean) / std)
        if z > Z_SCORE_THRESHOLD:
            send_notification("Anomaly: Z-score exceeds threshold")
            return True

    return False


def detect_orientation_anomaly(roll, pitch):

    if abs(roll) > ORIENT_THRESHOLD or abs(pitch) > ORIENT_THRESHOLD:
        send_notification("Anomaly: Orientation out of bounds")
        return True
    return False


def detect_delta_anomaly(ax, ay, az):
    global prev_ax, prev_ay, prev_az
    delta = ((ax-prev_ax)**2 + (ay-prev_ay)**2 + (az-prev_az)**2)**0.5
    prev_ax, prev_ay, prev_az = ax, ay, az
    if delta > 0.7:
        send_location_ws("Anomaly: Sudden delta change")
        return True
    return False

def main():
    pycom.heartbeat(False)
    pycom.rgbled(0x0A0A08)
    time.sleep(2)
    gc.enable()
    
    log('GC enabled, free memory: {}', gc.mem_free())


    try:
        wlan = connect_wifi(WIFI_SSID, WIFI_PASS)
    except Exception as e:
        log('WiFi failed, falling back to LoRaWAN: {}', e)


    gps, accel = init_sensors()
    log('Sensors initialized')

    last_gps_time = time.time()
    counter = 0
    while True:
        try:
            ax, ay, az = accel.acceleration()
            roll = accel.roll()
            pitch = accel.pitch()
            log('Acceleration: x={:.2f}g, y={:.2f}g, z={:.2f}g, Roll: {:.2f}, Pitch: {:.2f}', ax, ay, az, roll, pitch)
            
            enough_data = counter >= ROLLING_WINDOW_SIZE

            if enough_data:
                anomaly_detected = (
                    detect_anomaly(ax, ay, az) or
                    detect_orientation_anomaly(roll, pitch) or
                    detect_delta_anomaly(ax, ay, az)
                )
                counter = 0
            else:
                anomaly_detected = False

            pycom.rgbled(0xFF8C00 if anomaly_detected else 0x000000)

            send_sensor_data_ws(ax, ay, az, roll, pitch)
            counter += 1
        except Exception as e:
            log('Sensor data error: {}', e)

        # Check coordinates every 3 minutes (180 seconds)
        current_time = time.time()
        if current_time - last_gps_time >= 180:
            lat, lon = get_coordinates(gps, debug=DEBUG)
            if lat is not None and lon is not None:
                log('Coordinates: lat={}, lon={}', lat, lon)
                try:
                    send_location_ws(lat, lon)
                except Exception as e:
                    log('Send error: {}', e)
            else:
                log('No GPS fix yet')
            last_gps_time = current_time  # reset GPS timer

        log('Sleeping for {} seconds', SLEEP_INTERVAL)
        time.sleep(SLEEP_INTERVAL)

if __name__ == "__main__":
    main()