from wiolte import wiolte
import unetwork as network
import usocket as socket
import umqtt.simple
import machine
import utime as time

try:
    from mpy_builtins import *
    from typing import Tuple, Callable, List
except:
    pass

def reset():
    pyb.sync()
    machine.soft_reset()

wiolte.initialize()

driver = network.Driver()

while not driver.active(is_active=True):
    print("The module did not go active before timed out.\n")

driver.connect(access_point='soracom.io', user='sora', password='sora')

client = umqtt.simple.MQTTClient('wiolte', 'beam.soracom.io', 1883)
while not client.connect():
    time.sleep_ms(1000)

while True:
    print('Publish message\n')
    client.publish('devices/wiolte/messages/events/', b'Hello from MicroPython on WioLTE')
    time.sleep_ms(5000)
