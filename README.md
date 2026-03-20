# AEG / Electrolux - Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/v/release/emanuelbesliu/homeassistant-aeg)](https://github.com/emanuelbesliu/homeassistant-aeg/releases/latest)
[![License](https://img.shields.io/github/license/emanuelbesliu/homeassistant-aeg)](LICENSE)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/emanuelbesliu)

**Custom Home Assistant integration for AEG / Electrolux smart appliances using the OCP internal API.**

Monitor and control your washing machines, tumble dryers, dishwashers, ovens, air conditioners, and more — directly from Home Assistant with real-time WebSocket updates.

---

## IMPORTANT DISCLAIMER

**This integration is developed independently through REVERSE ENGINEERING for personal and educational use only.**

- **NOT affiliated with** AEG or Electrolux AB
- **NOT endorsed by** AEG or Electrolux AB
- **NOT supported by** AEG or Electrolux AB
- AEG and Electrolux have **NO responsibility or liability** for this integration
- **Use at your own risk**
- This integration may **stop working** at any time if Electrolux changes their API
- By using this integration, you acknowledge that it is **unofficial** and **unsupported**

**The author (Emanuel Besliu) provides this integration "AS IS" without any warranty.**

---

## Features

- **OCP Internal API** - Uses the same API as the official AEG/Electrolux mobile app (not the limited public developer API)
- **Real-Time Updates** - WebSocket connection for instant appliance state changes
- **Multi-Brand Support** - Works with AEG and Electrolux accounts
- **14 Appliance Categories** - WM (washing machine), WD (washer-dryer), TD (tumble dryer), DW (dishwasher), OV (oven), HB (hob), CR (cooker range), AC (air conditioner), and more
- **7 Entity Platforms** - Sensors, binary sensors, switches, buttons, selects, numbers, climate
- **Secure Authentication** - Full Gigya (SAP Customer Data Cloud) OAuth flow with token refresh
- **Config Flow** - Easy setup via the HA UI with reauth support
- **Bilingual UI** - Romanian and English

## Supported Appliance Types

| Code | Type | Examples |
|------|------|---------|
| WM | Washing Machine | LFR73164OE, L9FEC969S |
| WD | Washer-Dryer | LWR7596O5Q |
| TD | Tumble Dryer | TR938M6C, T9DBC68SC |
| DW | Dishwasher | FSE74718P, FFB83806PM |
| OV | Oven | BPK748380B, BSK798380B |
| HB | Hob | IKE84471FB |
| CR | Cooker Range | Combined oven + hob |
| AC | Air Conditioner | Various split/portable units |
| DH | Dehumidifier | - |
| HD | Hood | - |

## Installation

### Option 1: Copy to custom_components

1. Copy the `custom_components/aeg` folder to your Home Assistant `custom_components` directory:
   ```
   /config/custom_components/aeg/
   ```

2. Restart Home Assistant

3. Go to **Settings** > **Devices & Services** > **Add Integration**

4. Search for "**AEG**"

5. Enter your AEG/Electrolux account credentials (same as the mobile app)

### Option 2: HACS (Coming Soon)

Will be available after testing and release.

## Configuration

1. **Settings** > **Devices & Services** > **Add Integration**
2. Search for "**AEG**"
3. Enter your **email** (same as the AEG/Electrolux app)
4. Enter your **password**
5. Select your **brand** (AEG or Electrolux)
6. Enter your **country code** (e.g., RO, DE, FR, UK, SE)
7. Click **Submit**

The integration will authenticate, discover all appliances on your account, and create entities automatically.

## Entity Platforms

### Sensors
- Appliance state (Running, Off, Paused, etc.)
- Cycle phase (Wash, Rinse, Spin, Dry, etc.)
- Time to end (minutes remaining)
- Temperature readings
- Percentage values (humidity, progress)
- Cycle counters, total working time

### Binary Sensors
- Door state (open/closed)
- Boolean property sensors (remote control enabled, etc.)

### Switches
- Power on/off
- Toggle switches for various appliance features

### Buttons
- Start/stop/pause commands
- Filter reset buttons

### Selects
- Program/cycle selection
- Mode selection

### Numbers
- Temperature setpoints
- Timer values
- Numeric settings

### Climate (AC only)
- Temperature control
- HVAC mode (cool, heat, fan, dry, auto)
- Fan speed
- Swing mode

## File Structure

```
custom_components/aeg/
├── __init__.py          # Integration setup and entry management
├── api.py               # OCP API client (REST + token management)
├── gigya.py             # Gigya/SAP authentication (login, JWT, OAuth1 HMAC-SHA1)
├── websocket.py         # WebSocket client for real-time updates
├── coordinator.py       # Data update coordinator (WS + polling fallback)
├── config_flow.py       # UI configuration flow with reauth
├── const.py             # Constants (API keys, URLs, endpoints, categories)
├── entity.py            # Base entity class
├── sensor.py            # Sensor entities (7 types)
├── binary_sensor.py     # Binary sensor entities
├── switch.py            # Switch entities
├── button.py            # Button entities
├── select.py            # Select entities
├── number.py            # Number entities
├── climate.py           # Climate entity (AC/heat pump)
├── manifest.json        # Integration metadata
├── strings.json         # Romanian translations
└── translations/
    └── en.json          # English translations
```

## How It Works

### Authentication Flow
1. Client credentials token from OCP API
2. Gigya identity provider discovery (per brand + country)
3. Gigya socialize.getIDs (device tracking)
4. Gigya accounts.login (email + password)
5. Gigya accounts.getJWT with OAuth1 HMAC-SHA1 signature
6. OCP token exchange (JWT -> access_token + refresh_token)
7. Automatic token refresh every 12 hours

### Data Flow
- **WebSocket**: Real-time push updates when appliance state changes
- **Polling fallback**: Periodic REST API polling if WebSocket disconnects
- **Coordinator**: Manages data updates, caching, and retry logic

## License

MIT License - Copyright (c) 2026 Emanuel Besliu

## Legal Notice

This integration is developed independently through reverse engineering for personal and educational use only. It is NOT affiliated with, endorsed by, or supported by AEG, Electrolux AB, or any of their subsidiaries. AEG and Electrolux have no responsibility or liability for this integration. Use at your own risk.

The AEG and Electrolux names and logos are trademarks of Electrolux AB. This project is not endorsed by or affiliated with AEG or Electrolux AB.

---

## Support the Developer

If you find this project useful, consider buying me a coffee!

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/emanuelbesliu)

---

**Developed by Emanuel Besliu (@emanuelbesliu)**
