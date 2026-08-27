"""Dockstream RFID Smart Fountain.

Shares the same water/filter/cleaning telemetry as the Dockstream 2 (reuses
its compute_alerts), but additionally reports which pet's RFID tag was
present during a drinking event via WEIGHT_CHANGE_EVENT. That event is
handled directly in devices.py (mirrors the feeder's PET_IDENTIFY_EVENT
pattern) since the RFID-to-pet matching logic is device-type-agnostic, so
track_intake here is a deliberate no-op -- recording intake from the
generic before/after currentWeight delta would double-count the same
drink already logged from the RFID-linked event.
"""

from . import dockstream2

DEVICE_TYPES = ["dockstream_rfid"]

MQTT_MODELS = {
    "dockstream_rfid": "PLWF305",
}

ALERT_MESSAGES = dockstream2.ALERT_MESSAGES
DEFAULT_NOTIFICATIONS = dockstream2.DEFAULT_NOTIFICATIONS

compute_alerts = dockstream2.compute_alerts


def track_intake(old_state: dict, new_state: dict, min_grams: float = 5) -> float | None:
    return None
