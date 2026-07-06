# BLE Explorer

A BLE (Bluetooth Low Energy) test tool for Windows. Built as **an alternative to nRF Connect for Desktop (BLE)**, it is used for firmware debugging/validation, advertisement packet analysis, standard BLE service discovery, and long-running notify monitoring.

![version](https://img.shields.io/badge/version-1.0.0-blue) ![platform](https://img.shields.io/badge/platform-Windows%2010%2B-lightgrey) ![Python](https://img.shields.io/badge/python-3.12%2B-green)

## Features

### Scan
- Real-time BLE device scan (name / address / RSSI / advertising interval)
- Live name & MAC search filter
- **Advertisement packet analysis**
  - Raw AD breakdown — shows each AD field (type / length / value), for validating firmware advertisement packets
  - Automatic decoding of known formats — iBeacon, Eddystone (UID/URL/TLM), Manufacturer Data (Company ID + payload hex/ASCII)
  - Advertising-interval estimation — corrects for Windows reception characteristics (duplicate bursts / missed events)
  - Receive count, TX Power, service UUID name resolution

### Connect (multiple simultaneous devices)
- One tab per device — connect to / operate several devices at once
- **Connection parameter display** — MTU, PHY (1M/2M/Coded), Connection Interval, Link Timeout
  - Polls every 2 seconds to track the firmware's connection-parameter-update negotiation (logs changes)
- Step-by-step connection timing log (connect + service discovery duration, service/characteristic counts)
- Connects using device info cached during the scan — skips bleak re-discovery for faster connections
- Detects unexpected disconnects + reconnect button

### GATT
- Card-style service/characteristic view — large service name, small UUID
- Expanding a characteristic row auto-reads it; inline Write (hex/string/byte); notify is toggled with the ▶/⏸ in the header
- Automatic parsing of standard characteristic values — Battery Level (%), Device Name, Heart Rate (bpm), PnP ID, etc.
- **UUID name resolution** — built-in Bluetooth SIG DB + user aliases (right-click → set alias, saved to `uuid_aliases.json`)
- Copy UUID (right-click); abbreviated UUID tooltip shows the full UUID

### Misc
- Dark/light theme toggle (setting persisted)
- Log panel — per-device filter, clear, export to txt. Records notify values with timestamps
- Single-exe distribution (PyInstaller)

## Requirements

- Windows 10 (build 19041+) / Windows 11 — PHY and connection-parameter queries require 19041 or newer
- A Bluetooth adapter (with BLE support)
- To run from source: Python 3.12+

## Installation & Run

### Using the exe (end users)

Download the latest `BLE_Explorer_v*.exe` from the [Releases](https://github.com/gazam2842/desktop-ble-Explorer/releases) page and run it. No installation required.

### Running from source (development)

```bash
git clone https://github.com/gazam2842/desktop-ble-Explorer.git
cd desktop-ble-Explorer
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

### Building the exe

```bash
build.bat
```

After the tests pass, `dist\BLE_Explorer_v<version>.exe` is produced. The version is managed in `version.py`.

## Usage Summary

1. **Scan** button → refreshes the device list; selecting a device shows advertisement details on the right
2. **Double-click** a device → connect (scan auto-pauses) → creates a device tab
3. **Click** a characteristic row → expand + auto Read / **▶** button → subscribe to notify
4. **Right-click** a UUID → set alias / copy UUID
5. Filter and export per device from the log at the bottom

## Project Structure

```
main.py              entry point (integrates asyncio + Qt via qasync)
controller.py        scan + device session management
version.py           app version (single source of truth)
ble/
  scanner.py         BleakScanner wrapper
  connection.py      BleakClient connect/disconnect
  session.py         per-device session (GATT ops, notify, parameter polling)
  gatt_ops.py        GATT read/write/notify
  adv_parser.py      first-pass advertisement parsing
  adv_decode.py      AD field breakdown/decoding, interval estimation
  conn_params.py     connection parameter query (MTU/PHY/Interval)
  uuid_names.py      SIG UUID name DB + user aliases
  char_parsers.py    standard characteristic value parsing
  codec.py           hex/string/byte conversion
ui/
  main_window.py     tab-based main window
  device_list.py     scan result table
  adv_detail_panel.py advertisement detail (accordion)
  device_view.py     device tab (connection info + GATT)
  gatt_card_view.py  card-style GATT view
  log_panel.py       log (filter/export)
  theme/             dark/light QSS
tests/               pytest unit tests (mostly pure logic)
```

## Tech Stack

| Component | Choice |
|---|---|
| GUI | PyQt6 |
| BLE | bleak (Windows WinRT backend) |
| async integration | qasync (asyncio ↔ Qt event loop) |
| testing | pytest + pytest-asyncio |
| distribution | PyInstaller (single exe) |

## Tests

```bash
.venv\Scripts\python -m pytest
```

Runs without BLE hardware — the bleak/WinRT dependencies are verified with fake objects.

## Known Limitations

- **Windows only** — depends on WinRT (PHY/connection parameters, raw AD extraction)
- The advertising interval is an estimate (shown with `≈`) — Windows scan duty-cycle characteristics introduce error
- HCI/SMP-level handshake logs are not available (Windows does not expose them)
- Connection time is longer than nRF-dongle-based tools (due to the Windows BLE stack's GATT cache build step)
- Connection parameter queries depend on bleak's internals — if bleak changes, only that display falls back to N/A

## License

Not specified yet. Add a `LICENSE` file to declare terms before public distribution.
