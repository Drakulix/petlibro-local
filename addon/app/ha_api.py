"""HA REST API helpers."""

import logging

import aiohttp

from ha_config import HA_API_URL, _headers

_LOGGER = logging.getLogger(__name__)


async def get_ha_version() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{HA_API_URL}/config",
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                return data.get("version", "")
    except Exception:
        _LOGGER.exception("Failed to fetch HA version")
        return ""


async def get_notify_services() -> list:
    """Returns sorted list of service slugs under the HA notify domain."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{HA_API_URL}/services",
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                all_services = await resp.json()
        for domain_obj in all_services:
            if domain_obj.get("domain") == "notify":
                return sorted(domain_obj.get("services", {}).keys())
        return []
    except Exception:
        _LOGGER.exception("Failed to fetch notify services")
        return []


async def get_mobile_notify_targets(notify_services: list) -> list:
    """Return [{service, label}] for mobile_app_* notify services with HA-friendly names."""
    import re as _re

    mobile = [s for s in notify_services if s.startswith("mobile_app_")]
    if not mobile:
        return []

    slug_to_label: dict[str, str] = {}

    # Strategy 1: config entries — has the device title + device_id used in the service slug
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{HA_API_URL}/config/config_entries/entry",
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    for entry in await resp.json():
                        if entry.get("domain") != "mobile_app":
                            continue
                        title = entry.get("title", "").strip()
                        if not title:
                            continue
                        entry_data = entry.get("data", {})
                        for key in ("device_id",):
                            val = entry_data.get(key, "")
                            if val:
                                slug_to_label[val] = title
                        uid = entry.get("unique_id", "")
                        if uid:
                            slug_to_label[uid] = title
                        # Also index by slugified title in case service name derived from device name
                        title_slug = _re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
                        if title_slug:
                            slug_to_label.setdefault(title_slug, title)
    except Exception:
        _LOGGER.debug("Config entries API unavailable for mobile notify targets")

    # Strategy 2: device_tracker entities — original slug-match approach
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{HA_API_URL}/states",
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    for entity in await resp.json():
                        eid = entity.get("entity_id", "")
                        if eid.startswith("device_tracker."):
                            tracker_slug = eid[len("device_tracker."):]
                            name = entity.get("attributes", {}).get("friendly_name", "")
                            if name:
                                slug_to_label.setdefault(tracker_slug, name)
    except Exception:
        _LOGGER.debug("States API unavailable for mobile notify targets")

    result = []
    for svc in mobile:
        slug = svc[len("mobile_app_"):]
        label = slug_to_label.get(slug) or slug.replace("_", " ").title()
        result.append({"service": svc, "label": label})
    return result


async def get_ha_areas() -> list[str]:
    """Return sorted list of HA area names via the template endpoint."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{HA_API_URL}/template",
                json={"template": "{{ areas() | map('area_name') | list | sort | tojson }}"},
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    _LOGGER.warning("HA areas fetch failed: HTTP %d — %s", resp.status, text[:200])
                    return []
                import json as _json
                text = await resp.text()
                return _json.loads(text)
    except Exception:
        _LOGGER.exception("Failed to fetch HA areas")
        return []
