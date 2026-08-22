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
}

DEFAULT_NOTIFICATIONS = {
    "food_low":      True,
    "desiccant_due": True,
    "bowl_due":      True,
    "housing_due":   True,
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
    return alerts


def track_intake(old_state: dict, new_state: dict, min_grams: float = 5) -> float | None:
    return None  # feeders don't track water intake
