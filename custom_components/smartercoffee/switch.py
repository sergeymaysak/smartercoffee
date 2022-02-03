#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2019-2022 Sergiy Maysak. All rights reserved.

"""Support for Smarter Coffee maker switches."""

import asyncio
import logging
from datetime import datetime, timedelta
import async_timeout

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.util import convert
from homeassistant.const import STATE_OFF, STATE_ON, STATE_STANDBY, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_send,
    async_dispatcher_connect
)

from .const import DOMAIN as SMARTER_COFFEE_DOMAIN
from .const import MAKERS
from . import SmarterCoffeeBaseEntity
from . import SMARTERCOFFEE_UPDATE

# define polling interval in 10 minutes - this allows 
# to avoid ddos of coffee machine
SCAN_INTERVAL = timedelta(minutes=10)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup the switch platform from a config entry."""
    _LOGGER.info('Creating smartercoffee switches')
    @callback
    def build_entities(maker):
        """Register the device."""
        async_add_entities(
            [
                SmarterCoffeeSwitch(maker, 'Use Beans', 'use_beans', True, 'mdi:seed', 'mdi:filter'),
                SmarterCoffeeSwitch(maker, 'Brew', 'brew', False, 'mdi:coffee-to-go', 'mdi:coffee-to-go'),
                SmarterCoffeePollingSwitch(maker, 'Detect Carafe', 'carafe_detection', False, 'mdi:coffee-maker', 'mdi:coffee-maker-outline'),
                # SmarterCoffeePollingSwitch(maker, 'One Cup Mode', 'one_cup_mode', False, 'mdi:cup', 'mdi:cup-off')
            ]
        )

    coordinator = hass.data[SMARTER_COFFEE_DOMAIN]
    for maker in coordinator.makers:
        build_entities(maker)


class SmarterCoffeeSwitch(SmarterCoffeeBaseEntity, SwitchEntity):
    """Representation of a SmarterCoffee switch."""

    def __init__(self, maker, name, switch_class, default, icon_on, icon_off):
        """Initialize the SmarterCoffee switch."""
        super().__init__(maker, name)
        self._switch_class = switch_class
        self._default = default
        self.icon_on = icon_on
        self.icon_off = icon_off
        self.entity_id = '{}.{}_{}'.format('switch', SMARTER_COFFEE_DOMAIN,
            self._switch_class)

    @property
    def is_on(self):
        """Return true if switch is on. Standby is on.."""
        return self.coffemaker.is_on(self._switch_class)

    @property
    def icon(self):
        """Return the icon of device based on its type."""
        return self.icon_on if self.is_on else self.icon_off

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

    def __init__(self, maker, name, switch_class, default, icon_on, icon_off):
        """Initialize the SmarterCoffee polling-based switch."""
        super().__init__(maker, name, switch_class, default, icon_on, icon_off)

    @property
    def should_poll(self):
        """Return the polling state."""
        return True

    async def async_update(self):
        """Fetch switch state."""
        _LOGGER.info(f'Requested update for switch: {self._switch_class}')
        if self._switch_class == 'carafe_detection':
            await self.coffemaker.api.fetch_carafe_detection_status()            
        elif self._switch_class == 'one_cup_mode':
            await self.coffemaker.api.fetch_one_cup_mode_status()

    async def async_added_to_hass(self):
        """Set up a listener when this entity is added to HA."""
        @callback
        def _refresh():
            self.async_schedule_update_ha_state()  # do not use forse update here to avoid recursion

        self._unsub_dispatcher = async_dispatcher_connect(self.hass,
            SMARTERCOFFEE_UPDATE, _refresh)

        # request initial forse update
        self.async_schedule_update_ha_state(force_refresh=True)
