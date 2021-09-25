# Author Identity: Sergiy Maysak
# Copyright: 2021 Sergiy Maysak. All rights reserved.

"""Config flow for SmarterCoffee Integration."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_flow

from .const import DOMAIN
from . import SmarterDevicesCoordinator

import logging

_LOGGER = logging.getLogger(__name__)

async def _async_has_devices(hass: HomeAssistant) -> bool:
    """Return if there are devices that can be discovered."""    
    devices = await SmarterDevicesCoordinator.async_find_devices(hass.loop)
    return len(devices) > 0


config_entry_flow.register_discovery_flow(DOMAIN, "SmarterCoffee Machine Integration", _async_has_devices)
