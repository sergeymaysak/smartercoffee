#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2019-2021 Sergiy Maysak. All rights reserved.

import logging
import asyncio
import async_timeout
    
from .const import DOMAIN as SMARTER_COFFEE_DOMAIN
from .const import MAKERS

from . import SmarterCoffeeBaseEntity
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup the sensor platform from a config entry."""

    @callback
    def build_entities(maker):
        """Register the device."""
        async_add_entities(
            [
                SmarterCoffeeSensor(maker, 'state', 'unknown', 'State', 'mdi:coffee'),
                SmarterCoffeeSensor(maker, 'water_level', 'empty', 'Water Level', 'mdi:water'),
            ]
        )

    coordinator = hass.data[SMARTER_COFFEE_DOMAIN]
    for maker in coordinator.makers:
        build_entities(maker)


class SmarterCoffeeSensor(SmarterCoffeeBaseEntity):
    """Representation of a Sensor."""
    def __init__(self, maker, sensor_type, def_value, name, icon):
        """Constructor with platform(api)."""
        super().__init__(maker, name)      
        self._sensor_type = sensor_type
        self._default = def_value
        self._attr_icon = icon
        self.entity_id = '{}.{}_{}'.format('sensor', SMARTER_COFFEE_DOMAIN,
            self._sensor_type)
    
    @property
    def state(self):
        """Return the state of the sensor."""
        return getattr(self.coffemaker.api, self._sensor_type, self._default)

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}_{self._sensor_type}"
