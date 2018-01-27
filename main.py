from wiolte import LTEModule
import pyb
import logging
import struct

logging.basicConfig(logging.DEBUG)

m = LTEModule()
m.initialize()
m.set_supply_power(True)

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
    
    connect_packet = bytearray(1024)
    connect_packet[0] = 0x10
    connect_packet[1] = 20  # Remain length
    connect_packet[2] = 0
    connect_packet[3] = 6
    connect_packet[4:10] = b'MQIsdp'
    connect_packet[10] = 3
    connect_packet[11] = 0x02
    connect_packet[12] = 0x00
    connect_packet[13] = 0x0a
    connect_packet[14] = 0
    connect_packet[15] = 6
    connect_packet[16:22] = b'wiolte'
    m.socket_send(conn, connect_packet, offset=0, length=22)
    buffer = bytearray(1024)
    for i in range(10):
        n = m.socket_receive(conn, buffer)
        if n == 4: break
        pyb.delay(100)
    
    length = make_publish(buffer, 'devices/wiolte/messages/events/', b'Hello from MicroPython on WioLTE')
    m.socket_send(conn, buffer, length=length)

