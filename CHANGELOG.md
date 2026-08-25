# Petlibro Local Changelog

For full release notes and details on each version, see the [GitHub Releases page](https://github.com/smcneece/petlibro-local/releases).

## 2026.08.4
- Dockstream 2 Smart Fountain: added `WF02` as a recognized serial prefix for Auto Setup, confirmed by a user-submitted device. Same `PLWF106` MQTT model as `WF03` units, just a different hardware/serial revision
- New "Download Debug Capture" button in Help/About: the app now continuously keeps a rolling log of raw dl/ MQTT traffic in the background, including from devices it doesn't recognize yet (marked UNRECOGNIZED in the download). Since these devices only check in occasionally, capturing continuously instead of during a fixed window means intermittent devices still get caught. Makes it much easier to diagnose an unsupported or misbehaving device without walking through a manual `mosquitto_sub` capture

## 2026.08.3
- Hasn't eaten alert: per-pet configurable alert that fires via bell, email, and mobile push if no eating session is detected within a set number of hours. Enabled in the pet profile and auto-dismisses when an eating session is logged
- New Home Assistant sensor: Last Eating Duration (seconds). Updates after every qualifying door session — RFID or manual — so automations can check how long a pet was at the feeder to decide whether to skip or dispense the next meal
- Minimum drink detection threshold is now configurable per fountain in the Maintenance tab. Default is 5g (≈ 1 tsp), down from the previous hardcoded 10g. Lower it for kittens or small sips; raise it if pump turbulence triggers false readings
- Fountain drink log: each detected drinking event (weight drop between 10g and 800g) is now recorded with a timestamp and volume. The Log tab on a fountain device card now shows a timestamped drink activity list instead of the 7-day bar chart. Daily totals are still shown on the device card and in the overview tab
- Next meal time on the feeder card now shows the time only (3:00 AM) without a Tomorrow or weekday prefix
- Storage writes are now atomic: data is written to a temporary file and replaced in place, preventing configuration loss on ungraceful host power loss or reboot
- Clearing all feeding plans now correctly clears the Next Meal sensor in Home Assistant instead of leaving the previous timestamp displayed indefinitely
- Editing or saving feeding plans now immediately pushes the updated Next Meal state to Home Assistant; previously the sensor stayed stale until the next device MQTT message
- Adding, renaming, or deleting a custom display icon now immediately updates the Display Icon select entity options in Home Assistant without requiring an app restart
- Selecting a display icon via a Home Assistant automation or dashboard now correctly saves the icon name, so the app card reflects the active icon
- Active custom display icon name now correctly reported to the Home Assistant select entity after app restart; previously the select would revert to "None" if a user-created icon was active
- Bowl cleaning, manual lid access, and other non-feeding door events no longer update the "Last Fed" timestamp in the app and Home Assistant sensor
- Device alert notifications now use unique IDs per device and alert type, so a second feeder going offline no longer overwrites the first feeder's notification in the HA bell panel
- Pet eating notifications also carry unique IDs, so Finn's notification and Zoey's notification appear as separate bell entries
- Offline alerts auto-dismiss from the HA bell and mobile push when a device comes back online
- Hardcoded English strings in the device detail modal (LED Display, Scrolling Text, door open log entries, notification channel labels) are now routed through the i18n system

## 2026.08.2
- Offline watchdog: devices are now marked offline in Home Assistant and the app if no MQTT message is received within 5 minutes, catching power loss and Wi-Fi drops without requiring a broker restart
- Offline and back-online notifications now fire correctly via email, mobile push, and HA persistent notification when a device goes silent or reconnects
- Notification subject lines now include the alert type so the reason is visible without opening the email
- Alert bell in the app header now opens a dropdown listing all active alerts by device; clicking an alert opens that device's detail modal
- RFID tag detection: confirmed field names from live capture (`rfid` for tag, `type` for NEAR/LEAVE action). Eating sessions are logged with duration and linked to the pet profile. RFID tag number auto-detected on first scan and stored on the pet profile, or entered manually behind an eye toggle
- RFID-only pet meal tracking: pet Recent Activity shows only RFID-confirmed eating sessions. Duration is measured from feeder door open to close (accurate eating time), but only when the door was triggered by an RFID scan. Manual access, bowl cleaning, and scheduled dispenses are excluded. Door-only events appear in the device log as "Door open for Xs"
- 30-second minimum for RFID eating sessions; short tag passes and walk-bys are ignored. Duplicate entries from the same session are deduplicated automatically
- Pet activity notifications: when an RFID eating session is detected, a notification fires via the same channels as device alerts (bell, email, mobile push) — e.g. "Zoey ate for 3m25s at Zoey's Feeder". Per-pet notification toggles stored on the pet profile
- Pet profiles now show a Recent Activity log. Foundation is in place to extend pet timelines to fountains and litter boxes as RFID-capable devices are added
- Delete pet moved from the modal footer to a trash icon on the pet card, preventing accidental deletion confusion with the activity log
- Pet modal Save button is now compact and centered rather than full-width
- Timestamps in activity logs now zero-pad single-digit hours (07:03 AM instead of 7:03 AM) for consistent column alignment
- Pet list on desktop is now centered and max-width constrained instead of stretching full screen width

## 2026.08.1
- Initial public beta
- Local MQTT support for **Dockstream 2** and **Dockstream 2 Cordless** fountains. Completely offline, no PetLibro cloud required
- Local MQTT support for **OneRFID Smart Feeder (PLAF301)**
- Fountain monitoring: real-time water level (grams/ml/oz), filter days remaining, cleaning days remaining, pump on/off switch, light on/off switch, battery level (cordless model)
- Feeder monitoring: food level (OK/Low), lid state, desiccant days remaining, last fed time, next scheduled meal time
- Feeder controls: Feed Now button, Open Door button, volume slider (0 to 100), display text (up to 20 characters), display icon (None, Heart, Dog, Cat, Elk)
- **Custom Icon Editor**: 5 × 12 pixel grid with click-and-drag drawing and live 26-wide display preview. Save up to 12 named icons. Built-in presets include the stock PetLibro icons and the Petlibro Salute easter egg. All sends work fully offline over local MQTT
- Feeding schedule management: view, add, edit, enable/disable, and skip scheduled meals. Times entered in local time and converted to UTC automatically
- Pet profiles: name, photo, breed, weight, linked devices. Pet avatar badges overlay device cards
- Maintenance tracking: filter replacement, fountain cleaning, bowl cleaning, housing cleaning. Configurable intervals with overdue alerts
- Notifications: in-app bell, email (any HA notify service), mobile push. Configurable per device and per alert type
- Home Assistant MQTT Discovery: all devices, sensors, switches, buttons, numbers, selects, and text entities auto-created in HA. Survives restarts and device renames. Availability tracking (online/offline)
- Feeder timezone: auto-detected from browser and HA Supervisor on first install. Named timezone select with DST-aware automatic conversion, no manual UTC offset needed
- Water intake tracking: daily grams logged per fountain, shown on device card and in detail modal
- Dark/light theme following system preference
- Mobile layout: floating action buttons for Add Device and Alerts on narrow screens, responsive card grid
