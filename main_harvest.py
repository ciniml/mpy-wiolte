from wiolte import wiolte, LTEModule
from sht31 import SHT31
from bmp280 import BMP280
import pyb
import logging
import struct
import uasyncio as asyncio
import time

try:
    from mpy_builtins import *
    from typing import Tuple, Callable, List
except:
    pass

def reset():
    pyb.sync()
    machine.soft_reset()

logging.basicConfig(logging.DEBUG)
l = logging.Logger('MAIN')

# Initialize Wio LTE module
wiolte.initialize()
wiolte.set_grove_power(False)
time.sleep(1)
wiolte.set_grove_power(True)

# Initialize LTE modem
m = wiolte.get_comm()
m.set_supply_power(True)

# Initialize barometer sensor
i2c = machine.I2C(1)
sensor_bmp = BMP280(i2c, 0x77)
sensor_bmp.reset()
sensor_bmp.configure()

# Initialize humidity sensor
pin_d38 = pyb.Pin('D38')    # D38:SCL
pin_d39 = pyb.Pin('D39')    # D39:SDA
i2c_d38 = machine.I2C(scl=pin_d38, sda=pin_d39)

address_sht31 = i2c_d38.scan()
if len(address_sht31) > 0:
    l.info("Found SHT31 at address %02x", address_sht31[0])
    sensor_sht = SHT31(i2c_d38, address_sht31[0])
    sensor_sht.stop_measurement()
    if not sensor_sht.reset():
        l.error("Failed to reset SHT31")
    if not sensor_sht.set_heater(True):
        l.error("Failed to enable heater of SHT31")
    if not sensor_sht.start_measurement(repeatability=SHT31.REPEATABILITY_MEDIUM, mps=SHT31.MPS_10):
        l.error("Failed to start SHT31 measurement")
        sensor_sht = None
else:
    l.error("Failed to detect SHT31")

async def main_task():
    # Wait until the LTE module gets ready to communicate.
    while not await m.turn_on_or_reset():
        await asyncio.sleep_ms(1000)
    
    log = logging.Logger('main') # type: logging.Logger

    log.info('LTE connection is now available.')
    rssi = await m.get_RSSI()
    log.info('RSSI: %s', str(rssi))

    # Activate LTE network.
    while not await m.activate('soracom.io', 'sora', 'sora', timeout=5000):
        pass
    
    log.info('LTE network has been activated.')

    buffer = bytearray(1024)
    while True:
        connected = False
        # Connect to SORACOM Harvest endpoint.
        while not connected:
            conn = await m.socket_open('harvest.soracom.io', 8514, m.SOCKET_UDP)
            log.info('Connection to SORACOM Harvest = {0}'.format(conn))
            if conn is None:
                # Failed to connect. Retry after 10[s]
                await asyncio.sleep_ms(10000)
                continue
            connected = True

        while m.socket_is_connected(conn):
            # Read sensor value.
            sht_value = sensor_sht.read() if sensor_sht is not None else None
            bmp_value = sensor_bmp.read() if sensor_bmp is not None else None

            temperature = sht_value[0] if sht_value is not None else 'null'
            humidity    = sht_value[1] if sht_value is not None else 'null'
            pressure    = bmp_value[0] if bmp_value is not None else 'null'
            temperature = bmp_value[1] if bmp_value is not None else temperature

            # Construct data to transmit to SORACOM Harvest
            payload = '{{"temperature":{0},"humidity":{1},"pressure":{2}}}\n'.format(temperature, humidity, pressure)
            log.info("Send: %s", payload)
            payload_bytes = bytes(payload, 'utf-8')
            # Transmit data
            if not await m.socket_send(conn, payload_bytes, length=len(payload_bytes), timeout=5000):
                break
            # Receive response.
            length = await m.socket_receive(conn, buffer, timeout=5000)
            if length is not None:
                if buffer[:length] != b'201':
                    log.error('ERROR: invalid response - %s', buffer[:length])
            # Wake up after 120[s] 
            await asyncio.sleep_ms(1000*60*2)

        await m.socket_close(conn)

loop = asyncio.get_event_loop()
loop.run_until_complete(main_task())

uart_ec21 = machine.UART(2)
uart_ec21.init(baudrate=115200, timeout=5000, timeout_char=1000)
