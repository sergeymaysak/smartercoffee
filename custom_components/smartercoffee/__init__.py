#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2019-2021 Sergiy Maysak. All rights reserved.

"""SmarterCoffee v .1.0 Platform integration."""
from __future__ import annotations

import asyncio
import async_timeout
import time
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

# import voluptuous as vol
from homeassistant.core import callback
from homeassistant.const import (
    # CONF_HOST,
    # CONF_PORT,
    # EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
)
# import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import (
    async_load_platform
)

from homeassistant.helpers.dispatcher import (
    async_dispatcher_send,
    async_dispatcher_connect,
)
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .const import MAKERS

from . smarterdiscovery import DeviceInfo

SMARTERCOFFEE_UPDATE = f'{DOMAIN}_update'

NOTIFICATION_ID = 'smartercoffee_notification'
NOTIFICATION_TITLE = "SmarterCoffee Setup"

PLATFORMS = ["binary_sensor", "switch", "sensor", "select"]

_LOGGER = logging.getLogger(__name__)

class SmarterCoffeeException(Exception):
    """SmarterCoffee exception."""

    def __init__(self, message):
        """Initialize SmarterCoffeeException."""
        super(SmarterCoffeeException, self).__init__(message)
        self.message = message

class SmarterCoffeeDevice:
    """Principal object to control SmarterCoffee maker."""

    @classmethod
    async def async_find_devices(cls, loop):
        """Run discovery for 30 seconds."""
        from . smarterdiscovery import SmarterDiscovery
                
        coffee_finder = SmarterDiscovery(loop=loop)
        with async_timeout.timeout(30):
            devices = await coffee_finder.find()
            _LOGGER.info(f'Found SmarterCoffee devices: {devices}')

        return devices

    def __init__(self, hass, api, device_info: DeviceInfo):
        """Designated initializer for SmarterCoffee platform."""
        self.hass = hass
        self.api = api
        self.entities = []
        self.device_info = device_info

    @property
    def manufacturername(self):
        return "Smarter"

    @property
    def productname(self):
        return "Smarter Coffee v. 1.0"

    @property
    def fw_version(self):
        return self.device_info.fw_version

    async def connect(self, timeout) -> bool:
        with async_timeout.timeout(timeout):
            connected = await self.api.connect()
        return connected

    def start_monitor(self):
        def _state_changed(maker):
            _LOGGER.info("Arrived smarter coffee state update {}".format(self.api))
            async_dispatcher_send(self.hass, SMARTERCOFFEE_UPDATE)
        
        self.api.start_monitoring(_state_changed)

    async def async_stop_monitor(self):
        await self.api.stop_monitoring()

    async def turn_on(self, switch_class):
        if switch_class == 'use_beans':
            return await self.api.turn_use_beans_on()
        elif switch_class == 'hot_plate':
            return await self.api.turn_hot_plate_on()
        elif switch_class == 'brew':
            return await self.api.start_brew()
        elif switch_class == 'carafe_detection':
            return await self.api.turn_carafe_detection_on()
        elif switch_class == 'one_cup_mode':
            return await self.api.turn_one_cup_mode_on()

    async def turn_off(self, switch_class):
        if switch_class == 'use_beans':
            return await self.api.turn_use_beans_off()
        elif switch_class == 'hot_plate':
            return await self.api.turn_hot_plate_off()
        elif switch_class == 'brew':
            return await self.api.stop_brew()
        elif switch_class == 'carafe_detection':
            return await self.api.turn_carafe_detection_off()
        elif switch_class == 'one_cup_mode':
            return await self.api.turn_one_cup_mode_off()

    def is_on(self, switch_class):
        if switch_class == 'use_beans':
            return self.api.use_beans
        elif switch_class == 'hot_plate':
            return self.api.hot_plate
        elif switch_class == 'brew':
            return self.api.state in ['brewing', 'working', 'boiling', 'grinding']
        elif switch_class == 'carafe_detection':
            return self.api.carafe_detection
        elif switch_class == 'one_cup_mode':
            return self.api.one_cup_mode

    async def shutdown(self):
        _LOGGER.info("[SMARTERCOFFEE] Stopping monitor and disconnecting")
        await self.async_stop_monitor()
    
    @property
    def mac_address(self) -> str:
        return self.api.mac_address


def makeCoffeeMaker(hass, device):
    from . smartercontroller import SmarterCoffeeController
    # shared instance of smartrcoffee
    host = device.host_info
    mac = device.mac_address
    _LOGGER.info(f"Creating smarter coffee at host {host}, mac: {mac}")

    controller = SmarterCoffeeController(ip_address=host.ip_address, 
        port=host.port, mac=mac, loop=hass.loop)
    maker = SmarterCoffeeDevice(hass, controller, device)

    return maker


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmarterCoffee Machine Integration from a config entry."""
    try:
        try:
            devices = await SmarterCoffeeDevice.async_find_devices(loop=hass.loop)
        except:
            raise SmarterCoffeeException("Unable to find SmarterCoffee")
        
        if len(devices) <= 0:
            raise SmarterCoffeeException("Unable to find SmarterCoffee")

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN].setdefault(MAKERS, [])
        
        for device in devices:
            maker = makeCoffeeMaker(hass, device)
            connected = await maker.connect(30)
            if connected:
                maker.start_monitor()                
                register_device(hass, maker, entry)
                hass.data[DOMAIN][MAKERS].append(maker)
            else:
                raise SmarterCoffeeException("Unable to Connect")
        
        register_services(hass)
        hass.config_entries.async_setup_platforms(entry, PLATFORMS)

        async def _shutdown(event):
            for maker in hass.data[DOMAIN][MAKERS]:
                await maker.shutdown()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown)

    except Exception as ex:
        _LOGGER.error("Unable to connect to SmarterCoffee: %s",
                      str(ex))
        hass.components.persistent_notification.create(
            "Error: {}<br />"
            "Please restart hass after fixing this."
            "".format(ex),
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID)
        return False

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    for maker in hass.data[DOMAIN][MAKERS]:
        await maker.shutdown()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(MAKERS, None)

    return unload_ok

def register_device(hass: HomeAssistant, maker: SmarterCoffeeDevice, entry: ConfigEntry):
    """Register coffee machine device."""
    device_registry = dr.async_get(hass)

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, maker.api.mac_address)},
        identifiers={(DOMAIN, maker.api.mac_address)},
        manufacturer=maker.manufacturername,
        name="SmarterCoffee Maker",
        model=maker.productname,
        sw_version=maker.fw_version,
    )

def register_services(hass):
    """Register coffee machine custom services."""
    async def async_handle_brew_coffee(service):
        try:
            _LOGGER.info(f"Handle brew_coffee service {service.data}")
            cups_str = service.data.get('cups', 3)
            cups = int(cups_str)

            grind_str = service.data.get('use_beans', 'Beans')
            grind = 1 if grind_str == 'Beans' else 0
            
            strength_str = service.data.get('strength', "Strong")
            strength_map = {'Weak': 1, 'Medium': 2, 'Strong': 3}
            strength = 3
            if strength_str in strength_map:
                strength = strength_map[strength_str]

            hot_plate_time_str = service.data.get('hot_plate_time', 15)
            hot_plate_time = 0 if hot_plate_time_str == 'Off' else int(hot_plate_time_str)            

            coffee_maker = await async_get_maker_for_service(hass, service)
            _LOGGER.info(f"Executing brew_coffee cups: {cups} grind: {grind} strength: {strength} hot_plate_time: {hot_plate_time} maker: {coffee_maker}")

            result = await coffee_maker.api.brew(cups=cups, strength=strength,
                grind=grind, hot_plate_time=hot_plate_time)
            _LOGGER.info(f"Executed brew_coffee service with result: {result}")
        except Exception as ex:
            _LOGGER.error(f"Unable to call brew_coffee service: {ex}")

    # register service to brew service with parameters
    hass.services.async_register(DOMAIN, 'brew_coffee', async_handle_brew_coffee)

async def async_get_maker_for_service(hass, service):
    """Get coffee maker to be used for specified service."""
    device_id = None
    key = 'device_id'
    if key in service.data:
        device_id = service.data.get(key)[0]
        _LOGGER.info(f'Found target: {device_id}')

    device = None
    if device_id is not None:
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(device_id)
        _LOGGER.info(f'Found device: {device}')
    
    maker = None
    makers = hass.data[DOMAIN][MAKERS]
    if device is not None:
        mac_address = list(device.identifiers)[0][1]
        _LOGGER.info(f'Found maker mac address: {mac_address}')
        for coffee_maker in makers:
            if coffee_maker.mac_address == mac_address:
                maker = coffee_maker
                _LOGGER.info(f'Found coffee maker: {maker}')
                break
    if maker is None and len(makers) > 0:
        maker = makers[0]

    return maker

class SmarterCoffeeBaseEntity(Entity):
    """Representation of a Base Entity for SmarterCoffee."""
    def __init__(self, maker, name):
        """Constructor with name."""
        self._name = name
        self._unsub_dispatcher = None
        self._maker = maker
    
    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    async def async_added_to_hass(self):
        """Set up a listener when this entity is added to HA."""
        @callback
        def _refresh():
            self.async_schedule_update_ha_state(force_refresh=True)

        self._unsub_dispatcher = async_dispatcher_connect(self.hass,
            SMARTERCOFFEE_UPDATE, _refresh)
    
    async def async_will_remove_from_hass(self):
        _LOGGER.info("async_will_remove_from_hass")
        self._unsub_dispatcher()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def available(self):
        """Return true if switch is available."""
        return self.coffemaker.api.available

    @property
    def coffemaker(self):
        return self._maker

    @property
    def _mac_address(self):
        return self.coffemaker.mac_address
