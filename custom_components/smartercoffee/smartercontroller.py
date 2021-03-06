#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2019-2022 Sergiy Maysak. All rights reserved.

import asyncio
from array import array
from threading import Thread
import functools
import concurrent.futures

USE_FILTER_ONLY = 0
USE_BEANS = 1

HOT_PLATE_ON = True

STATE_READY_TO_START = 'ready'   # ready to start
STATE_DONE = 'done'     # just completed
STATE_NO_CARAFE = 'no-carafe'
STATE_WATER_EMPTY = 'water-empty'   # not enought water
STATE_BOILING = 'boiling'
STATE_DESCALING = 'descaling'

water_level_message_types = {
    0x0: 'empty',
    0x1: 'low',
    0x2: 'half',
    0x3: 'full',
}

strength_message_types = {
    0x0: 'weak',
    0x1: 'medium',
    0x2: 'strong',
}

COMMAND_BREW = 0x33
COMMAND_BREW_STOP = 0x34
COMMAND_SET_STRENGTH = 0x35
COMMAND_SET_CUPS = 0x36
COMMAND_BREW_DEFAULT = 0x37
COMMAND_DEFAULTS = 0x48
COMMAND_TOGGLE_BEANS = 0x3c
COMMAND_TURN_HOT_PLATE_ON = 0x3e
COMMAND_TURN_HOT_PLATE_OFF = 0x4a

COMMAND_GET_CARAFE_REQUIRED = 0x4c
COMMAND_SET_CARAFE_REQUIRED = 0x4b

# set mode 'one cup' or 'carafe' - default is carafe
COMMAND_SET_MODE = 0x4e
# command to fetch current mode (cup or carafe)
COMMAND_GET_MODE = 0x4f

COMMAND_SUFFIX = 0x7e

RESPONSE_ID_STATUS = 0x32
RESPONSE_ID_COMMAND = 0x03
RESPONSE_DEFAULTS = 0x49
RESPONSE_ID_CARAFE = 0x4d
RESPONSE_ID_MODE = 0x50

REPLY_TABLE = {
    0x0: 'ok',
    0x1: 'error: Already brewing',
    0x2: 'error: No carafe',
    0x3: 'error: Not enough water',
    0x4: 'error: You sent wrong value',
    0x05: 'error: no carafe',
    0x06: 'error: no water',
    0x07: 'error: low water, could not finish',
    0x0d: 'error: timer errror',
    0x68: 'error: wifi error',
    0x69: 'error: invalid command'
}


class Logger:
    @classmethod
    def defaultLogger(cls):
        return cls()

    def __init__(self):
        pass

    def log(self, string):
        print(string)


def as_hex_string(bytes):
        hex_string = ''
        for n in bytes:
            hex_string += ' ' + hex(n)
        return hex_string

def split_response(response):
    """Find all response messages in a single buffer."""
    binary = array('B', response)
    return binary.tobytes().split(COMMAND_SUFFIX.to_bytes(1, 'big'))


class SmarterCoffeeController:
    def __init__(self, ip_address, port=2081, mac=None, loop=None, logger=Logger.defaultLogger()):
        """
        Init controller with ip address and main even loop.
        Main even loop will be notified when state of device is changed.
        """
        self._loop = loop if loop is not None else asyncio.get_event_loop()
        self.io_loop = None
        self._thread = None
        self._io_lock = None

        self._mac_address = mac
        self._ip_address = ip_address
        self._port = port
        self._logger = logger
        self._reader = None
        self._writer = None
        self._previous_data = None
        self._update_status_in_progress = False
        self.monitoring = False

        self.available = True
        self.state = 'unknown'
        self.cups = 3
        self.water_level = 'full'
        self.enoughwater = True
        self.wifi_strength = 3
        self.strength = 'strong'

        self.use_beans = True
        self.hot_plate_time = 5
        self.hot_plate = False
        self.carafe = True

        self.carafe_detection = True
        self.one_cup_mode = False

    @property
    def mac_address(self):
        return self._mac_address

    @property
    def is_io_ready(self):
        return self._reader is not None and self._writer is not None

    async def connect(self):
        if self.is_io_ready:
            self._log('Already connected - return')
            return True

        self._start_worker_thread_if_needed()
        future = asyncio.run_coroutine_threadsafe(self._connect_io(), self.io_loop)
        return future

    async def _connect_io(self):
        async with self._io_lock:
            if self.is_io_ready:
                return self.is_io_ready

            self._reader, self._writer = await asyncio.open_connection(
                host=self._ip_address, port=self._port)
            if self.is_io_ready:
                self._log('Connection esteblished to {}'.format(self._ip_address))
                await self._fetch_defaults()
            else:
                self._log('Failed to open connection')

        return self.is_io_ready

    async def _run_monitor(self, handler=None):
        needs_reconnect_timeout = False

        if not self.is_io_ready:
            succeed = await asyncio.wait_for(self._connect_io(), timeout=30.0)
            self._loop.call_soon_threadsafe(
                functools.partial(self._set_availability, succeed, handler))

        needs_reconnect_timeout = succeed is not True
        self._log('Start monitoring state')
        while self.monitoring:
            try:
                if needs_reconnect_timeout:
                    self._log('Waiting for 2 minutes before attempt to reconnect...')
                    await asyncio.sleep(120)

                if not self.is_io_ready:
                    self._log('Reconnecting...')
                    connected = await asyncio.wait_for(self._connect_io(), timeout=30.0)
                    if not connected:
                        raise EOFError()

                if self.is_io_ready and needs_reconnect_timeout:
                    needs_reconnect_timeout = False
                    self._loop.call_soon_threadsafe(
                        functools.partial(self._set_availability, True, handler))

                # Wait for 1 second
                await asyncio.sleep(1)

                # self._log(f'State monitor will read at: {self.io_loop.time()}')
                async with self._io_lock:
                    data = await asyncio.wait_for(self._reader.read(20), timeout=30.0)
                    if len(data) == 0:
                        self._log('Connection closed by server...')
                        raise EOFError()
                    message = data

                if self._previous_data != message:
                    self._log(f'Received: {as_hex_string(data)}')
                    # schedule message handling to main run loop
                    self._loop.call_soon_threadsafe(
                        functools.partial(self._handle_message, message, handler))
                    self._previous_data = message
            except Exception as e:
                self._log(f'got exception while monitoring smartercoffee {e}')
                await self._disconnect_io()
                self._loop.call_soon_threadsafe(
                    functools.partial(self._set_availability, False, handler))
                needs_reconnect_timeout = True
        self._log('Monitor stopped')

    def _handle_message(self, message, handler):
        try:
            responses = split_response(message)
            for single_message in responses:
                if len(single_message) < 1:
                    continue
                bytes_array = array('B', single_message)
                id = bytes_array[0]
                if id == RESPONSE_ID_STATUS:
                    self._parse(bytes_array)
                elif id == RESPONSE_ID_CARAFE or id == RESPONSE_ID_MODE:
                    self._parse_carafe_or_cups_status(bytes_array)
                elif id == RESPONSE_DEFAULTS:
                    self._parse_defaults(bytes_array)
                elif id == RESPONSE_ID_COMMAND:
                    result = REPLY_TABLE[bytes_array[1]]
                    self._log(f'result of command {result}')
        except Exception as exc:
            self._log(f'exception during parsing {exc}')
        if handler is not None:
            handler(self)

    def _set_availability(self, available, handler):
        """Update availability changed in io thread. Called in main thread."""
        self.available = available
        if handler is not None:
            handler(self)

    def _start_worker_thread_if_needed(self):
        if self.io_loop is not None:
            return
        
        def _io_worker(loop):
            try:
                self._log('started io worker thread')
                asyncio.set_event_loop(loop)
                self._io_lock = asyncio.Lock()
                loop.run_forever()
            except KeyboardInterrupt:
                self._log('io worker thread stopped')
                for task in asyncio.all_tasks(loop):
                    loop.run_until_complete(task)
                loop.stop()    # Received Ctrl+C
                loop.close()
            except Exception as exc:
              self._log(f'exception during io worker thread run {exc}') 
            self._log('io worker thread exit.')

        self.io_loop = asyncio.new_event_loop()
        self._thread = Thread(target=_io_worker, args=(self.io_loop,))
        self._thread.start()

    def start_monitoring(self, handler):
        if self.monitoring:
            self._log('Already monitoring - return')
            return

        self.monitoring = True
        self._start_worker_thread_if_needed()
        asyncio.run_coroutine_threadsafe(self._run_monitor(handler), self.io_loop)

    async def stop_monitoring(self):
        if not self.monitoring:
            self._log('Already stopped - return')
            return
        
        self.monitoring = False
        self._log('Set monitoring flag to False')
        disconnected = await self.disconnect()
        if disconnected:
            self._shutdown_thread()

    def _shutdown_thread(self):
        self._log('Shutting down the io thread')
        def _generate_abort():
            raise KeyboardInterrupt()
        
        self.io_loop.call_soon_threadsafe(
            functools.partial(_generate_abort))

        try:
            self._thread.join()
        finally:
            self._log('IO thread joined')
            self._thread = None
            self.io_loop = None
            self._io_lock = None

    async def disconnect(self):
        """Disconnects IO. Called from main thread."""
        if not self.is_io_ready:
            self._log('Already connected - return')
            return True

        return asyncio.run_coroutine_threadsafe(self._disconnect_io(), self.io_loop)

    async def _disconnect_io(self):
        """Private handler of disconnect io request. Called from background thread."""
        self._log('Disconnecting...')
        
        if self._writer == None:
            self._log("Already disconected - return")
            return
        
        async with self._io_lock:
            self._writer.close()
            # dont wait for close as it hangs sometimes - see https://github.com/encode/httpx/pull/640
            # await self._writer.wait_closed()            
            self._writer = None
            self._reader = None
            self._log(f'Connection to {self._ip_address} closed.')

        return self._writer == None
    
    @property
    def _is_disconnecting(self) -> bool:
        """Private helper to detect if io is disconnecting now."""
        if self._writer is None:
            return False
        
        return self._writer.is_closing()

    async def _fetch_defaults(self):
        """Internal method to fetch default setting of device."""
        cmd = self._command_id(COMMAND_DEFAULTS)
        return await self._sendCommand(cmd)

    async def brew(self, cups=3, strength=2, grind=True, hot_plate_time=5):
        """Brew coffee with parameters specified - amount of cups, strength, use grinder, keep plate warm."""
        cups_value = self._constrained(cups, min=1, max=12, default=3)
        strength_value = self._constrained(strength, min=0, max=2, default=2)
        hot_plate_time_value = self._constrained(hot_plate_time, min=0, max=40, default=5)
        use_grinder = 1 if grind is True else 0
        
        self._log(f'Sending brew {cups_value} cups, strength {strength_value}'
                   ' grind {use_grinder} hot_plate {hot_plate_time_value}')
        cmd = bytearray([COMMAND_BREW, cups_value, strength_value, 
                         hot_plate_time_value, use_grinder,
                         COMMAND_SUFFIX])        
        self.hot_plate_time = hot_plate_time_value
        return await self._sendCommand(cmd)

    async def start_brew(self):
        """Brew with defaults."""
        cmd = self._command_id(COMMAND_BREW_DEFAULT)
        return await self._sendCommand(cmd)

    async def stop_brew(self):
        """Stop current brew."""
        cmd = self._command_id(COMMAND_BREW_STOP)
        return await self._sendCommand(cmd)

    async def set_cups(self, cups):
        """Set amount of cups."""
        self._log('sending cups: {}'.format(cups))
        data = self._command_in_range(COMMAND_SET_CUPS, cups,
            min=1, max=12, default=3)
        return await self._sendCommand(data)

    async def set_strength(self, strength):
        """Set level of coffee strength (0-weak, 1-medium, 2-strong)."""
        self._log('sending set streight {}'.format(strength))
        data = self._command_in_range(COMMAND_SET_STRENGTH, strength,
            min=0, max=2, default=0)
        return await self._sendCommand(data)

    async def toggle_grind(self):
        """Set use grinder of not."""
        cmd = self._command_id(COMMAND_TOGGLE_BEANS)
        return await self._sendCommand(cmd)

    async def turn_use_beans_on(self):
        """Set use beans. Does nothing if its already set."""
        if not self.use_beans:
            return await self.toggle_grind()
        
        # return status 'ok'
        return REPLY_TABLE[0]
    
    async def turn_use_beans_off(self):
        """Set use beans. Doe nothing if its already set."""
        if self.use_beans:
            return await self.toggle_grind()
        
        # return status 'ok'
        return REPLY_TABLE[0]

    async def turn_hot_plate_on(self, hot_plate_time=5):
        self._log('sending hot_plate_time: {}'.format(hot_plate_time))
        data = self._command_in_range(COMMAND_TURN_HOT_PLATE_ON,
            hot_plate_time, min=5, max=40, default=5)
        self.hot_plate_time = self._constrained(hot_plate_time, min=5, max=40, default=5)
        return await self._sendCommand(data)

    async def turn_hot_plate_off(self):
        cmd = self._command_id(COMMAND_TURN_HOT_PLATE_OFF)
        return await self._sendCommand(cmd)

    async def fetch_carafe_detection_status(self):
        cmd = self._command_id(COMMAND_GET_CARAFE_REQUIRED)
        return await self._sendCommand(cmd)

    async def fetch_one_cup_mode_status(self):
        cmd = self._command_id(COMMAND_GET_MODE)
        return await self._sendCommand(cmd)        

    async def turn_carafe_detection_on(self):
        # force set new state
        self.carafe_detection = True
        cmd = bytearray([COMMAND_SET_CARAFE_REQUIRED, 0x0, COMMAND_SUFFIX])
        return await self._sendCommand(cmd)

    async def turn_carafe_detection_off(self):
        # force set new state
        self.carafe_detection = False
        cmd = bytearray([COMMAND_SET_CARAFE_REQUIRED, 0x1, COMMAND_SUFFIX])
        return await self._sendCommand(cmd)

    async def turn_one_cup_mode_on(self):
        cmd = bytearray([COMMAND_SET_MODE, 0x1, COMMAND_SUFFIX])
        return await self._sendCommand(cmd)
    
    async def turn_one_cup_mode_off(self):
        cmd = bytearray([COMMAND_SET_MODE, 0x0, COMMAND_SUFFIX])
        return await self._sendCommand(cmd)

    def _command_id(self, command_id):
        return bytearray([command_id, COMMAND_SUFFIX])

    def _command_in_range(self, command_id, value, min, max, default):
        constrained_value = default
        if value <= max and value >= min:
            constrained_value = value

        return bytearray([command_id, constrained_value, COMMAND_SUFFIX])

    async def _sendCommand(self, command_bytes):
        self._start_worker_thread_if_needed()
        # request sending command in own background thread
        future = asyncio.run_coroutine_threadsafe(
            self._send_cmd_io(command_bytes), self.io_loop)
        
        # future.result() never completes and we dont really need result of command sending
        # so just return True
        return True
        
        # try:
        #     result = future.result()
        # except concurrent.futures.TimeoutError:
        #     print('The coroutine took too long, cancelling the task...')
        #     future.cancel()
        #     result = 'failed'
        # except Exception as exc:
        #     print(f'The coroutine raised an exception: {exc!r}')
        # else:
        #     print(f'The coroutine returned: {result!r}')

        # return result

    async def _send_cmd_io(self, bytes):
        if self._is_disconnecting:
            self._log(f'io is disconnecting - reject command: {as_hex_string(bytes)}')
            return

        if not self.is_io_ready:
            succeed = await asyncio.wait_for(self._connect_io(), timeout=30.0)
            if succeed is False:
                return 'error: no connection to device'

        self._log(f'gonna send command: {as_hex_string(bytes)}')
        async with self._io_lock:
            self._writer.write(bytes)
            await self._writer.drain()
            self._log(f'command sent - waiting for results')
            reply = await self._reader.read(20)

        try:
            a = array('B', reply)
            self._log(f'arrived cmd response: {as_hex_string(a)}')
            self._loop.call_soon_threadsafe(
                        functools.partial(self._handle_message, a, None))
            result = REPLY_TABLE[0] # useless - to remove?
        except Exception as exc:
            self._log(f'exception during read cmd status {exc}')
            result = 'error: unknown response'

        self._log(f'result of command {result}')
        return result

    def _parse_carafe_or_cups_status(self, message):
        """Parse arrived carafe defect or one cup mode status. Executed on main thread."""
        try:
            a = array('B', message)
            if a[0] == RESPONSE_ID_CARAFE:
                self.carafe_detection = not (a[1] != 0)
                self._log(f'Carafe detection is {self.carafe_detection}')
            elif a[0] == RESPONSE_ID_MODE:       
                self.one_cup_mode = a[1] != 0
                self._log(f'One cups mode is {self.one_cup_mode}')
            else:
                self._log('Arrived message is not a carafe defect or one cup mode response - return')
        except Exception:
            return

    def _parse_defaults(self, message):
        """Parse read defaults. Executed on main thread."""
        try:
            a = array('B', message)
            if a[0] != RESPONSE_DEFAULTS:
                self._log('Arrived message is not a defaults response - return')
                return
            
            cups = a[1]
            strength = a[2]
            beans = a[3]
            hot_plate_time = a[4]
            self._log(f'arrived defaults - cups {cups}, strength {strength}, use beans {beans}, hot plate time {hot_plate_time}')
            self.hot_plate_time = hot_plate_time
        except Exception:
            return

    def _parse(self, message):
        """Parse status response. Executed on main thread."""
        try:
            a = array('B', message)
            hex_string = ''
            for n in a:
                hex_string += ' ' + hex(n)
            self._log('arrived message: {}'.format(hex_string))

            if a[0] != RESPONSE_ID_STATUS:
                self._log('Arrived message is not a status message - return')
                return

            status = a[1]
            water_level = a[2]
            wifi_strength = a[3]
            strength = a[4]
            cups = a[5]
        except Exception as ex:
            self._log(f'Exception during parse {ex}')
            return

        def is_set(x, n):
            return x & 2**n != 0

        self.use_beans = is_set(status, 1)
        ready_hot_plate = is_set(status, 5) # set when hot plate turned off after being heating
        ready = is_set(status, 2)
        heater_on = is_set(status, 4)
        grinder_on = is_set(status, 3)
        # timer_event = is_set(status, 7)
        self.carafe = is_set(status, 0)
        self.hot_plate = is_set(status, 6)

        if ready or ready_hot_plate:
            if ready:
                self._log(f'state_ready is on')
            if ready_hot_plate:
                self._log(f'ready_hot_plate is on')
            self.state = 'ready'
        if self.hot_plate:
            self._log(f'hot_plate is on - state is heating plate')
            self.state = 'heating plate'
        if heater_on:
            self.state = 'brewing'
        if grinder_on:
            self.state = 'grinding'

        self._log(f'new state is {self.state}')

        try:
            level = water_level % 16
            self.water_level = water_level_message_types[level]
            self.enoughwater = water_level/16 >= 1
        except Exception:
            self.water_level = 'empty'
            self.enoughwater = False
        
        self.wifi_Strength = wifi_strength
        self.cups = cups % 16

        try:
            self.strength = strength_message_types[strength]
        except Exception:
            self.strength = 'strong'

    def _constrained(self, value, min, max, default):
        constrained_value = default
        if value <= max and value >= min:
            constrained_value = value
        return constrained_value

    def _log(self, message):
        if self._logger is not None:
            self._logger.log(f'[SmarterCoffee] {message}')

    def __repr__(self):
        """Return string representation."""
        return ('SmarterCoffee state: {}, use: {}, water level: {}, cups: {},'
                ' strength: {}'
                ).format(self.state,
                         'beans' if self.use_beans else 'filter only',
                         self.water_level, self.cups,
                         self.strength)


# print('\n\n\n=================\n')
# print('Start brew engine')


# def on_state_update(coffeemaker):
#     print('state updated: {}'.format(coffeemaker))

# loop = asyncio.get_event_loop()
# coffee_maker = None
# try:
#     coffee_maker = SmarterCoffeeController(ip_address='192.168.1.88', loop=loop)
#     # connected = await coffee_maker.connect()
#     future = asyncio.ensure_future(coffee_maker.connect())
#     # print('connected: {}'.format(future.result()))    
    
#     coffee_maker.start_monitoring(on_state_update)
#     streight = asyncio.ensure_future(coffee_maker.set_strength(0))
#     # loop.call_later(2, coffee_maker.set_strength(0))

#     loop.run_forever()
# except KeyboardInterrupt:
#     pass
# finally:
#     print('finally')
#     coffee_maker.stop_monitoring()
#     # future = asyncio.ensure_future(coffee_maker.disconnect())
#     # loop.run_until_complete(future)
# # Close the server
# loop.close()
