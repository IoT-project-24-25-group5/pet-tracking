import sys
import time
import gc
import machine
import socket
import ssl
import ujson

import pycom
from network import WLAN

# Append shield libs
sys.path.append('/flash/shields')
from lib.L76GNSS import L76GNSS
from lib.pycoproc_1 import Pycoproc
from lib.LIS2HH12 import LIS2HH12
from lib.client import connect
from lib.protocol import Websocket

import binascii

# Configuration
WIFI_SSID = 'stop using our Telenet'
WIFI_PASS = '1020304050'
HOST = 'iot.philippevoet.dev'
PORT = 443
POST_PATH = '/location'
SLEEP_INTERVAL = 2  # seconds
GPS_TIMEOUT = 60  # seconds
GPS_BUFFER = 512
DEBUG = True

WS_HOST = 'wss://iot.philippevoet.dev'  # Make sure your server supports secure WebSockets (wss)


def log(msg, *args):
    """Formatted logging with optional debug output"""
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

"""
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

def send_lora_payload(lora, lat, lon):
    s = socket.socket(socket.AF_LORA, socket.SOCK_RAW)
    s.setsockopt(socket.SOL_LORA, socket.SO_DR, 5)
    s.setblocking(True)

    # Encode payload
    payload = bytearray()
    payload.extend(int(lat * 10000).to_bytes(4, 'big', signed=True))
    payload.extend(int(lon * 10000).to_bytes(4, 'big', signed=True))
    s.send(payload)
    log("LoRaWAN payload sent")
"""



def send_location_ws(lat, lon):
    try:
        ws = connect(WS_HOST)
        payload = ujson.dumps({"type": "location", "latitude": lat, "longitude": lon})
        ws.send(payload)
        log("WebSocket sent: {}", payload)
        ws.close()
    except Exception as e:
        log("WebSocket error: {}", e)

def init_sensors():
    py = Pycoproc(Pycoproc.PYTRACK)
    time.sleep(1)
    gps = L76GNSS(py, timeout=GPS_TIMEOUT, buffer=GPS_BUFFER)
    accel = LIS2HH12(py)
    return gps, accel


def get_coordinates(gps, debug=False):
    coords = gps.coordinates(debug=debug)
    lat, lon = coords[0], coords[1]
    return lat, lon


def send_location(lat, lon):
    payload = '{{"latitude": {lat}, "longitude": {lon}}}'.format(lat=lat, lon=lon)
    request = '\r\n'.join([
        'POST {} HTTP/1.1'.format(POST_PATH),
        'Host: {}'.format(HOST),
        'Content-Type: application/json',
        'Content-Length: {}'.format(len(payload)),
        '', payload
    ])

    addr_info = socket.getaddrinfo(HOST, PORT)[0][-1]
    s = socket.socket()
    try:
        ssl_sock = ssl.wrap_socket(s)
        ssl_sock.connect(addr_info)
        ssl_sock.send(request)
        response = ssl_sock.recv(512)
        log('Server response: {}', response)
    finally:
        ssl_sock.close()


def main():
    pycom.heartbeat(False)
    pycom.rgbled(0x0A0A08)
    time.sleep(2)
    gc.enable()

    log('GC enabled, free memory: {}', gc.mem_free())

    log("updated")

    # Try Wi-Fi
    wifi_available = True
    try:
        wlan = connect_wifi(WIFI_SSID, WIFI_PASS)
    except Exception as e:
        log('WiFi failed, falling back to LoRaWAN: {}', e)
        wifi_available = False

    gps, accel = init_sensors()
    log('Sensors initialized')

    """
    # Join LoRaWAN if Wi-Fi failed
    if not wifi_available:
        try:
            app_eui = binascii.unhexlify('C0D4437F77F3505B')
            app_key = binascii.unhexlify('46A94F82F3E876ECBED1F28B03F2E47A')  
            lora = join_lorawan(app_eui, app_key)
        except Exception as e:
            log("LoRaWAN error: {}", e)
            machine.reset()
    """
    while True:
        try:
            ax, ay, az = accel.acceleration()
            log('Acceleration: x={:.2f}g, y={:.2f}g, z={:.2f}g', ax, ay, az)
        except Exception as e:
            log('Accel error: {}', e)

        lat, lon = get_coordinates(gps, debug=DEBUG)
        lat = 51.20325791712549
        lon = 4.4201269367747456
        if lat is not None and lon is not None:
            log('Coordinates: lat={}, lon={}', lat, lon)
            try:
                if wifi_available:
                    send_location_ws(lat, lon)
                else:
                    send_lora_payload(lora, lat, lon)
            except Exception as e:
                log('Send error: {}', e)
        else:
            log('No GPS fix yet')

        log('Sleeping for {} seconds', SLEEP_INTERVAL)
        time.sleep(SLEEP_INTERVAL)



if __name__ == '__main__':
    main()