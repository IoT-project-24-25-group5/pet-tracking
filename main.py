import sys
sys.path.append('/flash/shields')

import time

import gc
import pycom
from lib.L76GNSS import L76GNSS
from lib.pycoproc_1 import Pycoproc
from network import WLAN
wlan = WLAN()
wlan.antenna(WLAN.EXT_ANT)

pycom.heartbeat(False)
pycom.rgbled(0x0A0A08) # white
 
time.sleep(2)
gc.enable()
 
py = Pycoproc(Pycoproc.PYTRACK)
 
time.sleep(1)
l76 = L76GNSS(py, timeout=30, buffer=512)

time.sleep(1)
 
while (True):
    coord = l76.coordinates(debug=True)
    print()
    print(coord)
    print("{} - {}".format(coord, gc.mem_free()))
    print('Sleep for 5 seconds.')
    time.sleep(5)