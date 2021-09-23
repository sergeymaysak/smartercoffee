#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2019-2021 Sergiy Maysak. All rights reserved.

"""Support for SmarterCoffee binary sensors."""
import asyncio
import logging
import async_timeout

from homeassistant.components.binary_sensor import BinarySensorDevice
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.core import callback

from .const import DOMAIN as SMARTER_COFFEE_DOMAIN
from .const import MAKERS
from . import SmarterCoffeeBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup the binary sensor platform from a config entry."""

    @callback
    def build_entities(maker):
        """Register the device."""
        async_add_entities(
            [
                SmarterCoffeeBinarySensor(maker, 'Carafe', 'carafe', True, 'presence'),
                SmarterCoffeeBinarySensor(maker, 'Enough Water', 'enoughwater', True, 'occupancy')
            ]
        )

    coordinator = hass.data[SMARTER_COFFEE_DOMAIN]
    for maker in coordinator.makers:
        build_entities(maker)


class SmarterCoffeeBinarySensor(SmarterCoffeeBaseEntity, BinarySensorEntity):
    """Representation a SmarterCoffee binary sensor."""

    def __init__(self, maker, name, sensor_type, def_value, device_class):
        """Initialize the Binary sensor."""
        super().__init__(maker, name)

        self._default = def_value
        self._sensor_type = sensor_type
        self._device_class = device_class
        self.entity_id = '{}.{}_{}'.format('binary_sensor', SMARTER_COFFEE_DOMAIN,
            self._sensor_type)
    
    @property
    def device_class(self):
        return self._device_class

    @property
    def is_on(self):
        """Return true if sensor is on."""
        return getattr(self.coffemaker.api, self._sensor_type, self._default)

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}_{self._sensor_type}"
