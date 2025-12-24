# Gemini Sentry

**Automated Proximity Detection & Aggressive Alert System**

This daemon monitors local Bluetooth and Wi-Fi airwaves for rapidly approaching devices. When a device's signal strength (RSSI) increases significantly within a short window (indicating physical approach), it triggers an aggressive "High Alert" state.

## Features

*   **Aggressive Alert:** Fullscreen flashing red overlay (Interrupts user input) + Max Volume Alarm.
*   **Passive & Active Scanning:** Uses `btmon` (Bluetooth) and `iw` (Wi-Fi) to detect devices.
*   **Configurable:** Allowlist your own devices to prevent false positives.
*   **Daemonized:** Runs as a systemd service, auto-restarting on failure.

## Installation

```bash
sudo dpkg -i gemini-sentry_1.0.0_all.deb
sudo systemctl start gemini-sentry
```

## Configuration

Edit `/etc/gemini-sentry/config.json` to whitelist your devices:

```json
{
    "whitelist": {
        "11:22:33:44:55:66": "My Phone",
        "AA:BB:CC:DD:EE:FF": "Headphones"
    },
    "approach_delta": 5,
    "rssi_threshold_alert": -85
}
```

Restart the service to apply changes:
`sudo systemctl restart gemini-sentry`

## Testing / Simulation

To verify the alarm system is working without needing to physically approach your device:

```bash
# Triggers the Fullscreen Alert & Sound immediately
sudo pkill -SIGUSR1 -f sentry_daemon.py
```

**WARNING:** This will maximize your system volume and flash your screen.

## Privacy & Safety

*   This tool monitors **local RF signals**. It does not transmit data externally.
*   The `config.json` is stored locally on your machine.
