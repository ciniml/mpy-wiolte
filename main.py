from wiolte import LTEModule
import logging

logging.basicConfig(logging.DEBUG)

m = LTEModule()
m.initialize()
m.set_supply_power(True)
if m.turn_on_or_reset():
    print('LTE connection is now available.')
    print(m.get_RSSI())

