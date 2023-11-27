#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2019-2023 Sergiy Maysak. All rights reserved.

"""SmarterCoffee v .1.0 Platform integration."""
from __future__ import annotations

import asyncio
import async_timeout
import time
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later

from homeassistant.core import callback
from homeassistant.const import (
    # CONF_HOST,
    # CONF_PORT,
    # EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
)

from homeassistant.helpers.dispatcher import (
    async_dispatcher_send,
    async_dispatcher_connect,
)
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .const import MAKERS
from .const import CONFIG_ENTRY

from . smarterdiscovery import DeviceInfo

SMARTERCOFFEE_UPDATE = f'{DOMAIN}_update'

NOTIFICATION_ID = 'smartercoffee_notification'
NOTIFICATION_TITLE = "SmarterCoffee Setup"

PLATFORMS = ["binary_sensor", "switch", "sensor", "select", "button"]

_LOGGER = logging.getLogger(__name__)

class SmarterCoffeeException(Exception):
    """SmarterCoffee exception."""

    def __init__(self, message):
        """Initialize SmarterCoffeeException."""
        super(SmarterCoffeeException, self).__init__(message)
        self.message = message

class SmarterDevicesCoordinator:
    """Central object to manage multiple coffee makers."""
    
    SECONDS_BETWEEN_DISCOVERY = 10
    MAX_SECONDS_BETWEEN_DISCOVERY = 300

    def __init__(self, config_entry, hass):
        self._config_entry = config_entry
        self._hass = hass
        self._macs = []
        self._makers = []
        self._scan_delay = 0
        self._stop = None

    @property
    def makers(self) -> list[SmarterCoffeeDevice]:
        return self._makers

    @classmethod
    async def async_find_devices(cls, loop) -> list[DeviceInfo]:
        """Run discovery for 10 seconds."""
        devices = []
        try:
            from . smarterdiscovery import SmarterDiscovery
            coffee_finder = SmarterDiscovery(loop=loop)

            async with async_timeout.timeout(10):
                devices = await coffee_finder.find()
        except asyncio.TimeoutError:
            _LOGGER.info('SmarterCoffee discovery has timeouted out.')
        except AssertionError as error:
            _LOGGER.info(f'SmarterCoffee discover got AssertionError: {error}')
        except Exception as ex:
            _LOGGER.info(f'SmarterCoffee discover got exception: {str(ex)}')
        
        _LOGGER.info(f'returning SmarterCoffee devices: {devices}')
        return devices

    async def async_schedule_discovery(self, *_) -> None:
        """Periodically discover new SmarterCofee devices."""
        _LOGGER.info("Start discovery for SmarterCofee devices in local network...")
        devices = []
        try:
            devices = await self.async_find_devices(self._hass.loop)
            for deviceInfo in devices:
                await self.async_add_device(self._hass, deviceInfo)
        finally:
            self._scan_delay = min(
                self._scan_delay + self.SECONDS_BETWEEN_DISCOVERY,
                self.MAX_SECONDS_BETWEEN_DISCOVERY)

            if devices is None or len(devices) <= 0:
                _LOGGER.info(f'Reschedule discover in: {self._scan_delay} seconds')
                self._stop = async_call_later(self._hass, self._scan_delay,
                    self.async_schedule_discovery)

    async def async_add_device(self, hass, deviceInfo):
        """Add newly found device."""
        if deviceInfo.mac_address in self._macs:
            return

        maker = self._makeCoffeeMaker(deviceInfo)
        self._macs.append(maker.mac_address)
        self._makers.append(maker)

        register_device(hass, maker, self._config_entry)
        await maker.connect(10)
        maker.start_monitor()

        await hass.config_entries.async_forward_entry_setups(self._config_entry, PLATFORMS)

    def _makeCoffeeMaker(self, deviceInfo) -> SmarterCoffeeDevice:
        """Factory for new SmarterCoffeeDevice instance."""
        from . smartercontroller import SmarterCoffeeController
        host = deviceInfo.host_info
        mac = deviceInfo.mac_address
        _LOGGER.info(f"Creating smarter coffee at host {host}, mac: {mac}")

        controller = SmarterCoffeeController(ip_address=host.ip_address, 
            port=host.port, mac=mac, loop=self._hass.loop)
        maker = SmarterCoffeeDevice(self._hass, controller, deviceInfo)

        return maker
    
    async def shutdown(self):
        self._stop = None
        for maker in self._makers:
            await maker.shutdown()

class SmarterCoffeeDevice:
    """Principal object to control SmarterCoffee maker."""

    def __init__(self, hass, api, device_info: DeviceInfo):
        """Designated initializer for SmarterCoffee platform."""
        self.hass = hass
        self.api = api
        self.device_info = device_info
        self.platforms_loaded = False

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
            return self.api.state in ['brewing', 'boiling', 'grinding']
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmarterCoffee Machine Integration from a config entry."""
    try:
        coordinator = SmarterDevicesCoordinator(entry, hass)
        hass.data[DOMAIN] = coordinator

        await coordinator.async_schedule_discovery()
        register_services(hass)

        async def _shutdown(event):
            coordinator = hass.data[DOMAIN]
            await coordinator.shutdown()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown)
    except Exception as ex:
        _LOGGER.error(f'Unable to connect to SmarterCoffee: {ex}')
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
    coordinator = hass.data[DOMAIN]
    await coordinator.shutdown()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN] = None

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
    
    async def async_handle_warm_plate(service):
        """Handle warm plate request."""
        try:
            _LOGGER.info(f"Handle handle_warm service {service.data}")

            hot_plate_time_str = service.data.get('hot_plate_time', 15)
            coffee_maker = await async_get_maker_for_service(hass, service)
            _LOGGER.info(f"Executing handle_warm hot_plate_time: {hot_plate_time_str} maker: {coffee_maker}")

            if hot_plate_time_str == 'Off':
                result = await coffee_maker.api.turn_hot_plate_off()
            else:
                result = await coffee_maker.api.turn_hot_plate_on(int(hot_plate_time_str))            
            _LOGGER.info(f"Executed brew_coffee service with result: {result}")
        except Exception as ex:
            _LOGGER.error(f"Unable to call warm_plate service: {ex}")

    # register services
    hass.services.async_register(DOMAIN, 'brew_coffee', async_handle_brew_coffee)
    hass.services.async_register(DOMAIN, 'warm_plate', async_handle_warm_plate)


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
    coordinator = hass.data[DOMAIN]
    makers = coordinator.makers
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
