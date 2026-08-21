"""HA notification dispatch for Petlibro Local alerts.

Sends bell (HA persistent notification), email, and mobile alerts based
on global settings and per-device channel overrides.
"""

import logging

import aiohttp

from ha_config import HA_API_URL, _headers

_LOGGER = logging.getLogger(__name__)

_NOTIFY_ID = "petlibro_local"


async def fire_notification(title: str, message: str, settings: dict, device: dict):
    if settings.get("notify_bell_enabled", True) and device.get("notify_bell", True):
        await _fire_persistent(title, message)

    service = settings.get("notify_email_service", "").strip()
    if device.get("notify_email", True) and service:
        addr = device.get("notify_email_address", "") or settings.get("notify_email_to", "")
        targets = [a.strip() for a in addr.split(",") if a.strip()] if addr else []
        if targets:
            await _fire_notify_service(service, title, message, targets)

    if device.get("notify_mobile", False):
        mobile = (device.get("notify_mobile_service", "").strip()
                  or settings.get("notify_mobile_default_service", "").strip())
        if mobile:
            await _fire_notify_service(mobile.removeprefix("notify."), title, message, [])


async def _fire_persistent(title: str, message: str):
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{HA_API_URL}/services/persistent_notification/create",
                headers={**_headers(), "Content-Type": "application/json"},
                json={"title": title, "message": message, "notification_id": _NOTIFY_ID},
                timeout=aiohttp.ClientTimeout(total=10),
            )
        _LOGGER.info("Persistent notification: %s", title)
    except Exception:
        _LOGGER.exception("Failed to fire persistent notification")


async def _fire_notify_service(service: str, title: str, message: str, targets: list):
    if service.startswith("mobile_app_"):
        payload = {"title": title, "message": message}
    else:
        html_msg = "<br>".join(message.split("\n"))
        payload = {
            "title": title,
            "message": html_msg,
            "data": {"html": f"<html><body>{html_msg}</body></html>"},
        }
    if targets:
        payload["target"] = targets
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{HA_API_URL}/services/notify/{service}",
                headers={**_headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            )
        _LOGGER.info("Notify service '%s' fired: %s", service, title)
    except Exception:
        _LOGGER.exception("Failed to fire notify service '%s'", service)
