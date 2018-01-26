from wiolte import LTEModule
import logging
import struct

logging.basicConfig(logging.DEBUG)

m = LTEModule()
m.initialize()
m.set_supply_power(True)
if m.turn_on_or_reset():
    print('LTE connection is now available.')
    print(m.get_RSSI())

    m.activate('soracom.io', 'sora', 'sora')
    conn = m.socket_open('beam.soracom.io', 1883, m.SOCKET_TCP)
    print('Connection to SORACOM Beam = {0}'.format(conn))
    
