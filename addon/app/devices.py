"""MQTT client for Petlibro devices.

Maintains a persistent connection to HA Mosquitto, subscribes to all configured
device topics, and keeps an in-memory state dict updated with the latest telemetry.
Device-type-specific logic (alerts, intake tracking) lives in device_types/.
"""

import asyncio
import json
import logging
import os

import aiomqtt
import device_types as _device_types
import ha_mqtt

_LOGGER = logging.getLogger(__name__)

# In-memory device states keyed by serial number
_state:        dict[str, dict]  = {}
_online:       dict[str, bool]  = {}
_alert_sent:   dict[str, set]   = {}
_offline_since: dict[str, float] = {}   # epoch when each device first went offline

OFFLINE_ALERT_DELAY_SECS = 90

_host = "localhost"
_port = 1883
_user = ""
_pass = ""

# Built from the device_types registry at import time
_DEVICE_MODELS:   dict[str, str] = _device_types.all_mqtt_models()
_ALERT_MESSAGES:  dict[str, str] = _device_types.all_alert_messages()

# Serials currently subscribed: serial -> (model, device_type)
_devices: dict[str, tuple[str, str]] = {}

_client_task:     asyncio.Task | None  = None
_client_ref:      aiomqtt.Client | None = None
_reconnect_event: asyncio.Event | None = None
_suppress_alerts: bool = False


def suppress_alerts(suppress: bool):
    global _suppress_alerts
    _suppress_alerts = suppress


# ── Configuration ──────────────────────────────────────────────────────────

def configure(host: str, port: int, user: str, password: str):
    global _host, _port, _user, _pass
    _host = host
    _port = port
    _user = user
    _pass = password


# ── Device registration ────────────────────────────────────────────────────

def register_device(serial: str, model: str, device_type: str):
    _devices[serial] = (model, device_type)
    try:
        import storage as _storage
        cached = _storage.get_device_mqtt_cache(serial)
        if cached:
            _state.setdefault(serial, {}).update(cached)
    except Exception:
        pass
    _LOGGER.info("Registered device %s... (%s)", serial[:6], device_type)
    if _reconnect_event:
        _reconnect_event.set()


def _mark_online(serial: str):
    """Mark device online and clear any pending offline timer."""
    was_online = _online.get(serial, False)
    _online[serial] = True
    if not was_online:
        _offline_since.pop(serial, None)
        if _client_ref is not None:
            asyncio.ensure_future(ha_mqtt.publish_availability(_client_ref, serial, True))


def _mark_offline(serial: str):
    """Mark device offline, recording the time it first went offline."""
    import time as _t
    was_online = _online.get(serial, True)
    if was_online:
        _offline_since.setdefault(serial, _t.time())
    _online[serial] = False
    if was_online and _client_ref is not None:
        asyncio.ensure_future(ha_mqtt.publish_availability(_client_ref, serial, False))


def unregister_device(serial: str):
    _devices.pop(serial, None)
    _state.pop(serial, None)
    _online.pop(serial, None)
    _offline_since.pop(serial, None)
    _alert_sent.pop(serial, None)
    if _reconnect_event:
        _reconnect_event.set()


def get_device_state(serial: str) -> dict:
    return _state.get(serial, {})


def get_all_states() -> dict:
    return {
        serial: {**_state.get(serial, {}), "online": _online.get(serial, False)}
        for serial in _devices
    }


def is_online(serial: str) -> bool:
    return _online.get(serial, False)


# ── MQTT topic helpers ─────────────────────────────────────────────────────

def _mqtt_model(device_type: str) -> str:
    return _DEVICE_MODELS.get(device_type, device_type)


def _topic_for(device_type: str, serial: str) -> str:
    return f"dl/{_mqtt_model(device_type)}/{serial}/device/+/post"


def _service_sub_topic(device_type: str, serial: str) -> str:
    return f"dl/{_mqtt_model(device_type)}/{serial}/device/service/sub"


def _event_sub_topic(device_type: str, serial: str) -> str:
    return f"dl/{_mqtt_model(device_type)}/{serial}/device/event/sub"


# ── Commands ───────────────────────────────────────────────────────────────

async def send_command(serial: str, payload: dict) -> bool:
    global _client_ref
    import time
    if serial not in _devices:
        _LOGGER.warning("send_command: unknown serial %s...", serial[:6])
        return False
    _, device_type = _devices[serial]
    topic = _service_sub_topic(device_type, serial)
    if _client_ref is None:
        _LOGGER.warning("send_command: no MQTT client")
        return False
    envelope = {
        "cmd":   "ATTR_SET_SERVICE",
        "ts":    int(time.time() * 1000),
        "msgId": f"{serial}_{int(time.time())}",
        **payload,
    }
    try:
        await _client_ref.publish(topic, json.dumps(envelope))
        _LOGGER.debug("Command sent to %s...", serial[:6])
        return True
    except Exception:
        _LOGGER.exception("Failed to send command to %s...", serial[:6])
        return False


async def send_display(serial: str, display_text: str, display_icon: int) -> bool:
    """Push display content to the feeder via MQTT.

    For text: generates a scrolling bitmap and sends DISPLAY_MATRIX_SERVICE.
    For icons: sends ATTR_SET_SERVICE with screenDisplayId (feeder handles built-in bitmaps).
    """
    global _client_ref
    import time
    import display_matrix as dm

    if serial not in _devices:
        _LOGGER.warning("send_display: unknown serial %s...", serial[:6])
        return False
    _, device_type = _devices[serial]
    topic = _service_sub_topic(device_type, serial)
    if _client_ref is None:
        _LOGGER.warning("send_display: no MQTT client")
        return False

    ts = int(time.time() * 1000)
    msg_id = f"{serial}_{ts}"

    _CHUNK = 20  # frames per sub-message, matching cloud protocol
    try:
        if display_text:
            frames = dm.text_to_frames(display_text)
            n = len(frames)
            is_static = n == 1
            chunks = [frames[i:i + _CHUNK] for i in range(0, n, _CHUNK)]
            sub_num = len(chunks)
            for sub_idx, chunk in enumerate(chunks):
                envelope: dict = {
                    "cmd": "DISPLAY_MATRIX_SERVICE",
                    "ts": ts,
                    "msgId": msg_id,
                    "screenDisplayMatrix": chunk,
                    "screenDisplayNumber": n,
                    "screenDisplayId": 0,
                    "screenDisplayInterval": 2,
                    "displayScene": "USER_CUSTOM",
                    "subNum": sub_num,
                    "subIndex": sub_idx,
                }
                if not is_static:
                    envelope["loopDisplay"] = True
                await _client_ref.publish(topic, json.dumps(envelope))
                if sub_idx < sub_num - 1:
                    await asyncio.sleep(0.15)
            _LOGGER.info(
                "DISPLAY_MATRIX_SERVICE sent to %s... (%d frame%s, %d chunk%s)",
                serial[:6], n, "" if n == 1 else "s", sub_num, "" if sub_num == 1 else "s",
            )
        elif display_icon:
            frame = dm.ICON_FRAMES.get(display_icon)
            if frame:
                envelope = {
                    "cmd": "DISPLAY_MATRIX_SERVICE",
                    "ts": ts,
                    "msgId": msg_id,
                    "screenDisplayMatrix": [frame],
                    "screenDisplayNumber": 1,
                    "screenDisplayId": display_icon,
                    "screenDisplayInterval": 2,
                    "displayScene": "USER_CUSTOM",
                    "loopDisplay": True,
                    "subNum": 1,
                    "subIndex": 0,
                }
                await _client_ref.publish(topic, json.dumps(envelope))
                _LOGGER.info("Display icon %d sent to %s...", display_icon, serial[:6])
            else:
                _LOGGER.warning("Unknown icon id %d, not sending", display_icon)
        return True
    except Exception:
        _LOGGER.exception("Failed to send display to %s...", serial[:6])
        return False


async def send_display_frame(serial: str, frame: list) -> bool:
    """Push a raw DISPLAY_MATRIX_SERVICE frame to the feeder (custom icon)."""
    global _client_ref
    import time
    if serial not in _devices:
        return False
    _, device_type = _devices[serial]
    topic = _service_sub_topic(device_type, serial)
    if _client_ref is None:
        return False
    try:
        ts = int(time.time() * 1000)
        envelope = {
            "cmd": "DISPLAY_MATRIX_SERVICE",
            "ts": ts,
            "msgId": f"{serial}_{ts}",
            "screenDisplayMatrix": [frame],
            "screenDisplayNumber": 1,
            "screenDisplayId": 0,
            "screenDisplayInterval": 2,
            "displayScene": "USER_CUSTOM",
            "loopDisplay": False,
            "subNum": 1,
            "subIndex": 0,
        }
        await _client_ref.publish(topic, json.dumps(envelope))
        _LOGGER.info("Custom display frame sent to %s...", serial[:6])
        return True
    except Exception:
        _LOGGER.exception("Failed to send display frame to %s...", serial[:6])
        return False


async def send_feeding_plans(serial: str, plans: list) -> bool:
    """Push FEEDING_PLAN_SERVICE to feeder with the given plans (enabled only, _enabled stripped)."""
    global _client_ref
    import time
    if serial not in _devices:
        _LOGGER.warning("send_feeding_plans: unknown serial %s...", serial[:6])
        return False
    _, device_type = _devices[serial]
    topic = _service_sub_topic(device_type, serial)
    if _client_ref is None:
        _LOGGER.warning("send_feeding_plans: no MQTT client")
        return False
    clean = [{k: v for k, v in p.items() if k != "_enabled"} for p in plans if p.get("_enabled", True)]
    payload = json.dumps({
        "cmd":    "FEEDING_PLAN_SERVICE",
        "ts":     int(time.time() * 1000),
        "msgId":  f"{serial}_{int(time.time())}",
        "plans":  clean,
    })
    try:
        await _client_ref.publish(topic, payload)
        _LOGGER.debug("FEEDING_PLAN_SERVICE sent to %s... (%d plans)", serial[:6], len(clean))
        return True
    except Exception:
        _LOGGER.exception("Failed to send feeding plans to %s...", serial[:6])
        return False


# ── Alert logic ────────────────────────────────────────────────────────────

_PROTO_FIELDS     = frozenset({"cmd", "msgId", "code", "ts"})
_SENSITIVE_FIELDS = frozenset({"wifiSsid", "wifiPassword", "audioUrl"})


def _compute_device_alerts(serial: str) -> set:
    import storage as _storage
    cfg         = _storage.get_devices().get(serial, {})
    state       = _state.get(serial, {})
    device_type = cfg.get("device_type", "")
    notif       = cfg.get("notifications", {})
    alerts: set = set()

    mod = _device_types.get(device_type)
    if mod:
        alerts.update(mod.compute_alerts(state, cfg, _online.get(serial, False)))

    if notif.get("offline", True) and not _online.get(serial, False):
        import time as _t
        offline_secs = _t.time() - _offline_since.get(serial, _t.time())
        if offline_secs >= OFFLINE_ALERT_DELAY_SECS:
            alerts.add("offline")

    return alerts


async def _check_and_fire_alerts(serial: str):
    if _suppress_alerts:
        return
    import storage as _storage
    import notifications as _notifications
    try:
        current    = _compute_device_alerts(serial)
        prev       = _alert_sent.get(serial, set())
        new_alerts = current - prev
        _alert_sent[serial] = current
        if not new_alerts:
            return
        settings   = _storage.get_settings()
        device_cfg = _storage.get_devices().get(serial, {})
        for alert in new_alerts:
            name  = device_cfg.get("name") or serial[:6]
            title = f"Petlibro Local: {name}"
            msg   = _ALERT_MESSAGES.get(alert, alert)
            await _notifications.fire_notification(title, msg, settings, device_cfg)
            _LOGGER.info("Alert fired: %s for %s...", alert, serial[:6])
    except Exception:
        _LOGGER.exception("Alert check failed for %s...", serial[:6])


async def _persist_state_cache(serial: str):
    try:
        import storage as _storage
        _storage.save_device_mqtt_cache(serial, dict(_state.get(serial, {})))
    except Exception:
        pass


async def republish_ha_discovery(serial: str):
    """Republish HA discovery + state after a device settings change (name, room, etc.)."""
    if _client_ref is None or serial not in _devices:
        return
    try:
        import storage as _storage
        cfg   = _storage.get_devices().get(serial, {})
        state = _state.get(serial, {})
        plans = _storage.get_device_feeding_plans(serial)
        custom_icon_names = [ic["name"] for ic in _storage.get_custom_icons()]
        await ha_mqtt.publish_discovery(_client_ref, serial, cfg, state, extra_icon_names=custom_icon_names)
        await ha_mqtt.publish_state(_client_ref, serial, cfg, state, plans=plans)
    except Exception:
        _LOGGER.exception("Failed to republish HA discovery for %s...", serial[:6])


async def retract_ha_discovery(serial: str, cfg: dict, state: dict):
    """Retract HA MQTT discovery for a device before it is removed."""
    if _client_ref is None:
        return
    try:
        await ha_mqtt.retract_discovery(_client_ref, serial, cfg, state)
    except Exception:
        _LOGGER.exception("Failed to retract HA discovery for %s...", serial[:6])


async def _publish_ha_state(serial: str):
    """Push current device state values to HA MQTT state topics."""
    if _client_ref is None:
        return
    try:
        import storage as _storage
        cfg   = _storage.get_devices().get(serial, {})
        state = _state.get(serial, {})
        plans = _storage.get_device_feeding_plans(serial)
        await ha_mqtt.publish_state(_client_ref, serial, cfg, state, plans=plans)
    except Exception:
        _LOGGER.exception("Failed to publish HA state for %s...", serial[:6])


# ── HA command handling ────────────────────────────────────────────────────

async def _handle_ha_command(serial: str, topic: str, payload: str):
    """Route an HA MQTT command to the device."""
    _, device_type = _devices.get(serial, (None, ""))
    cmd = ha_mqtt.parse_command(topic, payload.strip(), device_type=device_type)
    if cmd is None:
        _LOGGER.warning("Unrecognised HA command topic: %s", topic)
        return
    if cmd.get("_feed_now"):
        ok = await send_command(serial, {"cmd": "MANUAL_FEEDING_SERVICE", "grainNum": 1})
        _LOGGER.info("HA Feed Now %s...: %s", serial[:6], "ok" if ok else "failed")
    elif cmd.get("_open_door"):
        ok = await send_command(serial, {"cmd": "SWITCH_DOOR_SERVICE", "barnDoorState": True})
        _LOGGER.info("HA Open Door %s...: %s", serial[:6], "ok" if ok else "failed")
    elif "_display_text" in cmd:
        text = cmd["_display_text"][:20]
        if text:
            import storage as _storage
            _storage.save_device(serial, {"display_text": text, "display_icon": 0, "display_icon_name": None})
            ok = await send_display(serial, text, 0)
            asyncio.ensure_future(_publish_ha_state(serial))
            _LOGGER.info("HA Display Text %s...: %s", serial[:6], "ok" if ok else "failed")
    elif "_display_icon" in cmd:
        import storage as _storage
        icon_name = cmd["_display_icon"]
        icon_id = ha_mqtt._ICON_NAMES.get(icon_name, None)
        if icon_id is not None and icon_id > 0:
            _storage.save_device(serial, {"display_icon": icon_id, "display_text": ""})
            ok = await send_display(serial, "", icon_id)
        elif icon_name in ha_mqtt._CUSTOM_FRAMES:
            # Built-in custom frame (e.g. Petlibro Salute)
            ok = await send_display_frame(serial, ha_mqtt._CUSTOM_FRAMES[icon_name])
        else:
            # Check user-saved custom icons by name
            saved = {ic["name"]: ic for ic in _storage.get_custom_icons()}
            if icon_name in saved:
                frame = [0] + [r << 7 for r in saved[icon_name]["rows"]] + [0]
                ok = await send_display_frame(serial, frame)
            else:
                # "None" — revert to stored text
                cfg = _storage.get_devices().get(serial, {})
                _storage.save_device(serial, {"display_icon": 0})
                ok = await send_display(serial, cfg.get("display_text", ""), 0)
        asyncio.ensure_future(_publish_ha_state(serial))
        _LOGGER.info("HA Display Icon %s... %s: %s", serial[:6], icon_name, "ok" if ok else "failed")
    elif "_display_frame" in cmd:
        frame = cmd["_display_frame"]
        if isinstance(frame, list) and len(frame) in (7, 8):
            ok = await send_display_frame(serial, frame)
            _LOGGER.info("Custom frame sent to %s...: %s", serial[:6], "ok" if ok else "failed")
    else:
        await send_command(serial, cmd)
        _LOGGER.debug("HA command %s... keys=%s", serial[:6], list(cmd.keys()))


async def handle_ha_command(serial: str, cmd: dict) -> None:
    """Public entry-point for API-driven commands (already-parsed dict)."""
    if cmd.get("_feed_now"):
        ok = await send_command(serial, {"cmd": "MANUAL_FEEDING_SERVICE", "grainNum": 1})
        _LOGGER.info("API Feed Now %s...: %s", serial[:6], "ok" if ok else "failed")
    elif cmd.get("_open_door"):
        ok = await send_command(serial, {"cmd": "SWITCH_DOOR_SERVICE", "barnDoorState": True})
        _LOGGER.info("API Open Door %s...: %s", serial[:6], "ok" if ok else "failed")
    elif "_display_text" in cmd:
        text = cmd["_display_text"][:20]
        if text:
            import storage as _storage
            _storage.save_device(serial, {"display_text": text, "display_icon": 0, "display_icon_name": None})
            ok = await send_display(serial, text, 0)
            asyncio.ensure_future(_publish_ha_state(serial))
            _LOGGER.info("API Display Text %s...: %s", serial[:6], "ok" if ok else "failed")
    elif "_display_frame" in cmd:
        frame = cmd["_display_frame"]
        if isinstance(frame, list) and len(frame) in (7, 8):
            ok = await send_display_frame(serial, frame)
            if ok:
                import storage as _storage
                name = cmd.get("_display_frame_name") or None
                _storage.save_device(serial, {"display_icon_name": name, "display_icon": 0})
                asyncio.ensure_future(_publish_ha_state(serial))
            _LOGGER.info("API Custom frame %s...: %s", serial[:6], "ok" if ok else "failed")
    else:
        await send_command(serial, cmd)
        _LOGGER.debug("API command %s... keys=%s", serial[:6], list(cmd.keys()))


# ── Message handling ───────────────────────────────────────────────────────

def _handle_message(serial: str, topic_str: str, raw: str):
    try:
        data = json.loads(raw)
    except Exception:
        _LOGGER.debug("Non-JSON from %s...", serial[:6])
        return

    cmd = data.get("cmd")

    if cmd == "NTP":
        asyncio.ensure_future(_respond_ntp(topic_str))
        return

    if cmd == "GET_FEEDING_PLAN_EVENT":
        asyncio.ensure_future(_respond_feeding_plan(serial, topic_str))
        return

    if cmd == "FEEDING_PLAN_SERVICE":
        code = data.get("code")
        plans = data.get("plans", [])
        _LOGGER.debug("FEEDING_PLAN_SERVICE from %s... code=%s plans=%d", serial[:6], code, len(plans))
        _mark_online(serial)
        asyncio.ensure_future(_check_and_fire_alerts(serial))
        return

    if cmd == "SWITCH_DOOR_SERVICE":
        code = data.get("code")
        _LOGGER.debug("SWITCH_DOOR_SERVICE ack from %s... code=%s", serial[:6], code)
        _mark_online(serial)
        asyncio.ensure_future(_check_and_fire_alerts(serial))
        return

    if cmd == "MANUAL_FEEDING_SERVICE":
        # Feeder ack for manual feed — code 0 = accepted.
        code = data.get("code")
        _LOGGER.debug("MANUAL_FEEDING_SERVICE ack from %s... code=%s", serial[:6], code)
        _mark_online(serial)
        asyncio.ensure_future(_check_and_fire_alerts(serial))
        return

    if cmd == "GRAIN_OUTPUT_EVENT":
        # Feeder reports grain dispensing progress. Ack it, and track intake on completion.
        asyncio.ensure_future(_ack_grain_output(serial, topic_str, data))
        _mark_online(serial)
        asyncio.ensure_future(_check_and_fire_alerts(serial))
        return

    if cmd == "WAREHOUSE_DOOR_EVENT":
        # Feeder door state change (open/close). Track duration to detect feeding sessions.
        import time as _time
        barn = data.get("barnDoorState")
        if barn is not None:
            prev_barn = _state.get(serial, {}).get("barnDoorState")
            _state.setdefault(serial, {})["barnDoorState"] = barn
            if barn and not prev_barn:
                _state[serial]["_door_open_ts"] = int(_time.time() * 1000)
            elif not barn and prev_barn:
                open_ts = _state[serial].pop("_door_open_ts", None)
                if open_ts:
                    duration_secs = int((_time.time() * 1000 - open_ts) / 1000)
                    try:
                        import storage as _storage
                        cfg = _storage.get_devices().get(serial, {})
                        min_secs = int(cfg.get("min_eating_secs", 30))
                    except Exception:
                        min_secs = 30
                    if duration_secs >= min_secs:
                        try:
                            import time as _time2
                            now_ts = int(_time2.time())
                            _storage.log_feeder_event(
                                serial, "pet_eating",
                                extra={"duration_secs": duration_secs},
                            )
                            _storage.save_device(serial, {"last_fed_ts": now_ts})
                        except Exception:
                            pass
        _mark_online(serial)
        asyncio.ensure_future(_check_and_fire_alerts(serial))
        asyncio.ensure_future(_publish_ha_state(serial))
        return

    if cmd == "DEVICE_START_EVENT":
        # Feeder just booted — ack it.
        asyncio.ensure_future(_ack_device_start(serial, topic_str, data))
        _mark_online(serial)
        asyncio.ensure_future(_check_and_fire_alerts(serial))
        return

    if cmd == "HEARTBEAT":
        rssi = data.get("rssi")
        if rssi is not None:
            _state.setdefault(serial, {})["rssi"] = rssi
        _mark_online(serial)
        asyncio.ensure_future(_check_and_fire_alerts(serial))
        asyncio.ensure_future(_publish_ha_state(serial))
        return

    if cmd in ("ATTR_GET_SERVICE", "ATTR_SET_SERVICE", "ATTR_PUSH_EVENT"):
        skip    = _PROTO_FIELDS | _SENSITIVE_FIELDS
        partial = {k: v for k, v in data.items() if k not in skip}
        if partial:
            _, device_type = _devices.get(serial, (None, None))
            mod       = _device_types.get(device_type) if device_type else None
            old_state = dict(_state.get(serial, {}))
            _state.setdefault(serial, {}).update(partial)
            if mod:
                grams = mod.track_intake(old_state, _state[serial])
                if grams:
                    try:
                        import storage as _storage
                        _storage.record_intake(serial, grams)
                        _LOGGER.debug("Recorded %.0fg intake for %s...", grams, serial[:6])
                    except Exception:
                        _LOGGER.exception("Failed to record intake for %s...", serial[:6])
            asyncio.ensure_future(_persist_state_cache(serial))
        _mark_online(serial)
        asyncio.ensure_future(_check_and_fire_alerts(serial))
        asyncio.ensure_future(_publish_ha_state(serial))
        return

    # Unknown cmd — store non-protocol fields
    skip    = _PROTO_FIELDS | _SENSITIVE_FIELDS
    partial = {k: v for k, v in data.items() if k not in skip}
    if partial:
        _state.setdefault(serial, {}).update(partial)
    _mark_online(serial)


async def _respond_feeding_plan(serial: str, request_topic: str) -> None:
    import time as _time
    global _client_ref
    if _client_ref is None:
        return
    response_topic = request_topic.replace("/post", "/sub")
    # Respond with GET_FEEDING_PLAN_EVENT + stored plans. Empty list is fine — feeder
    # will report code 2099 but runs its stored schedule autonomously.
    import storage as _storage
    stored_plans = _storage.get_device_feeding_plans(serial)
    clean_plans = [{k: v for k, v in p.items() if k != "_enabled"}
                   for p in stored_plans if p.get("_enabled", True)]
    payload = json.dumps({
        "cmd":   "GET_FEEDING_PLAN_EVENT",
        "code":  0,
        "ts":    int(_time.time() * 1000),
        "plans": clean_plans,
    })
    try:
        await _client_ref.publish(response_topic, payload)
        _LOGGER.debug("Feeding plan response sent to %s...", serial[:6])
    except Exception:
        pass


async def _ack_grain_output(serial: str, event_topic: str, data: dict) -> None:
    import time as _time
    global _client_ref
    if _client_ref is None:
        return
    response_topic = event_topic.replace("/post", "/sub")
    ack = json.dumps({
        "cmd":      "GRAIN_OUTPUT_EVENT",
        "ts":       int(_time.time() * 1000),
        "msgId":    data.get("msgId", ""),
        "code":     0,
        "execStep": data.get("execStep", ""),
    })
    try:
        await _client_ref.publish(response_topic, ack)
    except Exception:
        pass
    # Track food dispensed on completion
    if data.get("finished") and data.get("actualGrainNum", 0) > 0:
        try:
            import storage as _storage
            portions = data["actualGrainNum"]
            _storage.record_intake(serial, portions)
            _storage.log_feeder_event(serial, "food_dispensed", portions=portions)
        except Exception:
            pass


async def _ack_device_start(serial: str, event_topic: str, data: dict) -> None:
    import time as _time
    global _client_ref
    if _client_ref is None:
        return
    response_topic = event_topic.replace("/post", "/sub")
    ack = json.dumps({
        "cmd":   "DEVICE_START_EVENT",
        "ts":    int(_time.time() * 1000),
        "msgId": data.get("msgId", ""),
        "code":  0,
    })
    try:
        await _client_ref.publish(response_topic, ack)
        _LOGGER.debug("DEVICE_START_EVENT acked for %s...", serial[:6])
    except Exception:
        pass


async def _respond_ntp(request_topic: str) -> None:
    # NOTE: the timezone field here does NOT affect when scheduled plans fire.
    # executionTime in plans is always UTC (the PetLibro app converts local→UTC
    # before sending). This timezone is only used by the feeder for on-device
    # clock display. It is configurable in Settings → General → Feeder Timezone.
    import time as _time
    import storage as _storage
    global _client_ref
    if _client_ref is None:
        return
    response_topic = request_topic.replace("/post", "/sub")
    settings = _storage.get_settings()
    tz_name = settings.get("feeder_timezone", "") or os.environ.get("TZ", "")
    tz = settings.get("feeder_tz_offset", -7)
    if tz_name:
        try:
            import datetime as _dt
            from zoneinfo import ZoneInfo as _ZI
            tz = int(_dt.datetime.now(_ZI(tz_name)).utcoffset().total_seconds() / 3600)
        except Exception:
            pass
    payload = json.dumps({
        "cmd":            "NTP",
        "ts":             int(_time.time() * 1000),
        "code":           0,
        "calibrationTag": True,
        "timezone":       tz,
    })
    try:
        await _client_ref.publish(response_topic, payload)
    except Exception:
        pass


# ── MQTT loop ──────────────────────────────────────────────────────────────

async def _mqtt_loop():
    global _client_ref
    while True:
        if _reconnect_event:
            _reconnect_event.clear()
        if not _devices:
            if _reconnect_event:
                try:
                    await asyncio.wait_for(_reconnect_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(5)
            continue
        try:
            async with aiomqtt.Client(
                hostname=_host,
                port=_port,
                username=_user if _user else None,
                password=_pass if _pass else None,
                keepalive=60,
            ) as client:
                import time as _time
                _client_ref = client
                import storage as _storage
                for serial, (_, device_type) in list(_devices.items()):
                    topic = _topic_for(device_type, serial)
                    await client.subscribe(topic)
                    _LOGGER.info("Subscribed: %s... model=%s", serial[:6], _mqtt_model(device_type))
                    svc_topic    = _service_sub_topic(device_type, serial)
                    init_payload = json.dumps({
                        "cmd":   "ATTR_GET_SERVICE",
                        "ts":    int(_time.time() * 1000),
                        "msgId": f"{serial}_init",
                    })
                    await client.publish(svc_topic, init_payload)
                    # HA MQTT Discovery
                    cfg   = _storage.get_devices().get(serial, {})
                    state = _state.get(serial, {})
                    plans = _storage.get_device_feeding_plans(serial)
                    for ct in ha_mqtt.get_command_topics(serial, device_type):
                        await client.subscribe(ct)
                    custom_icon_names = [ic["name"] for ic in _storage.get_custom_icons()]
                    await ha_mqtt.publish_discovery(client, serial, cfg, state, extra_icon_names=custom_icon_names)
                    await ha_mqtt.retract_legacy_entities(client, serial, cfg)
                    await ha_mqtt.publish_state(client, serial, cfg, state, plans=plans)
                    await ha_mqtt.publish_availability(client, serial, True)

                async for message in client.messages:
                    if _reconnect_event and _reconnect_event.is_set():
                        break
                    topic_str   = str(message.topic)
                    payload_str = message.payload.decode("utf-8", errors="replace")
                    parts       = topic_str.split("/")

                    # HA command: petlibro_local/{serial}/{key}/set
                    if topic_str.startswith("petlibro_local/") and topic_str.endswith("/set") and len(parts) == 4:
                        ha_serial = parts[1]
                        if ha_serial in _devices:
                            asyncio.ensure_future(_handle_ha_command(ha_serial, topic_str, payload_str))
                        continue

                    # Device telemetry: dl/{model}/{serial}/device/{channel}/post
                    if len(parts) >= 4:
                        serial = parts[2]
                        if serial in _devices:
                            _handle_message(serial, topic_str, payload_str)

        except aiomqtt.MqttError as e:
            _LOGGER.warning("MQTT connection lost: %s — retrying in 10s", e)
            await asyncio.sleep(10)
        except Exception:
            _LOGGER.exception("MQTT loop error — retrying in 10s")
            await asyncio.sleep(10)
        finally:
            _client_ref = None
            for serial in _devices:
                _mark_offline(serial)
            for serial in list(_devices):
                asyncio.ensure_future(_check_and_fire_alerts(serial))


# ── Connection test ────────────────────────────────────────────────────────

async def test_connection(host: str, port: int, user: str, password: str) -> bool:
    """Try a quick connect/disconnect to verify credentials. Returns True on success."""
    async def _try():
        async with aiomqtt.Client(
            hostname=host,
            port=port,
            username=user if user else None,
            password=password if password else None,
        ):
            pass
    try:
        await asyncio.wait_for(_try(), timeout=6)
        return True
    except Exception:
        return False


async def start():
    global _client_task, _reconnect_event
    _reconnect_event = asyncio.Event()
    if _client_task is None or _client_task.done():
        _client_task = asyncio.ensure_future(_mqtt_loop())
        _LOGGER.info("MQTT client task started")
