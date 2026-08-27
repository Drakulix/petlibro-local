"""One RFID Smart Feeder."""

DEVICE_TYPES = ["one_rfid"]

MQTT_MODELS = {
    "one_rfid": "PLAF301",
}

ALERT_MESSAGES = {
    "food_low":      "Food hopper is empty or running low.",
    "desiccant_due": "Desiccant needs replacing.",
    "bowl_due":      "Food bowl needs cleaning.",
    "housing_due":   "Feeder housing needs cleaning.",
    "power_battery": "Running on battery power (AC lost).",
    "battery_low":   "Backup battery is low.",
}

DEFAULT_NOTIFICATIONS = {
    "food_low":      True,
    "desiccant_due": True,
    "bowl_due":      True,
    "housing_due":   True,
    "power_battery": True,
    "battery_low":   True,
}


def compute_alerts(state: dict, cfg: dict, online: bool) -> set:
    import time as _time
    notif = cfg.get("notifications", {})
    alerts = set()
    if notif.get("food_low", True):
        surplus = state.get("surplusGrain")
        if surplus is not None and not surplus and online:
            alerts.add("food_low")
    if notif.get("desiccant_due", True):
        last_ts   = cfg.get("last_desiccant_ts")
        life_days = cfg.get("desiccant_life_days", 14)
        if last_ts is not None:
            elapsed = (_time.time() - last_ts / 1000) / 86400
            if elapsed >= life_days:
                alerts.add("desiccant_due")
    if notif.get("bowl_due", True):
        last_ts   = cfg.get("last_bowl_cleaned_ts")
        interval  = cfg.get("bowl_cleaning_interval_days", 7)
        if last_ts is not None:
            elapsed = (_time.time() - last_ts / 1000) / 86400
            if elapsed >= interval:
                alerts.add("bowl_due")
    if notif.get("housing_due", True):
        last_ts   = cfg.get("last_housing_cleaned_ts")
        interval  = cfg.get("housing_cleaning_interval_days", 30)
        if last_ts is not None:
            elapsed = (_time.time() - last_ts / 1000) / 86400
            if elapsed >= interval:
                alerts.add("housing_due")
    if notif.get("power_battery", True):
        # Opportunistic: this feeder appears to drop WiFi shortly after
        # losing AC power to save the battery, so this typically only
        # catches the single transient state update sent right at the
        # transition, not a sustained live signal (and even that live push
        # isn't always sent in time -- the DEVICE_LOG_REPORT_EVENT io:35
        # handler in devices.py is the reliable fallback for accurate
        # lost/restored timing). Real outages mostly show up as the existing
        # "offline" alert instead.
        # powerType: 2 = battery, 3 = AC (confirmed via direct testing and
        # matching io:35 AC-presence sensor logs). 1 has never been observed
        # in any capture.
        if state.get("powerType") == 2:
            alerts.add("power_battery")
    if notif.get("battery_low", True):
        pct = state.get("electricQuantity")
        threshold = cfg.get("battery_low_pct", 20)
        if pct is not None and pct > 0 and pct <= threshold:
            alerts.add("battery_low")
    return alerts


def track_intake(old_state: dict, new_state: dict, min_grams: float = 5) -> float | None:
    return None  # feeders don't track water intake
