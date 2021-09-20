#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2021 Sergiy Maysak. All rights reserved.

"""Support for SmarterCoffee selectors."""
import asyncio
import logging
import async_timeout

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.core import callback

from .const import DOMAIN as SMARTER_COFFEE_DOMAIN
from .const import MAKERS
from . import SmarterCoffeeBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup the binary sensor platform from a config entry."""
    _LOGGER.info('Creating smartercoffee selects')
    @callback
    def build_entities(maker):
        """Register the device."""
        async_add_entities(
            [
                SmarterCoffeeSelect(maker, 'Cups', 'cups', '3', ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12']),
                SmarterCoffeeStrengthSelect(maker),
                SmarterCoffeeHotPlateSelect(maker)
            ]
        )

    for maker in hass.data[SMARTER_COFFEE_DOMAIN][MAKERS]:
        build_entities(maker)


class SmarterCoffeeSelect(SmarterCoffeeBaseEntity, SelectEntity):
    """Representation a SmarterCoffee options select control."""
    def __init__(self, maker, name, select_class, default, options):
        """Initialize the SmarterCoffee select."""
        super().__init__(maker, name)
        
        self._select_class = select_class
        self._default = default
        self._attr_options = list(options)
        self.entity_id = '{}.{}_{}'.format('select', SMARTER_COFFEE_DOMAIN,
            self._select_class)

    @property
    def current_option(self):
        """Return the current option."""
        value = getattr(self.coffemaker.api, self._select_class, self._default)
        return str(value).title()

    async def async_select_option(self, option: str) -> None:
        """Set an option of the coffee maker device."""
        api = self.coffemaker.api
        if self._select_class == 'cups':
            await api.set_cups(int(option))

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}_{self._select_class}"


class SmarterCoffeeStrengthSelect(SmarterCoffeeSelect):
    """Representation a SmarterCoffee strength select control."""
    def __init__(self, maker):
        """Initialize hot plate select."""
        super().__init__(maker, 'Stength', 'strength', 'Strong', ['Weak', 'Medium', 'Strong'])

    async def async_select_option(self, option: str) -> None:
        """Set an option of strength."""
        if option in self.options:
            value = self.options.index(option)
            await self.coffemaker.api.set_strength(value)


class SmarterCoffeeHotPlateSelect(SmarterCoffeeSelect):
    """Representation a SmarterCoffee options Hot Plate select control."""
    def __init__(self, maker):
        """Initialize hot plate select."""
        super().__init__(maker, 'Hot Plate', 'hot_plate', 'Off', ['Off', '5', '10', '15', '20', '25', '30', '35', '40'])

    @property
    def current_option(self):
        """Return the current selected state of hot plate."""
        is_on = self.coffemaker.api.hot_plate
        value = 'Off' if is_on is False else str(self.coffemaker.api.hot_plate_time)
        return value.title()

    async def async_select_option(self, option: str) -> None:
        """Set an option of hot plate."""
        api = self.coffemaker.api
        if option == 'Off':
            await api.turn_hot_plate_off()
        else:
            await api.turn_hot_plate_on(int(option))

