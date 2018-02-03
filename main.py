from wiolte import LTEModule
import pyb
import logging
import struct

logging.basicConfig(logging.DEBUG)

m = LTEModule()
m.initialize()
m.set_supply_power(True)

def make_connect(buffer:bytearray, client_name:str) -> int:
    client_name_bytes = bytes(client_name, 'utf-8')
    client_name_length = len(client_name_bytes)
    remaining_length = client_name_length
    buffer[0] = 0x10                # CONNECT
    buffer[1] = remaining_length    # remaining_length
    buffer[2] = 0               # Protocol Name
    buffer[3] = 6               # 
    buffer[4:10] = b'MQIsdp'    # 
    buffer[10] = 3              # Protocol Version
    buffer[11] = 0x02           # Flags
    buffer[12] = 0x00           #
    buffer[13] = 0x0a           #
    buffer[14] = 0                                          # Client Name
    buffer[15] = client_name_length                         #
    buffer[16:16+client_name_length] = client_name_bytes    #

    return remaining_length + 2

def make_publish(buffer:bytearray, topic:str, payload:bytes=None, payload_length:int=None) -> int:
    topic_bytes = bytes(topic, 'utf-8')
    topic_length = len(topic_bytes)
    payload_length = 0 if payload is None else (len(payload) if payload_length is None else payload_length)
    remaining_length = topic_length + 2 + (payload_length + 2 if payload_length > 0 else 0)
    buffer[0] = 0x30
    buffer[1] = remaining_length
    buffer[2] = 0
    buffer[3] = topic_length
    buffer[4:4+topic_length] = topic_bytes
    buffer[4+topic_length] = 0
    buffer[4+topic_length] = payload_length
    if payload_length > 0:
        buffer[6+topic_length:6+topic_length+payload_length] = payload[:payload_length]
    return remaining_length + 2

if m.turn_on_or_reset():
    print('LTE connection is now available.')
    print(m.get_RSSI())

    m.activate('soracom.io', 'sora', 'sora')
    conn = m.socket_open('beam.soracom.io', 1883, m.SOCKET_TCP)
    print('Connection to SORACOM Beam = {0}'.format(conn))
    
    buffer = bytearray(1024)
    length = make_connect(buffer, "wiolte")
    m.socket_send(conn, buffer, offset=0, length=length)
    
    for i in range(10):
        n = m.socket_receive(conn, buffer)
        if n == 4: break
        pyb.delay(100)
    
    length = make_publish(buffer, 'devices/wiolte/messages/events/', b'Hello from MicroPython on WioLTE')
    m.socket_send(conn, buffer, length=length)

