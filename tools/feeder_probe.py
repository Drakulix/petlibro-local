"""
Petlibro feeder MQTT probe - interactive command tool for device contributors.

Connects to your local Mosquitto broker and lets you send raw MQTT commands to
a feeder and watch the responses. Useful when adding support for a new feeder
model or investigating what commands a feeder accepts.

Requirements: pip install paho-mqtt
"""

import json
import time
import threading
import paho.mqtt.client as mqtt

# ── Configure these before running ───────────────────────────────────────────

BROKER_HOST = "homeassistant.local"   # HA hostname or IP
BROKER_PORT = 1883
USERNAME    = ""                      # Mosquitto username for this device
PASSWORD    = ""                      # Mosquitto password for this device

SERIAL      = ""                      # Full device serial number (from PetLibro app)
MODEL       = ""                      # Model string, e.g. PLAF301

# ─────────────────────────────────────────────────────────────────────────────

SUB_TOPIC = f"dl/{MODEL}/{SERIAL}/device/+/post"
SVC_SUB   = f"dl/{MODEL}/{SERIAL}/device/service/sub"
EVT_SUB   = f"dl/{MODEL}/{SERIAL}/device/event/sub"


def ts():
    return int(time.time() * 1000)


def send(client, topic, payload: dict):
    body = json.dumps(payload)
    print(f"\n>>> SEND -> {topic}")
    print(json.dumps(payload, indent=2))
    client.publish(topic, body)


def on_connect(client, userdata, flags, rc, props=None):
    if rc == 0:
        print(f"Connected to {BROKER_HOST}:{BROKER_PORT}")
        client.subscribe(SUB_TOPIC)
        print(f"Subscribed: {SUB_TOPIC}\n")
        send(client, SVC_SUB, {
            "cmd":   "ATTR_GET_SERVICE",
            "ts":    ts(),
            "msgId": f"{SERIAL}_probe",
        })
    else:
        print(f"Connection failed rc={rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        pretty  = json.dumps(payload, indent=2)
    except Exception:
        pretty = msg.payload.decode()
    topic_short = msg.topic.replace(f"dl/{MODEL}/{SERIAL}/device/", "")
    print(f"\n<<< {topic_short}")
    print(pretty)


def menu(client):
    time.sleep(2)
    while True:
        print("\n── Commands ─────────────────────────────────")
        print("  1  ATTR_GET_SERVICE (re-request device state)")
        print("  2  Feed Now (MANUAL_FEEDING_SERVICE, 1 portion)")
        print("  3  Open door (SWITCH_DOOR_SERVICE)")
        print("  4  ATTR_SET_SERVICE (custom fields)")
        print("  5  Raw JSON to service/sub")
        print("  6  Raw JSON to event/sub")
        print("  q  Quit")
        choice = input("Choice: ").strip().lower()

        if choice == "1":
            send(client, SVC_SUB, {
                "cmd":   "ATTR_GET_SERVICE",
                "ts":    ts(),
                "msgId": f"{SERIAL}_get",
            })

        elif choice == "2":
            send(client, SVC_SUB, {
                "cmd":      "MANUAL_FEEDING_SERVICE",
                "ts":       ts(),
                "msgId":    f"{SERIAL}_feed",
                "grainNum": 1,
            })

        elif choice == "3":
            send(client, SVC_SUB, {
                "cmd":          "SWITCH_DOOR_SERVICE",
                "ts":           ts(),
                "msgId":        f"{SERIAL}_door",
                "barnDoorState": True,
            })

        elif choice == "4":
            fields_raw = input("Fields as JSON object (e.g. {\"volume\": 50}): ").strip()
            try:
                fields = json.loads(fields_raw)
                payload = {"cmd": "ATTR_SET_SERVICE", "ts": ts(), "msgId": f"{SERIAL}_set"}
                payload.update(fields)
                send(client, SVC_SUB, payload)
            except Exception as e:
                print(f"Bad JSON: {e}")

        elif choice == "5":
            raw = input("JSON payload: ").strip()
            try:
                send(client, SVC_SUB, json.loads(raw))
            except Exception as e:
                print(f"Bad JSON: {e}")

        elif choice == "6":
            raw = input("JSON payload: ").strip()
            try:
                send(client, EVT_SUB, json.loads(raw))
            except Exception as e:
                print(f"Bad JSON: {e}")

        elif choice == "q":
            client.disconnect()
            break


if __name__ == "__main__":
    if not SERIAL or not MODEL or not USERNAME:
        print("ERROR: fill in BROKER_HOST, USERNAME, PASSWORD, SERIAL, and MODEL at the top of this file.")
        raise SystemExit(1)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USERNAME, PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)

    t = threading.Thread(target=menu, args=(client,), daemon=True)
    t.start()
    client.loop_forever()
