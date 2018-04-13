import logging
import struct
try:
    from mpy_builtins import machine, pyb, const
    from typing import Tuple, Callable, List
except:
    import pyb
    import machine

class SHT31(object):
    REPEATABILITY_HIGH = const(0)
    REPEATABILITY_MEDIUM = const(1)
    REPEATABILITY_LOW = const(2)
    MPS_0_5 = const(0)
    MPS_1   = const(1)
    MPS_2   = const(2)
    MPS_4   = const(3)
    MPS_10  = const(4)
    
    PERIODIC_MSB = [
        0x20,
        0x21,
        0x22,
        0x23,
        0x27,
    ]
    PERIODIC_LSB = {
        (REPEATABILITY_HIGH  , MPS_0_5): 0x32,
        (REPEATABILITY_MEDIUM, MPS_0_5): 0x24,
        (REPEATABILITY_LOW   , MPS_0_5): 0x2f,
        (REPEATABILITY_HIGH  , MPS_1  ): 0x30,
        (REPEATABILITY_MEDIUM, MPS_1  ): 0x26,
        (REPEATABILITY_LOW   , MPS_1  ): 0x2d,
        (REPEATABILITY_HIGH  , MPS_2  ): 0x36,
        (REPEATABILITY_MEDIUM, MPS_2  ): 0x20,
        (REPEATABILITY_LOW   , MPS_2  ): 0x2b,
        (REPEATABILITY_HIGH  , MPS_4  ): 0x34,
        (REPEATABILITY_MEDIUM, MPS_4  ): 0x22,
        (REPEATABILITY_LOW   , MPS_4  ): 0x29,
        (REPEATABILITY_HIGH  , MPS_10 ): 0x37,
        (REPEATABILITY_MEDIUM, MPS_10 ): 0x21,
        (REPEATABILITY_LOW   , MPS_10 ): 0x2a,
    }
    def __init__(self, i2c:machine.I2C, address:int):
        self.__l = logging.Logger('SHT31')
        self.__i2c = i2c
        self.__address = address

    def reset(self) -> bool:
        return self.__i2c.writeto(self.__address, bytes((0x30, 0xa2)), True) == 2

    def start_measurement(self, repeatability:int=REPEATABILITY_LOW, mps:int=MPS_1):
        if mps < 0 or len(SHT31.PERIODIC_MSB) <= mps:
            raise ValueError()
        if (repeatability, mps) not in SHT31.PERIODIC_LSB:
            raise ValueError()
        msb = SHT31.PERIODIC_MSB[mps]
        lsb = SHT31.PERIODIC_LSB[(repeatability, mps)]

        return self.__i2c.writeto(self.__address, bytes((msb, lsb)), True) == 2

    def stop_measurement(self):
        return self.__i2c.writeto(self.__address, bytes((0x30, 0x93)), True) == 2

    def set_heater(self, enable_heater:bool) -> bool:
        lsb = 0x6d if enable_heater else 0x66
        return self.__i2c.writeto(self.__address, bytes((0x30, lsb)), True) == 2

    def read_raw(self) -> bytes:
        try:
            return self.__i2c.readfrom_mem(self.__address, 0xe000, 6, addrsize=16)
        except OSError:
            return None

    def read(self) -> (float, float):
        raw = self.read_raw()
        if raw is None:
            return (None, None)
        values = struct.unpack('>HBHB', raw)
        return (
            values[0]/65535.0*175 -45,
            values[2]/65535.0*315 -49,
        )
