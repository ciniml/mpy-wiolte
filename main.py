from wiolte import wiolte, LTEModule
from sht31 import SHT31
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

# Initialize humidity sensor
i2c = machine.I2C(1)
address_sht31 = i2c.scan()
if len(address_sht31) > 0:
    l.info("Found SHT31 at address %02x", address_sht31[0])
    sensor_sht = SHT31(i2c, address_sht31[0])
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

def put_string(buffer:memoryview, length:int, utf8:bytes) -> int:
    struct.pack_into('>H', buffer, 0, length)
    if length > 0:
        buffer[2:2+length] = utf8
        return length + 2
    else:
        return 2

def get_string(buffer:memoryview) -> Tuple[int, memoryview]:
    length = struct.unpack_from('>H', buffer)
    if length == 0 :
        return (2, '')
    else:
        return (2 + length, buffer[2:2+length])

def put_remaining_length(buffer:memoryview, remaining_length:int) -> int:
    if remaining_length < 0:
        raise ValueError()
    
    count = 0
    while count == 0 or remaining_length > 0:
        byte = remaining_length & 0x7f
        remaining_length >>= 7
        if remaining_length > 0:
            byte |= 0x80
        buffer[count] = byte
        count += 1
    return count

def get_remaining_length(buffer:memoryview) -> Tuple[int,int]:
    index = 0
    remaining_length = 0
    shift = 0
    byte = 0x80
    while (byte & 0x80) != 0:
        byte = buffer[index]
        remaining_length += (byte & 0x7f) << shift
        shift += 7
        if shift > 21:
            raise ValueError("Invalid remaining length")
        index += 1
    return (index, remaining_length)


def put_fixed_header(buffer:memoryview, packet_type:int, flags:int, remaining_length:int) -> int:
    buffer[0] = (packet_type << 4) | flags
    return put_remaining_length(buffer[1:], remaining_length) + 1

def get_fixed_header(buffer:memoryview) -> Tuple[int, Tuple[int, int, int]]:
    packet_type = buffer[0] >> 4
    flags = buffer[0] & 0xf
    index, remaining_length = get_remaining_length(buffer[1:])
    return (index + 1, (packet_type, flags, remaining_length))

def put_packet_id(buffer:memoryview, packet_id:int) -> int:
    struct.pack_into('>H', buffer, packet_id)
    return 2

async def receive_response(m:LTEModule, conn:int, buffer:memoryview, timeout:int=None) -> Tuple[Tuple[int, int, int], memoryview]:
    length = await m.socket_receive(conn, buffer, 0, 4, timeout)
    if length is None or length < 2:
        return None, None
    i, (packet_type, flags, remaining_length) = get_fixed_header(buffer)
    if remaining_length + i > length:
        length = await m.socket_receive(conn, buffer, i, remaining_length, timeout)
        if length is None:
            return None, None
    return (packet_type, flags, remaining_length), buffer[i:i+remaining_length]

class ControlPacketType(object):
    CONNECT = const(1)
    CONNACK = const(2)
    PUBLISH = const(3)
    PUBACK = const(4)
    PUBREC = const(5)
    PUBREL = const(6)
    PUBCOMP = const(7)
    SUBSCRIBE = const(8)
    SUBACK = const(9)
    UNSUBSCRIBE = const(10)
    UNSUBACK = const(11)
    PINGREQ = const(12)
    PINGRESP = const(13)
    DISCONNECT = const(14)

class ConnectFlags(object):
    UserNameFlag = const(0x80)
    PasswordFlag = const(0x40)
    WillRetain = const(0x20)
    WillQoS_0 = const(0x00)
    WillQoS_1 = const(0x08)
    WillQoS_2 = const(0x10)
    WillQoS_3 = const(0x18)
    WillFlag = const(0x04)
    CleanSession = const(0x02)


def make_connect(buffer:bytearray, client_name:str, user_name:str=None, password:str=None, keep_alive:int=10) -> int:
    client_name_bytes = bytes(client_name, 'utf-8')
    client_name_length = len(client_name_bytes) + 2
    user_name_bytes = bytes(user_name, 'utf-8') if user_name is not None else None
    user_name_length = len(user_name_bytes) + 2 if user_name is not None else 0
    password_bytes = bytes(password, 'utf-8') if password is not None else None
    password_length = len(password_bytes) + 2 if password is not None else 0
    flags = ConnectFlags.CleanSession
    flags |= ConnectFlags.UserNameFlag if user_name is not None else 0
    flags |= ConnectFlags.PasswordFlag if password is not None else 0
        
    remaining_length = 10 + client_name_length + user_name_length + password_length
    mv = memoryview(buffer)
    i = 0
    i += put_fixed_header(mv[i:], ControlPacketType.CONNECT, 0, remaining_length)
    i += put_string(mv[i:], 4, b'MQTT')
    mv[i] = 4; i += 1        # Protocol Version
    mv[i] = flags; i += 1    # Flags
    struct.pack_into('>H', mv, i, keep_alive); i += 2   # Keep Alive
    i += put_string(mv[i:], client_name_length-2, client_name_bytes)  # Client Name
    if user_name_bytes is not None:
        i += put_string(mv[i:], user_name_length-2, user_name_bytes)    # User Name
    if password_bytes is not None:
        i += put_string(mv[i:], password_length-2, password_bytes)    # User Name
    return remaining_length + 2

def make_disconnect(buffer:bytearray) -> int:
    mv = memoryview(buffer)
    put_fixed_header(mv[0:], ControlPacketType.DISCONNECT, 0, 0)
    put_remaining_length(mv[1:], 0)
    return 2


def make_publish(buffer:bytearray, topic:str, payload:bytes=None, payload_length:int=None) -> int:
    topic_bytes = bytes(topic, 'utf-8')
    topic_length = len(topic_bytes)
    payload_length = 0 if payload is None else (len(payload) if payload_length is None else payload_length)
    remaining_length = topic_length + 2 + (payload_length + 2 if payload_length > 0 else 0)

    mv = memoryview(buffer)
    i = 0
    i += put_fixed_header(mv[i:], ControlPacketType.PUBLISH, 0, remaining_length)
    i += put_string(mv[i:], topic_length, topic_bytes)
    i += put_string(mv[i:], payload_length, payload)
    
    return remaining_length + 2

async def main_task():
    while not await m.turn_on_or_reset():
        await asyncio.sleep_ms(1000)
    
    log = logging.Logger('main') # type: logging.Logger

    log.info('LTE connection is now available.')
    rssi = await m.get_RSSI()
    log.info('RSSI: %s', str(rssi))

    while not await m.activate('soracom.io', 'sora', 'sora', timeout=5000):
        pass
    
    log.info('LTE network has been activated.')

    buffer = bytearray(1024)

    while True:
        connected = False
        while not connected:
            conn = await m.socket_open('beam.soracom.io', 1883, m.SOCKET_TCP)
            log.info('Connection to SORACOM Beam = {0}'.format(conn))
    
            length = make_connect(buffer, client_name="wiolte", keep_alive=120)
            log.debug("CONNECT: %s", buffer[:length])
            if not await m.socket_send(conn, buffer, offset=0, length=length, timeout=1000):
                await m.socket_close(conn, timeout=1000)
                continue
            
            for i in range(10):
                response, body = await receive_response(m, conn, buffer, timeout=1000)
                if response is None:
                    await asyncio.sleep_ms(100)
                    continue
            
                packet_type, flags, remaining_length = response
                log.debug("RESPONSE: %x, %x, %d", packet_type, flags, remaining_length)
                if packet_type == ControlPacketType.CONNACK and remaining_length == 2:
                    return_code = body[1]
                    if return_code != 0:
                        log.error("CONNECT failed. error=%d", return_code)
                    else:
                        log.info("CONNECT success")
                    connected = return_code == 0
                    break
                
            if not connected:
                length = make_disconnect(buffer)
                await m.socket_send(conn, buffer, offset=0, length=length, timeout=5000)
                await m.socket_close(conn, timeout=1000)
                await asyncio.sleep_ms(5000)

        while m.socket_is_connected(conn):
            if sensor_sht is not None:
                sensor_value = sensor_sht.read()
                if sensor_value[0] is not None:
                    payload = '{{"temperature":{0},"humidity":{1}}}'.format(*sensor_value)
                    length = make_publish(buffer, 'devices/wiolte/messages/events/', bytes(payload, 'utf-8'))
                    if not await m.socket_send(conn, buffer, length=length, timeout=5000):
                        break
            await asyncio.sleep_ms(30000)

        await m.socket_close(conn)
        
loop = asyncio.get_event_loop()
loop.run_until_complete(main_task())

