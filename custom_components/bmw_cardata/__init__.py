"""BMW CarData integration."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
import logging
import logging.handlers
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BmwCarDataApi, BmwCarDataAuthApi
from .const import (
    CONF_VERBOSE_LOGGING,
    DATA_ENTRIES,
    DEFAULT_VERBOSE_LOGGING,
    DOMAIN,
    PLATFORMS,
    SERVICE_REFRESH_DATA,
)
from .coordinator import BmwCarDataCoordinator
from .stream_manager import BmwCarDataStreamManager
from .token_manager import BmwCarDataTokenManager

_INTEGRATION_LOGGER_NAME = "custom_components.bmw_cardata"
_FILE_HANDLER_MARKER = "_bmw_cardata_verbose_handler"


def _apply_verbose_logging(config_dir: str) -> None:
    """Set integration logger to DEBUG and attach a rotating file handler."""
    logger = logging.getLogger(_INTEGRATION_LOGGER_NAME)
    _remove_verbose_logging()  # ensure no duplicate handlers
    logger.setLevel(logging.DEBUG)
    log_path = os.path.join(config_dir, "bmw_cardata.log")
    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(name)s  %(levelname)-8s  %(message)s")
    )
    setattr(handler, _FILE_HANDLER_MARKER, True)
    logger.addHandler(handler)
    logger.debug(
        "BMW CarData verbose logging enabled — writing to %s", log_path
    )


def _remove_verbose_logging() -> None:
    """Remove the BMW CarData file handler and restore propagated log level."""
    logger = logging.getLogger(_INTEGRATION_LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, _FILE_HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()
    # Reset to NOTSET so HA's own logger configuration controls the effective level.
    logger.setLevel(logging.NOTSET)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BMW CarData from a config entry."""
    # Apply or remove verbose logging based on the current option.
    verbose = bool(
        entry.options.get(
            CONF_VERBOSE_LOGGING,
            entry.data.get(CONF_VERBOSE_LOGGING, DEFAULT_VERBOSE_LOGGING),
        )
    )
    if verbose:
        _apply_verbose_logging(hass.config.config_dir)
    else:
        _remove_verbose_logging()

    domain_data = hass.data.setdefault(DOMAIN, {DATA_ENTRIES: {}})

    session = async_get_clientsession(hass)
    auth_api = BmwCarDataAuthApi(session)
    cardata_api = BmwCarDataApi(session)
    token_manager = BmwCarDataTokenManager(hass=hass, entry=entry, auth_api=auth_api)
    stream_manager = BmwCarDataStreamManager(
        hass,
        entry=entry,
        token_manager=token_manager,
        on_updates=lambda: coordinator.async_apply_stream_snapshot(),
    )
    coordinator = BmwCarDataCoordinator(
        hass,
        entry=entry,
        api=cardata_api,
        token_manager=token_manager,
        stream_manager=stream_manager,
    )
    await stream_manager.async_start()
    await coordinator.async_config_entry_first_refresh()

    domain_data[DATA_ENTRIES][entry.entry_id] = {
        "coordinator": coordinator,
        "token_manager": token_manager,
        "stream_manager": stream_manager,
    }

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_DATA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_DATA,
            partial(_async_handle_refresh_service, hass),
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _remove_verbose_logging()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    domain_data = hass.data.get(DOMAIN, {})
    entries = domain_data.get(DATA_ENTRIES, {})
    if isinstance(entries, dict):
        entry_data = entries.pop(entry.entry_id, None)
        if isinstance(entry_data, dict):
            stream_manager: BmwCarDataStreamManager | None = entry_data.get("stream_manager")
            if stream_manager is not None:
                await stream_manager.async_stop()

    if not entries:
        if hass.services.has_service(DOMAIN, SERVICE_REFRESH_DATA):
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH_DATA)
        hass.data.pop(DOMAIN)
    return True


async def _async_handle_refresh_service(hass: HomeAssistant, call) -> None:
    """Handle manual refresh service for all configured entries."""
    domain_data = hass.data.get(DOMAIN, {})
    entries: Mapping[str, dict] = domain_data.get(DATA_ENTRIES, {})
    for entry_data in entries.values():
        coordinator: BmwCarDataCoordinator | None = entry_data.get("coordinator")
        if coordinator is not None:
            await coordinator.async_request_refresh()
