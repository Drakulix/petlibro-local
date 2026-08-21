# Petlibro Local Changelog

For full release notes and details on each version, see the [GitHub Releases page](https://github.com/smcneece/petlibro-local/releases).

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
