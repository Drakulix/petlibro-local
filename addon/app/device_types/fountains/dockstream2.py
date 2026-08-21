"""Dockstream 2 Smart Fountain and Dockstream 2 Smart Cordless Fountain."""

import time as _time

DEVICE_TYPES = ["dockstream2", "dockstream2_cordless"]

MQTT_MODELS = {
    "dockstream2":          "PLWF106",
    "dockstream2_cordless": "PLWF116",
}

ALERT_MESSAGES = {
    "water_low":    "Water level is low.",
    "filter_due":   "Filter replacement is due soon.",
    "cleaning_due": "Cleaning is overdue.",
}

DEFAULT_NOTIFICATIONS = {
    "water_low":    True,
    "filter_due":   True,
    "cleaning_due": True,
}


def compute_alerts(state: dict, cfg: dict, online: bool) -> set:
    notif = cfg.get("notifications", {})
    alerts = set()

    if notif.get("water_low", True):
        threshold = state.get("lowWater") or cfg.get("low_water_grams", 500)
        cw = state.get("currentWeight")
        if cw is not None and cw < threshold and online:
            alerts.add("water_low")

    if notif.get("filter_due", True):
        fts = state.get("filterNextReplacementTimestamp")
        if fts is not None:
            days = (fts - _time.time() * 1000) / 86400000
            if days <= 3:
                alerts.add("filter_due")

    if notif.get("cleaning_due", True):
        last_ts = cfg.get("last_cleaned_ts")
        interval = cfg.get("cleaning_interval_days", 30)
        if last_ts is not None:
            days = (last_ts + interval * 86400000 - _time.time() * 1000) / 86400000
            if days <= 0:
                alerts.add("cleaning_due")

    return alerts


def track_intake(old_state: dict, new_state: dict) -> float | None:
    """Return grams consumed if a plausible drinking event occurred, else None."""
    old_weight = old_state.get("currentWeight")
    new_weight = new_state.get("currentWeight")
    if old_weight is None or new_weight is None:
        return None
    drop = old_weight - new_weight
    if 10 <= drop <= 800:
        return drop
    return None
