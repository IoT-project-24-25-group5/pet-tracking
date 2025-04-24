import sys
sys.path.append('/flash/shields')

import time

import gc
import pycom
from lib.L76GNSS import L76GNSS
from lib.pycoproc_1 import Pycoproc
from network import WLAN
import machine
import socket
import ssl


HOST = 'iot.philippevoet.dev'


# swith signal towards exteranl antenna
wlan = WLAN(mode=WLAN.STA)
wlan.connect(ssid='', auth=(WLAN.WPA2, ''))
while not wlan.isconnected():
    machine.idle()
print("WiFi connected succesfully")

pycom.heartbeat(False)
pycom.rgbled(0x0A0A08) # white
 
time.sleep(2)
gc.enable()
 
py = Pycoproc(Pycoproc.PYTRACK)
 
time.sleep(1)
l76 = L76GNSS(py, timeout=60, buffer=512)

time.sleep(1)
 
while (True):
    coord = l76.coordinates(debug=True)
    
    lat, lon = coord[0], coord[1] 
    print("{} - {}".format(coord, gc.mem_free()))
    
    """lat = "51.203141"
    lon = "4.420835"""

    if lat is not None and lon is not None:
        try:
            path = '/location'
            addr = socket.getaddrinfo(HOST, 443)[0][-1]
            s = socket.socket()
            ss = ssl.wrap_socket(s)
            ss.connect(addr)

            # Send HTTPS POST manually (raw HTTP)
            payload = '{{"latitude": {}, "longitude": {}}}'.format(lat, lon)
            request = (
                "POST {} HTTP/1.1\r\n"
                "Host: {}\r\n"
                "Content-Type: application/json\r\n"
                "Content-Length: {}\r\n"
                "\r\n"
                "{}"
            ).format(path, HOST, len(payload), payload)

            ss.send(request)
            print("Data sent to server")

            print(ss.recv(256))
            ss.close()
            
        except Exception as e:
            print("error sending coordinates" , e)
    
    print('Sleep for 20 seconds.')
    time.sleep(20)
