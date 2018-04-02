# from typing import Tuple, Callable, List
import logging
import pyb
import machine
import time
import uasyncio as asyncio
import wiolte

class WioLteDriver(object):
    def __init__(self):
        self.__lte = wiolte.wiolte.get_comm()
        self.__loop = asyncio.get_event_loop()
        self.__active = False
        self.__is_connected = False
        self.__thread = None
        
    def isconnected(self) -> bool:
        return self.__is_connected

    def active(self, is_active:bool=None) -> bool:
        if is_active is None:
            return self.__active
        if self.__active == is_active:
            return True
        
        if is_active:
            self.__lte.set_supply_power(to_supply=True)
            result = self.__loop.run_until_complete(self.__lte.turn_on_or_reset())
            if result:
                self.__active = True
                return True
            else:
                return False
        else:
            self.__lte.set_supply_power(to_supply=False)
            self.__active = False
            self.__is_connected = False
            return True
    
    def connect(self, access_point:str, user:str, password:str) -> None:
        if not self.__active:
            raise RuntimeError("Interface is not active.")
        if self.__loop.run_until_complete(self.__lte.activate(access_point, user, password)):
            self.__is_connected = True
    
    def disconnect(self) -> None:
        self.__is_connected = False
    
    def status(self, param:str=None) -> any:
        imei = self.__loop.run_until_complete(self.__lte.get_IMEI())
        imsi = self.__loop.run_until_complete(self.__lte.get_IMSI())
        rssi = self.__loop.run_until_complete(self.__lte.get_RSSI())
        return (imei, imsi, rssi)


theDriver = WioLteDriver()

def Driver() -> WioLteDriver:
    return theDriver
