# Changelog

All notable changes to the AEG / Electrolux Home Assistant Integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-20

### Added
- Initial release
- Full authentication via Gigya (SAP Customer Data Cloud) + OCP token exchange
- Multi-brand support (AEG, Electrolux)
- Real-time appliance updates via WebSocket
- Sensor platform: state, time, temperature, percentage, generic, nested state sensors
- Binary sensor platform: door state, boolean property sensors
- Switch platform: power, toggle, bool toggle switches
- Button platform: command, filter reset, property command buttons
- Select platform: static and dynamic selection entities
- Number platform: numeric value entities
- Climate platform: AC/heat pump control
- Support for 14 appliance categories: WM, WD, TD, DW, OV, HB, CR, AC, and more
- Config flow with reauth support
- Bilingual UI: Romanian (strings.json) + English (translations/en.json)
- HACS-compatible layout
