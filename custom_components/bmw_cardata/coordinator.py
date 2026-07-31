"""MQTT data coordinator for BMW CarData."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BASIC_DATA_BY_VIN,
    CONF_MAPPINGS,
    CONF_STREAM_TOPIC,
    CONF_TELEMATIC_DATA_BY_VIN,
)
from .stream_manager import BmwCarDataStreamManager


class BmwCarDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Publish incoming BMW MQTT data to Home Assistant entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry: ConfigEntry,
        stream_manager: BmwCarDataStreamManager,
    ) -> None:
        """Initialize the MQTT-only coordinator."""
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="BMW CarData",
            update_interval=None,
        )
        self._entry = entry
        self._stream_manager = stream_manager
        self._telematic_cache_by_vin: dict[str, dict[str, dict[str, Any]]] = {}

    @property
    def use_streaming(self) -> bool:
        """Return whether MQTT configuration and authorization are complete."""
        return self._stream_manager.enabled

    async def async_initialize(self) -> None:
        """Initialize empty state and start the MQTT listener."""
        self.async_set_updated_data(self._build_payload())
        await self._stream_manager.async_start()

    async def async_apply_stream_snapshot(self) -> None:
        """Apply the latest incoming MQTT data and update entities."""
        telematic_snapshot = await self._stream_manager.async_get_telematic_snapshot()
        if not telematic_snapshot:
            return

        self._telematic_cache_by_vin = self._merge_telematic_by_vin(
            self._telematic_cache_by_vin,
            telematic_snapshot,
        )
        self.logger.debug(
            "Applying BMW MQTT snapshot with key counts per VIN: %s",
            {
                vin: len(values)
                for vin, values in self._telematic_cache_by_vin.items()
            },
        )
        self.async_set_updated_data(self._build_payload())

    def _build_payload(self) -> dict[str, Any]:
        """Build coordinator data exclusively from MQTT state and topic metadata."""
        return {
            CONF_MAPPINGS: self._build_stream_mappings(),
            CONF_BASIC_DATA_BY_VIN: {},
            CONF_TELEMATIC_DATA_BY_VIN: dict(self._telematic_cache_by_vin),
        }

    def _build_stream_mappings(self) -> list[dict[str, str]]:
        """Build vehicle mappings from the configured topic and received VINs."""
        vins = set(self._telematic_cache_by_vin)
        stream_topic = self._entry.options.get(
            CONF_STREAM_TOPIC,
            self._entry.data.get(CONF_STREAM_TOPIC, ""),
        )
        if isinstance(stream_topic, str):
            for segment in stream_topic.split("/"):
                candidate = segment.strip().upper()
                if len(candidate) == 17 and candidate.isalnum():
                    vins.add(candidate)
        return [
            {"vin": vin, "mappingType": "PRIMARY"}
            for vin in sorted(vins)
            if isinstance(vin, str) and vin
        ]

    @staticmethod
    def _merge_telematic_by_vin(
        base: dict[str, dict[str, dict[str, Any]]],
        incoming: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Merge incoming telematic entries by VIN."""
        merged = {vin: dict(values) for vin, values in base.items()}
        for vin, telematic in incoming.items():
            if not isinstance(vin, str) or not isinstance(telematic, dict):
                continue
            values = merged.setdefault(vin, {})
            for key, entry in telematic.items():
                if isinstance(key, str) and isinstance(entry, dict):
                    values[key] = entry
        return merged
