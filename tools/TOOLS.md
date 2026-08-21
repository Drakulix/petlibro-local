# Tools

Developer and diagnostic scripts. Not required for normal use of Petlibro Local.

Open each script in a text editor — full setup instructions are at the top of the file.

---

## mqtt_proxy.py — Credential and packet capture

Transparent MQTT proxy. Captures your device's MQTT username and password and logs
all traffic between the device and the PetLibro cloud. Used for adding a device
manually and for reverse-engineering new device types.

Requires Python 3.9+, no extra packages.

> **Privacy:** `mqtt_proxy.log` contains credentials and device data in plain text.
> Do not post it publicly or attach it to GitHub issues.

---

## feeder_probe.py — Interactive feeder command tool

Connects to your local Mosquitto broker and lets you send MQTT commands to a feeder
interactively. Useful for testing commands on a new device model.

Requires Python 3.9+ and paho-mqtt (`pip install paho-mqtt`).

---

If you capture useful packet logs for a device that is not yet supported,
please open an issue or pull request on the
[Petlibro Local GitHub repository](https://github.com/smcneece/petlibro-local).
