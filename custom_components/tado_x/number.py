"""Number platform for Tado X."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_OFFSET, MIN_OFFSET, OFFSET_STEP
from .coordinator import TadoXDataUpdateCoordinator, TadoXDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado X number entities."""
    coordinator: TadoXDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NumberEntity] = []

    # Add temperature offset number entities for devices that support it
    # Only VA04 (valves) and SU04 (temperature sensors) support offset
    # TR04 (thermostats) and IB02 (bridges) do not support temperature offset
    for device in coordinator.data.devices.values():
        _LOGGER.debug(
            "Checking device %s (type: %s) for temperature offset support",
            device.serial_number,
            device.device_type,
        )
        if device.device_type in ("VA04", "SU04"):
            _LOGGER.info(
                "Adding temperature offset entity for device %s (%s)",
                device.serial_number,
                device.device_type,
            )
            entities.append(TadoXTemperatureOffset(coordinator, device.serial_number))

    _LOGGER.info("Total temperature offset entities created: %s", len(entities))
    async_add_entities(entities)


class TadoXTemperatureOffset(CoordinatorEntity[TadoXDataUpdateCoordinator], NumberEntity):
    """Tado X temperature offset number entity."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_OFFSET
    _attr_native_max_value = MAX_OFFSET
    _attr_native_step = OFFSET_STEP
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "temperature_offset"

    def __init__(
        self,
        coordinator: TadoXDataUpdateCoordinator,
        device_serial: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._device_serial = device_serial
        self._attr_unique_id = f"{coordinator.home_id}_{device_serial}_temperature_offset"

    @property
    def _device(self) -> TadoXDevice | None:
        """Get the device data."""
        return self.coordinator.data.devices.get(self._device_serial)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        device = self._device
        if not device:
            return DeviceInfo(
                identifiers={(DOMAIN, self._device_serial)},
                name=f"Device {self._device_serial}",
                manufacturer="Tado",
            )

        # Map device types to friendly names
        device_type_names = {
            "VA04": "Radiator Valve",
            "SU04": "Temperature Sensor",
            "TR04": "Thermostat",
            "IB02": "Bridge",
        }
        device_type_name = device_type_names.get(device.device_type, device.device_type)

        # If device is associated with a room, use room as parent
        if device.room_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self._device_serial)},
                name=f"{device.room_name or 'Device'} {device_type_name}",
                manufacturer="Tado",
                model=f"Tado X {device.device_type}",
                sw_version=device.firmware_version,
                via_device=(DOMAIN, f"{self.coordinator.home_id}_{device.room_id}"),
            )
        else:
            # Standalone device (e.g., bridge)
            return DeviceInfo(
                identifiers={(DOMAIN, self._device_serial)},
                name=f"{device_type_name} {device.device_type}",
                manufacturer="Tado",
                model=f"Tado X {device.device_type}",
                sw_version=device.firmware_version,
                via_device=(DOMAIN, str(self.coordinator.home_id)),
            )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        device = self._device
        if not device:
            return False
        return device.connection_state == "CONNECTED"

    @property
    def native_value(self) -> float | None:
        """Return the current temperature offset."""
        device = self._device
        if not device:
            return None
        return device.temperature_offset

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:thermometer-lines"

    async def async_set_native_value(self, value: float) -> None:
        """Set the temperature offset."""
        try:
            await self.coordinator.api.set_device_temperature_offset(
                self._device_serial, value
            )
            # Refresh coordinator data to update the entity
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(
                "Failed to set temperature offset for device %s: %s",
                self._device_serial,
                err,
            )
            raise
