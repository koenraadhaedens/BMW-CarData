"""Lock platform for BMW CarData — door lock/unlock via CoCoAPI."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import BmwCarDataApiError, BmwCarDataOAuthError, BmwRemoteServicesApi
from .const import (
    CONF_MAPPINGS,
    CONF_TELEMATIC_DATA_BY_VIN,
    DATA_ENTRIES,
    DOMAIN,
)
from .coordinator import BmwCarDataCoordinator
from .sensor import _find_text_telematic_value
from .token_manager import BmwCarDataTokenManager

# Telematic values that mean "locked"
_LOCKED_VALUES = {"LOCKED", "SECURED", "FULLY_LOCKED", "FULLY_SECURED", "LOCK"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BMW CarData lock entities from config entry."""
    entry_data = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id]
    coordinator: BmwCarDataCoordinator = entry_data["coordinator"]
    token_manager: BmwCarDataTokenManager = entry_data["token_manager"]
    remote_api: BmwRemoteServicesApi = entry_data["remote_api"]

    known_unique_ids: set[str] = set()

    def _add_vin_entities() -> None:
        mappings = coordinator.data.get(CONF_MAPPINGS, []) if coordinator.data else []
        new_entities: list[LockEntity] = []
        for mapping in mappings:
            vin = mapping.get("vin")
            if not isinstance(vin, str) or not vin:
                continue
            unique_id = f"{entry.entry_id}_{vin}_lock"
            if unique_id in known_unique_ids:
                continue
            known_unique_ids.add(unique_id)
            new_entities.append(
                BmwCarDataLock(
                    coordinator=coordinator,
                    entry=entry,
                    vin=vin,
                    token_manager=token_manager,
                    remote_api=remote_api,
                )
            )
        if new_entities:
            async_add_entities(new_entities)

    _add_vin_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_vin_entities))


class BmwCarDataLock(CoordinatorEntity[BmwCarDataCoordinator], LockEntity):
    """BMW vehicle door lock."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:car-door-lock"

    def __init__(
        self,
        *,
        coordinator: BmwCarDataCoordinator,
        entry: ConfigEntry,
        vin: str,
        token_manager: BmwCarDataTokenManager,
        remote_api: BmwRemoteServicesApi,
    ) -> None:
        """Initialize lock entity."""
        super().__init__(coordinator)
        self._vin = vin
        self._token_manager = token_manager
        self._remote_api = remote_api
        self._attr_unique_id = f"{entry.entry_id}_{vin}_lock"
        self._attr_name = f"{vin} Door Lock"

    def _get_telematic(self) -> dict[str, Any]:
        """Return telematic data dict for this VIN."""
        telematic_by_vin = (
            self.coordinator.data.get(CONF_TELEMATIC_DATA_BY_VIN, {})
            if self.coordinator.data
            else {}
        )
        t = telematic_by_vin.get(self._vin, {})
        return t if isinstance(t, dict) else {}

    @property
    def is_locked(self) -> bool | None:
        """Return lock state derived from telematic data."""
        status = _find_text_telematic_value(
            self._get_telematic(),
            exact_keys=(
                "vehicle.doors.overallStatus",
                "vehicle.doors.lockState",
                "vehicle.bodywork.doors.overallStatus",
                "doorLockState",
                "lockState",
            ),
            include_term_groups=(
                ("doors", "overall"),
                ("doors", "lock"),
                ("door", "lock", "state"),
                ("lockstate",),
            ),
        )
        if status is None:
            return None
        return status.upper() in _LOCKED_VALUES

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the vehicle doors."""
        try:
            access_token = await self._token_manager.async_get_access_token()
            await self._remote_api.lock_doors(access_token, self._vin)
            # Give BMW time to process and push the state update via MQTT.
            await asyncio.sleep(5)
            await self.coordinator.async_request_refresh()
        except (BmwCarDataApiError, BmwCarDataOAuthError) as err:
            raise HomeAssistantError(f"Failed to lock BMW {self._vin}: {err}") from err

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle doors."""
        try:
            access_token = await self._token_manager.async_get_access_token()
            await self._remote_api.unlock_doors(access_token, self._vin)
            await asyncio.sleep(5)
            await self.coordinator.async_request_refresh()
        except (BmwCarDataApiError, BmwCarDataOAuthError) as err:
            raise HomeAssistantError(f"Failed to unlock BMW {self._vin}: {err}") from err

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {"vin": self._vin}
