"""Button platform for BMW CarData — remote commands via CoCoAPI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import BmwCarDataApiError, BmwCarDataOAuthError, BmwRemoteServicesApi
from .const import (
    CONF_MAPPINGS,
    DATA_ENTRIES,
    DOMAIN,
)
from .coordinator import BmwCarDataCoordinator
from .token_manager import BmwCarDataTokenManager


@dataclass(frozen=True, kw_only=True)
class BmwButtonDescription(ButtonEntityDescription):
    """Description of a BMW remote-command button."""

    command: str


BMW_BUTTONS: tuple[BmwButtonDescription, ...] = (
    BmwButtonDescription(
        key="climate_start",
        name="Climate Start",
        icon="mdi:air-conditioner",
        command="climate-now",
    ),
    BmwButtonDescription(
        key="climate_stop",
        name="Climate Stop",
        icon="mdi:air-conditioner-off",
        command="climate-stop",
    ),
    BmwButtonDescription(
        key="flash_lights",
        name="Flash Lights",
        icon="mdi:car-light-high",
        command="light-flash",
    ),
    BmwButtonDescription(
        key="honk_horn",
        name="Honk Horn",
        icon="mdi:bugle",
        command="horn-blow",
    ),
    BmwButtonDescription(
        key="find_vehicle",
        name="Find Vehicle",
        icon="mdi:car-search",
        command="vehicle-finder",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BMW CarData button entities from config entry."""
    entry_data = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id]
    coordinator: BmwCarDataCoordinator = entry_data["coordinator"]
    token_manager: BmwCarDataTokenManager = entry_data["token_manager"]
    remote_api: BmwRemoteServicesApi = entry_data["remote_api"]

    known_unique_ids: set[str] = set()

    def _add_vin_entities() -> None:
        mappings = coordinator.data.get(CONF_MAPPINGS, []) if coordinator.data else []
        new_entities: list[ButtonEntity] = []
        for mapping in mappings:
            vin = mapping.get("vin")
            if not isinstance(vin, str) or not vin:
                continue
            for desc in BMW_BUTTONS:
                unique_id = f"{entry.entry_id}_{vin}_{desc.key}"
                if unique_id in known_unique_ids:
                    continue
                known_unique_ids.add(unique_id)
                new_entities.append(
                    BmwCarDataButton(
                        coordinator=coordinator,
                        entry=entry,
                        vin=vin,
                        description=desc,
                        token_manager=token_manager,
                        remote_api=remote_api,
                    )
                )
        if new_entities:
            async_add_entities(new_entities)

    _add_vin_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_vin_entities))


class BmwCarDataButton(CoordinatorEntity[BmwCarDataCoordinator], ButtonEntity):
    """BMW remote command button."""

    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator: BmwCarDataCoordinator,
        entry: ConfigEntry,
        vin: str,
        description: BmwButtonDescription,
        token_manager: BmwCarDataTokenManager,
        remote_api: BmwRemoteServicesApi,
    ) -> None:
        """Initialize button entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._vin = vin
        self._token_manager = token_manager
        self._remote_api = remote_api
        self._attr_unique_id = f"{entry.entry_id}_{vin}_{description.key}"
        self._attr_name = f"{vin} {description.name}"

    async def async_press(self) -> None:
        """Send the remote command."""
        try:
            access_token = await self._token_manager.async_get_access_token()
            await self._remote_api.send_command(
                access_token, self._vin, self.entity_description.command
            )
        except (BmwCarDataApiError, BmwCarDataOAuthError) as err:
            raise HomeAssistantError(
                f"BMW remote command '{self.entity_description.command}' failed: {err}"
            ) from err

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {"vin": self._vin}
