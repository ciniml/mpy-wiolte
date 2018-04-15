import logging
import struct
try:
    from mpy_builtins import machine, pyb, const
    from typing import Tuple, Callable, List
except:
    import pyb
    import machine

class BMP280(object):
    "BMP280 Digital Pressure sensor driver"

    DEFAULT_ADDRESS = const(0x77)

    OVERSAMPLING_SKIPPED = const(0x0)
    OVERSAMPLING_1  = const(0x1)
    OVERSAMPLING_2  = const(0x2)
    OVERSAMPLING_4  = const(0x3)
    OVERSAMPLING_8  = const(0x4)
    OVERSAMPLING_16 = const(0x5)

    POWERMODE_SLEEP = const(0x0)
    POWERMODE_FORCED = const(0x1)
    POWERMODE_NORMAL = const(0x3)

    STANDBY_0_5  = const(0x0)
    STANDBY_62_5 = const(0x1)
    STANDBY_125  = const(0x2)
    STANDBY_250  = const(0x3)
    STANDBY_500  = const(0x4)
    STANDBY_1000 = const(0x5)
    STANDBY_2000 = const(0x6)
    STANDBY_4000 = const(0x7)

    IIR_OFF = const(0x0)
    IIR_2   = const(0x1)
    IIR_4   = const(0x2)
    IIR_8   = const(0x3)
    IIR_16  = const(0x4)

    def __init__(self, i2c:machine.I2C, address:int):
        "Construct BMP280 driver for the device which has 'address' on the 'i2c' bus."
        self.__l = logging.Logger('BMP280')
        self.__i2c = i2c
        self.__address = address
        

    def reset(self) -> bool:
        "Reset this BMP280 device."

        self.__i2c.writeto_mem(self.__address, 0xe0, bytes(0xb6))
        result = self.__i2c.readfrom_mem(self.__address, 0xd0, 1)
        if not len(result) == 1 and result[0] == 0x58:
            return False
        # Read trimming data
        calibration_bytes = self.__i2c.readfrom_mem(self.__address, 0x88, 26)
        if len(calibration_bytes) != 26:
            return False
        cal = struct.unpack('<HhhHhhhhhhhh', calibration_bytes)
        self.__dig_T1 = float(cal[ 0])
        self.__dig_T2 = float(cal[ 1])
        self.__dig_T3 = float(cal[ 2])
        self.__dig_P1 = float(cal[ 3])
        self.__dig_P2 = float(cal[ 4])
        self.__dig_P3 = float(cal[ 5])
        self.__dig_P4 = float(cal[ 6])
        self.__dig_P5 = float(cal[ 7])
        self.__dig_P6 = float(cal[ 8])
        self.__dig_P7 = float(cal[ 9])
        self.__dig_P8 = float(cal[10])
        self.__dig_P9 = float(cal[11])
        
        return True

    def configure(self, power_mode:int=POWERMODE_NORMAL, oversampling_pressure:int=OVERSAMPLING_1, oversampling_temperature:int=OVERSAMPLING_1, standby_period:int=STANDBY_1000, iir_coefficient:int=IIR_OFF):
        "Configure this BMP280 device"
        # Enter to SLEEP mode to update config register.
        self.__i2c.writeto(self.__address, bytes((0xf4, 0x00)))
        # Update config register and ctrl_meas register.
        config = ((standby_period&7) << 5) | ((iir_coefficient&7) << 2)
        self.__i2c.writeto(self.__address, bytes((0xf5, config)))
        ctrl_meas = ((oversampling_temperature&7) << 5) | ((oversampling_pressure&7) << 2) | (power_mode&3)
        self.__i2c.writeto(self.__address, bytes((0xf4, ctrl_meas)))
        
    
    def read_raw(self) -> bytes:
        "Read measured data from this device and return it without calibration."
        try:
            return self.__i2c.readfrom_mem(self.__address, 0xf7, 6)
        except OSError:
            return None

    def read(self) -> (float, float):
        "Read measured data and calculate calibrated values. This function returns 2-ple whose first element is measured pressure value in [P] and second element is measured temperature value in [C]."
        raw = self.read_raw()
        if raw is None:
            return None

        raw_P, xlsb_P, raw_T, xlsb_T = struct.unpack('>HBHB', raw)
        adc_T = (raw_T << 4) | (xlsb_T >> 4)
        adc_P = (raw_P << 4) | (xlsb_P >> 4)
        self.__l.debug("adc_T=%d, adc_P=%d", adc_T, adc_P)

        # Calibration formula from BMP280 datasheet.
        v1 = ((adc_T/16384.0) - (self.__dig_T1/1024.0))*self.__dig_T2
        v2 = (adc_T/131072.0) - (self.__dig_T1/8192.0)
        v2 = v2*v2*self.__dig_T3
        t_fine = v1 + v2
        T = (v1 + v2)/5120.0

        v1 = t_fine/2.0 - 64000.0
        v2 = v1*v1*self.__dig_P6/32768.0
        v2 = v2 + v1*self.__dig_P5*2.0
        v2 = v2/4.0 + self.__dig_P4*65536.0
        v1 = (self.__dig_P3*v1*v1/524288.0 + self.__dig_P2*v1)/524288.0
        v1 = (1.0 + v1/32768.0)*self.__dig_P1
        if v1 == 0.0:
            P = 0.0
        else:
            P = 1048576.0 - adc_P
            P = (P - (v2 / 4096.0)) * 6250.0 / v1
            self.__l.debug("P_before_comp: %f", P)
            v1 = self.__dig_P9*P*P/2147483648.0
            v2 = P*self.__dig_P8/32768.0
            P = P + (v1 + v2  + self.__dig_P7)/16.0
        return (P, T)

        

