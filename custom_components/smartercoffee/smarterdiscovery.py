#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2019-2021 Sergiy Maysak. All rights reserved.

import asyncio
from array import array
import socket
import struct
import collections
import re

BROADCAST_ADDR = '255.255.255.255'
PORT = 2081
DEVICE_TYPE_KETTLE = 0x1
DEVICE_TYPE_COFFEEMAKER = 0x2

HostInfo = collections.namedtuple('HostInfo', 'ip_address, port')
DeviceInfo = collections.namedtuple('DeviceInfo', 'device_type, fw_version, host_info, mac_address')

class SmarterDiscoveryProtocol:
    def __init__(self, loop, broadcast_addr, on_device_found):
        self.on_device_found = on_device_found
        self.transport = None
        self.broadcast_addr = broadcast_addr
        self.devices_found = []
        self._loop = loop
        self.next_broadcast_handle = None

    def connection_made(self, transport):
        self.transport = transport
        # print(f'UDP connection made.')

        # print(f'Sending: {command}')
        sock = transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        #sock.settimeout(3)
        addrinfo = socket.getaddrinfo(self.broadcast_addr, None)[0]
        if addrinfo[0] == socket.AF_INET: # IPv4
            ttl = struct.pack('@i', 1)
            sock.setsockopt(socket.IPPROTO_IP, 
                socket.IP_MULTICAST_TTL, ttl)

        self._broadcast()
        
    def _broadcast(self):
        # print('Broadcast...')
        command = bytearray([0x64, 0x7e])
        self.transport.sendto(command, (self.broadcast_addr, PORT))

        #repeat every 10 seconds
        self.next_broadcast_handle = self._loop.call_later(10, self._broadcast)

    def datagram_received(self, data, addr):
        
        def as_hex(data):
            hex_string = ''
            for n in data:
                hex_string += ' ' + hex(n)
            return hex_string

        print(f"Received: {as_hex(data)} from: {addr}")

        info = self._parse_data(data)
        if info is not None:
            asyncio.ensure_future(self._add_device(addr, info), loop=self._loop)
        else:
            print("Continue looking for device...")

    async def _fetch_mac_address(self, ip_adress):
        """Retrieve hardware mac address of smarter coffee device."""

        proc = await asyncio.create_subprocess_shell(
            f'ping -c 1 {ip_adress}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)

        (_, _) = await proc.communicate()
        rc = proc.returncode
        if rc != 0:
            return None

        proc = await asyncio.create_subprocess_shell(
            f'arp -n {ip_adress}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)

        (stdout, _) = await proc.communicate()
        string = stdout.decode('utf-8')
        result = re.search(r"(([a-f\d]{1,2}\:){5}[a-f\d]{1,2})", string)

        return result.group(0) if result else None

    async def _add_device(self, addr, discovery_info):
        host_info = HostInfo(ip_address=addr[0], port=addr[1])
        try:
            mac = await self._fetch_mac_address(host_info.ip_address)
        except Exception as e:
            mac = ""
        deviceInfo = DeviceInfo(device_type=discovery_info[0], fw_version=discovery_info[1], 
            host_info=host_info, mac_address = mac)

        self.devices_found.append(deviceInfo)
        # if at least one device found - let discovery work for more 1 sec
        # and report results via Future object
        self._loop.call_later(1, self._report_results)

    def error_received(self, exc):
        print('Error received:', exc)
        if self.next_broadcast_handle is not None:
            self.next_broadcast_handle.cancel()
            self.next_broadcast_handle = None
        self.on_device_found.set_exception(exc)

    def connection_lost(self, exc):
        # print("UDP connection closed")
        if self.next_broadcast_handle is not None:
            self.next_broadcast_handle.cancel()
            self.next_broadcast_handle = None
    
    def _parse_data(self, data):
        try:
            message = array('B', data)
            # '0x65 type version 0x7e'
            if message[0] != 0x65:
                raise BaseException
            
            type = message[1]
            fw_version = message[2]
            return (type, fw_version)
        except Exception as e:
            print(f'failed to parse arrived data with {e}')
        
        return None
    
    def _report_results(self):
        if self.next_broadcast_handle is not None:
            self.next_broadcast_handle.cancel()
            self.next_broadcast_handle = None
        self.on_device_found.set_result(self.devices_found)

class SmarterDiscovery:
    def __init__(self, loop=None):
        self._loop = loop if loop is not None else asyncio.get_event_loop()

    async def find(self):
        """Discover Smarter Coffee / iKettle devices in local network."""
        
        on_found = self._loop.create_future()
        
        addrinfo = socket.getaddrinfo(BROADCAST_ADDR, None)[0]
        sock = socket.socket(addrinfo[0], socket.SOCK_DGRAM)
        (transport, _) = await self._loop.create_datagram_endpoint(
            lambda: SmarterDiscoveryProtocol(self._loop, BROADCAST_ADDR, on_found),
            sock=sock)

        devices = None
        try:
            devices = await on_found
        finally:
            transport.close()
        return devices

# async def main():
#     loop = asyncio.get_running_loop()
    
#     try:
#         where_is_my_coffee = SmarterDiscovery(loop=loop)
#         # devices = await asyncio.wait_for(coffee_finder.find(), timeout=30.0)
#         devices = await where_is_my_coffee.find()
#         print(f'Found SmarterCoffee at: {devices}')

#         # mac = await fetch_mac_address('192.168.1.88')
#         # print(f'mac address: {mac}')
#     except Exception as e:
#         print(f'failed to find coffee {e}')

# asyncio.run(main())
