"""
machine module in MicroPython
"""

from typing import Dict, Tuple, List, Callable

def soft_reset() -> None:
    pass

class I2C(object):
    def __init__(self, id=-1, *args, scl, sda, freq:int=400000):
        pass
    def init(self, scl, sda, freq:int=400000):
        pass
    def deinit(self):
        pass
    def scan(self) -> List[int]:
        pass

    def readfrom(self, addr:int, nbytes:int, stop:bool=True) -> bytes:
        pass
    def readfrom_into(self, addr:int, buf:bytearray, stop:bool=True) -> int:
        pass
    def writeto(self, addr:int, buf:bytes, stop:bool=True) -> int:
        pass

    def readfrom_mem(self, addr:int, memaddr:int, nbytes:int, addrsize:int=8) -> bytes:
        pass
    def readfrom_mem_into(self, addr:int, memaddr:int, buf:bytearray, addrsize:int=8) -> None:
        pass
    def writeto_mem(self, addr:int, memaddr:int, buf:bytes, addrsize:int=8) -> None:
        pass
