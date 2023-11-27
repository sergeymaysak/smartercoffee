#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Author Identity: Sergiy Maysak
# Copyright: 2022-2023 Sergiy Maysak. All rights reserved.
"""Support for SmarterCoffee buttons."""
import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN as SMARTER_COFFEE_DOMAIN
from .const import MAKERS
from . import SmarterCoffeeBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup the button platform from a config entry."""
    _LOGGER.info('Creating smartercoffee buttons')
    @callback
    def build_entities(maker):
        """Register the device."""
        async_add_entities(
            [
                SmarterCoffeeButton(maker, 'Start Brew', 'turn_on', 'brew', 'mdi:coffee-to-go'),
                SmarterCoffeeButton(maker, 'Stop Brew', 'turn_off', 'brew', 'mdi:coffee-off')
            ]
        )

    coordinator = hass.data[SMARTER_COFFEE_DOMAIN]
    for maker in coordinator.makers:
        build_entities(maker)


class SmarterCoffeeButton(SmarterCoffeeBaseEntity, ButtonEntity):
    """Representation of the button for SmarterCoffeeMaker."""

    def __init__(self, maker, name, action, param, icon):
        """Constructor with platform(api)."""
        super().__init__(maker, name)
        self._attr_icon = icon
        self._action = action
        self._action_param = param
        self.entity_id = '{}.{}_{}_{}'.format('button', SMARTER_COFFEE_DOMAIN,
            action, param)

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}_button_{self._action}_{self._action_param}"

    async def async_press(self) -> None:
        """Press the button."""        
        if (action_func := getattr(self.coffemaker, self._action)) is not None:
            await action_func(self._action_param)
