# from typing import Tuple, Callable, List
import logging
import pyb

class WioLTE(object):
    def __init__(self):
        self.__comm = LTEModule()
        
    def initialize(self):
        pass

    def get_comm(self) -> LTEModule:
        return self.__comm
        
class LTEModule(object):
    "Controls Quectel EC21 LTE Module"
    CR = const(0x0d)
    LF = const(0x0a)

    def __init__(self):
        self.__l = logging.Logger('LTEModule')
        
        self.__pin_reset_module = pyb.Pin('RESET_MODULE')
        self.__pin_dtr_module = pyb.Pin('DTR_MODULE')
        self.__pin_pwrkey_module = pyb.Pin('PWRKEY_MODULE')
        self.__pin_module_power = pyb.Pin('M_POWR')
        self.__pin_module_status = pyb.Pin('PB15')
        self.__pin_disable_module = pyb.Pin('W_DISABLE')
        self.__pin_wakeup_module = pyb.Pin('WAKEUP_IN')
        
        self.__uart = pyb.UART(2)

    def initialize(self) -> None:
        "Initialize I/O ports and peripherals to communicate with the module."
        self.__l.debug('initialize')
        
        self.__pin_reset_module.init(pyb.Pin.OUT_PP)
        self.__pin_dtr_module.init(pyb.Pin.OUT_PP)
        self.__pin_pwrkey_module.init(pyb.Pin.OUT_PP)
        self.__pin_module_power.init(pyb.Pin.OUT_PP)
        self.__pin_module_status.init(pyb.Pin.IN)
        self.__pin_disable_module.init(pyb.Pin.OUT_PP)
        self.__pin_wakeup_module.init(pyb.Pin.OUT_PP)
        
        self.__pin_dtr_module.off()
        self.__pin_pwrkey_module.off()
        self.__pin_module_power.off()
        self.__pin_reset_module.on()
        self.__pin_disable_module.on()
        self.__pin_wakeup_module.off()
        
        self.__uart.init(baudrate=115200, flow=pyb.UART.CTS|pyb.UART.RTS, timeout=5000, timeout_char=1000)

    def set_supply_power(self, to_supply:bool):
        "Enable/Disable power supply to the module."
        self.__pin_module_power.value(1 if to_supply else 0)

    def reset(self) -> bool:
        "Reset the module."
        self.__pin_reset_module.off()
        pyb.delay(200)
        while self.__uart.any():
            self.__uart.read(self.__uart.any())
        self.__pin_reset_module.on()
        pyb.delay(300)

        for trial in range(15):
            if self.wait_response(b'RDY') is not None:
                return True
        return False

    def wait_busy(self, max_trials:int=50) -> bool:
        "Wait while the module is busy."
        self.__l.debug('Waiting busy...')
        for trial in range(max_trials):
            if not self.is_busy():
                return True
            pyb.delay(100)
        self.__l.debug('Failed.')
        return False

    def turn_on(self) -> bool:
        "Turn on the module."
        pyb.delay(100)
        self.__pin_pwrkey_module.on()
        pyb.delay(200)
        self.__pin_pwrkey_module.off()

        if not self.wait_busy():
            return False

        for trial in range(15):
            if self.wait_response(b'RDY') is not None:
                return True
        return False

    def turn_on_or_reset(self) -> bool:
        "Turn on or reset the module and wait until the LTE commucation gets available."
        if self.is_busy():
            if not self.turn_on():
                return False
        else:
            if not self.reset():
                return False
        
        if not self.write_command_wait(b'AT', b'OK'):    # Check if the module can accept commands.
            return False
        if not self.write_command_wait(b'ATE0', b'OK'):  # Disable command echo
            return False
        if not self.write_command_wait(b'AT+QURCCFG="urcport","uart1"', b'OK'):  # Use UART1 port
            return False

        buffer = bytearray(1024)
        result, responses = self.execute_command('AT+QSCLK=1', buffer, expected_response_list=[b'OK', b'ERROR'])
        if not result:
            return False
        
        self.__l.info('Waiting SIM goes active...')
        while True:
            result, responses = self.execute_command('AT+CPIN?', buffer)
            if len(responses) == 0: return False
            if result: return True
            pyb.delay(1000)
        
        
    def is_busy(self) -> bool:
        return bool(self.__pin_module_status.value())

    def write(self, s:bytes) -> None:
        self.__l.debug('<- ' + s)
        self.__uart.write(s)
    
    def read(self, length:int) -> bytes:
        return self.__uart.read(length)
    
    def write_command(self, command:bytes) -> None:
        self.__l.debug('<- %s', command)
        self.__uart.write(command)
        self.__uart.write('\r')

    def write_command_wait(self, command:bytes, expected_response:bytes) -> bool:
        self.write_command(command)
        return self.wait_response(expected_response) is not None

    def read_response_into(self, buffer:bytearray, offset:int=0) -> int:
        buffer_length = len(buffer)
        response_length = 0
        state = 0
        while True:
            c = self.__uart.readchar()
            if c < 0: return None  # Timed out
            #self.__l.debug('S:%d R:%c', state, c)
            if state == 0 and c == LTEModule.CR:
                state = 1
            elif state == 1 and c == LTEModule.LF:
                state = 2
            elif state == 1 and c == LTEModule.CR:
                state = 1
            elif state == 1 and c != LTEModule.LF:
                response_length = 0
                state = 0
            elif state == 2 and c == LTEModule.CR:
                state = 4
            elif state == 2 and c != LTEModule.CR:
                buffer[offset+response_length] = c
                response_length += 1
                if offset+response_length == buffer_length:
                    state = 3
            elif state == 3 and c == LTEModule.CR:
                state = 4
            elif state == 4 and c == LTEModule.LF:
                return response_length


    def read_response(self, max_response_size:int=1024) -> Tuple[bytearray, int]:
        response = bytearray(max_response_size)
        length = self.read_response_into(response)
        return (response, length)
    
    def wait_response(self, expected_response:bytes, timeout:int=None, max_response_size:int=1024) -> bytes:
        response = bytearray(max_response_size)
        expected_length = len(expected_response)
        while True:
            length = self.read_response_into(response)
            if length is None: return None
            self.__l.debug("wait_response: response=%s", response[:length])
            if length >= expected_length and response[:expected_length] == expected_response:
                return response[:length]

    def execute_command(self, command:bytes, response_buffer:bytearray, index:int=0, expected_response_predicate:Callable[[memoryview],bool]=None, expected_response_list:List[bytes]=[b'OK']) -> Tuple[bool, List[memoryview]]:
        assert expected_response_predicate is not None or expected_response_list is not None
        if expected_response_predicate is None:
            expected_response_predicate = lambda mv: mv in expected_response_list 
        self.write_command(command)
        buffer_length = len(response_buffer)
        responses = []
        mv = memoryview(response_buffer)
        while True:
            length = self.read_response_into(response_buffer, index)
            if length is None:
                return (False, responses)
            response = mv[index:index+length]
            responses.append(response)
            if expected_response_predicate(response):
                return (True, responses)
            index += length

        

wiolte = WioLTE()

