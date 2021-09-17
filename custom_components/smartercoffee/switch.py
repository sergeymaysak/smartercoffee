#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2019-2021 Sergiy Maysak

"""Support for Smarter Coffee maker switches."""

import asyncio
import logging
from datetime import datetime, timedelta
import async_timeout

from homeassistant.components.switch import SwitchDevice
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.util import convert
from homeassistant.const import STATE_OFF, STATE_ON, STATE_STANDBY, STATE_UNKNOWN
from homeassistant.core import callback

from .const import DOMAIN as SMARTER_COFFEE_DOMAIN
from .const import MAKERS
from . import SmarterCoffeeBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup the switch platform from a config entry."""
    _LOGGER.info('Creating smartercoffee switches')
    @callback
    def build_entities(maker):
        """Register the device."""
        async_add_entities(
            [
                SmarterCoffeeSwitch(maker, 'Use Beans', 'use_beans', True),
                SmarterCoffeeSwitch(maker, 'Brew', 'brew', False),
                SmarterCoffeeSwitch(maker, 'Hot Plate', 'hot_plate', False),
                # SmarterCoffeePollingSwitch('Detect Carafe', 'carafe_detection', False)),
                # SmarterCoffeePollingSwitch('One Cup Mode', 'one_cup_mode', False)
            ]
        )

    for maker in hass.data[SMARTER_COFFEE_DOMAIN][MAKERS]:
        build_entities(maker)

class SmarterCoffeeSwitch(SmarterCoffeeBaseEntity, SwitchEntity):
    """Representation of a SmarterCoffee switch."""

    def __init__(self, maker, name, switch_class, default):
        """Initialize the SmarterCoffee switch."""
        super().__init__(maker, name)
        self._switch_class = switch_class
        self._default = default
        self.entity_id = '{}.{}_{}'.format('switch', SMARTER_COFFEE_DOMAIN,
                                           self._switch_class)

    @property
    def is_on(self):
        """Return true if switch is on. Standby is on.."""
        return self.coffemaker.is_on(self._switch_class)

    @property
    def icon(self):
        """Return the icon of device based on its type."""
        if self._switch_class == "brew":
            return "mdi:coffee"
        return None

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        await self.coffemaker.turn_on(self._switch_class)
    
    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        await self.coffemaker.turn_off(self._switch_class)

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}_{self._switch_class}"


class SmarterCoffeePollingSwitch(SmarterCoffeeSwitch):
    """Representation of a SmarterCoffee switch which needs polling to get state."""

    def __init__(self, maker, name, switch_class, default):
        """Initialize the SmarterCoffee switch."""
        super().__init__(maker, name, switch_class, default)

    @property
    def should_poll(self):
        """Return the polling state."""
        return True
    
    async def async_update(self):
        """Fetch switch state."""
        if self._switch_class == 'carafe_detection':
            await self.coffemaker.api.fetch_carafe_detection_status()
        elif self._switch_class == 'one_cup_mode':
            await self.coffemaker.api.fetch_one_cup_mode_status()

    async def async_added_to_hass(self):
        """Set up a listener when this entity is added to HA."""
        pass
    
    async def async_will_remove_from_hass(self):
        pass
