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

class LTEModuleError(RuntimeError):
    def __init__(self, message:str):
        super().__init__(message)

class LTEModule(object):
    "Controls Quectel EC21 LTE Module"
    CR = const(0x0d)
    LF = const(0x0a)

    SOCKET_TCP = const(0)
    SOCKET_UDP = const(1)

    MAX_CONNECT_ID = const(12)
    MAX_SOCKET_DATA_SIZE = const(1460)

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
    
    def get_IMEI(self) -> str:
        "Gets International Mobile Equipment Identity (IMEI)"
        response = self.execute_command_single_response(b'AT+GSN')
        return str(response, 'utf-8') if response is not None else None
    
    def get_IMSI(self) -> str:
        "Gets International Mobile Subscriber Identity (IMSI)"
        response = self.execute_command_single_response(b'AT+CIMI')
        return str(response, 'utf-8') if response is not None else None

    def get_phone_number(self) -> str:
        "Gets phone number (subscriber number)"
        response = self.execute_command_single_response(b'AT+CNUM', b'+CNUM:')
        return str(response[6:], 'utf-8') if response is not None else None

    def get_RSSI(self) -> int:
        "Gets received signal strength indication (RSSI)"
        response = self.execute_command_single_response(b'AT+CSQ', b'+CSQ:')
        if response is None:
            return response
        try:
            s = str(response[5:], 'utf-8')
            rssi, ber = s.split(',', 2)
            return (int(rssi), int(ber))
        except ValueError:
            return None
    
    def activate(self, access_point:str, user:str, password:str) -> bool:
        self.__l.info("Activating network...")
        while True:
            # Read network registration status.
            response = self.execute_command_single_response(b'AT+CGREG?', b'+CGREG:')
            if response is None:
                raise LTEModuleError('Failed to get registration status.')
            s = str(response, 'utf-8')
            self.__l.debug('AT+CGREG?:%s', s)
            n, stat = s.split(',')[:2]
            if stat == '0' or stat == '4':  # Not registered and not searching (0), or unknown (4).
                raise LTEModuleError('Invalid registration status.')
            elif stat == '1' or stat == '5': # Registered.
                break
            
            # Read EPS network registration status
            response = self.execute_command_single_response(b'AT+CEREG?', b'+CEREG:')
            if response is None:
                raise LTEModuleError('Failed to get registration status.')
            s = str(response, 'utf-8')
            self.__l.debug('AT+CEREG?:%s', s)
            n, stat = s.split(',')[:2]
            if stat == '0' or stat == '4':  # Not registered and not searching (0), or unknown (4).
                raise LTEModuleError('Invalid registration status.')
            elif stat == '1' or stat == '5': # Registered.
                break
        # Configure TCP/IP contect parameters
        # contextID,context_type,APN,username,password,authentication
        # context_type  : IPv4 = 1, IPv4/v6 = 2
        # authentication: None = 0, PAP = 1, CHAP = 2, PAP or CHAP = 3
        command = bytes('AT+QICSGP=1,1,"{0}","{1}","{2}",1'.format(access_point, user, password), 'utf-8')
        if not self.write_command_wait(command, b'OK'):
            return False
        # Activate a PDP context
        if not self.write_command_wait(b'AT+QIACT=1', b'OK'):
            return False
        if not self.write_command_wait(b'AT+QIACT?', b'OK'):
            return False
        
        return True
    
    def socket_open(self, host:str, port:int, socket_type:int) -> int:
        assert(host is not None)
        assert(port is not None and 0 <= port and port <= 65535)
        if socket_type == LTEModule.SOCKET_TCP:
            socket_type_name = 'TCP'
        elif socket_type == LTEModule.SOCKET_UDP:
            socket_type_name = 'UDP'
        else:
            socket_type_name = None
        assert(socket_type_name is not None)

        

        buffer = bytearray(1024)

        # Read current connections and find unused connection.
        success, responses = self.execute_command(b'AT+QISTATE?', buffer)
        if not success:
            raise LTEModuleError('Failed to get socket status')
        connect_id_in_use = set()
        for response in responses:
            if len(response) < 10 or response[:10] != b'+QISTATE: ': continue
            s = str(bytes(response[10:]), 'utf-8')
            self.__l.debug(s)
            params = s.split(',',1)
            connect_id = int(params[0])
            connect_id_in_use.add(connect_id)

        new_connect_id = None
        for connect_id in range(LTEModule.MAX_CONNECT_ID):
            if connect_id not in connect_id_in_use:
                new_connect_id = connect_id
                break
        if new_connect_id is None:
            raise LTEModuleError('No connection resources available.')

        # Open socket.
        command = bytes('AT+QIOPEN=1,{0},"{1}","{2}",{3},0,0'.format(connect_id, socket_type_name, host, port), 'utf-8')
        if not self.write_command_wait(command, b'OK'):
            raise LTEModuleError('Failed to open socket.')
        if self.wait_response(bytes('+QIOPEN: {0},0'.format(connect_id), 'utf-8')) is None:
            raise LTEModuleError('Failed to open socket.')

        return connect_id
    
    def socket_send(self, connect_id:int, data:bytes, offset:int=0, length:int=None) -> bool:
        assert(0 <= connect_id and connect_id <= LTEModule.MAX_CONNECT_ID)

        length = len(data) if length is None else length
        if length == 0:
            return True
        assert(length <= LTEModule.MAX_SOCKET_DATA_SIZE)

        command = bytes('AT+QISEND={0},{1}'.format(connect_id, length), 'utf-8')
        self.write_command(command)
        if not self.wait_prompt(b'> '):
            return False
        mv = memoryview(data)
        self.__uart.write(mv[offset:offset+length])
        return self.wait_response(b'SEND OK') is not None
    
    def socket_receive(self, connect_id:int, buffer:bytearray, offset:int=0, length:int=None) -> int:
        assert(0 <= connect_id and connect_id <= LTEModule.MAX_CONNECT_ID)

        length = len(buffer) if length is None else length
        if length == 0:
            return True
        assert(length <= LTEModule.MAX_SOCKET_DATA_SIZE)

        command = bytes('AT+QIRD={0},{1}'.format(connect_id,length), 'utf-8')
        self.write_command(command)
        response = self.wait_response(b'+QIRD: ')
        if response is None:
            return None
        actual_length = int(str(response[7:], 'utf-8'))
        self.__l.debug('receive length=%d', actual_length)
        if actual_length == 0:
            return 0 if self.wait_response(b'OK') is not None else None
        mv = memoryview(buffer)
        bytes_read = self.__uart.readinto(mv[offset:offset+length], actual_length)
        self.__l.debug('bytes read=%d', bytes_read)
        self.__l.debug('bytes=%s', buffer[offset:offset+length])
        return actual_length if bytes_read == actual_length and self.wait_response(b'OK') is not None else None
    
    
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
            self.__l.debug('S:%d R:%c', state, c)
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
                if response_length == 0:
                    state = 1
                else:
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
        self.__l.debug('wait_response: target=%s', expected_response)
        response = bytearray(max_response_size)
        expected_length = len(expected_response)
        while True:
            length = self.read_response_into(response)
            if length is None: return None
            self.__l.debug("wait_response: response=%s", response[:length])
            if length >= expected_length and response[:expected_length] == expected_response:
                return response[:length]
    
    def wait_prompt(self, expected_prompt:bytes) -> bool:
        prompt_length = len(expected_prompt)
        index = 0
        while True:
            c = self.__uart.readchar()
            if c < 0: return False  # Timed out
            if expected_prompt[index] == c:
                index += 1
                if index == prompt_length:
                    return True
            else:
                index = 0

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

    def execute_command_single_response(self, command:bytes, starts_with:bytes=None) -> bytes:
        buffer = bytearray(1024)
        result, responses = self.execute_command(command, buffer)
        if not result: return None
        starts_with_length = len(starts_with) if starts_with is not None else 0

        for response in responses:
            if starts_with_length == 0 and len(response) > 0:
                response = bytes(response)
                self.__l.debug('-> %s', response)
                return response
            if starts_with_length > 0 and len(response) >= starts_with_length and response[:starts_with_length] == starts_with:
                response = bytes(response)
                self.__l.debug('-> %s', response)
                return response
        return None
        

wiolte = WioLTE()

