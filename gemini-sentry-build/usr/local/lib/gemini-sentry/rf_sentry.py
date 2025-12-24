import threading
import time
import subprocess
import re
import os
import signal
import json
import logging
from datetime import datetime

# Configure Logging
logger = logging.getLogger("gemini-sentry")

# ================= CONFIGURATION =================
CONFIG_PATH = "/etc/gemini-sentry/config.json"
DEFAULT_CONFIG = {
    "whitelist": {},  # MAC -> Name
    "approach_delta": 5,
    "approach_window": 10.0,
    "watchdog_timeout": 10.0,
    "wifi_interface": "wlan0",
    "rssi_threshold_alert": -85
}

# Global Config State
CURRENT_CONFIG = DEFAULT_CONFIG.copy()

def load_config():
    """Loads configuration from JSON file."""
    global CURRENT_CONFIG
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                user_config = json.load(f)
                # Update defaults with user values
                CURRENT_CONFIG.update(user_config)
                logger.info(f"SENTRY: Configuration loaded from {CONFIG_PATH}")
        else:
            logger.warning(f"SENTRY: Config not found at {CONFIG_PATH}. Using defaults.")
    except Exception as e:
        logger.error(f"SENTRY: Config Load Error: {e}")

# Load immediately on import
load_config()

# Shared Event Queue
EVENT_QUEUE = []

class SentryWatchdog(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        
        # Threads
        self.bt_thread = None
        self.wifi_thread = None
        
        # Heartbeats
        self.bt_last_beat = time.time()
        self.wifi_last_beat = time.time()
        
        # State
        self.tracking = {} 

    def run(self):
        logger.info("SENTRY: Watchdog Started. Initializing Sensors...")
        
        # Start Workers
        self.start_bt()
        self.start_wifi()
        
        while self.running:
            now = time.time()
            timeout = CURRENT_CONFIG["watchdog_timeout"]
            
            # --- BLUETOOTH WATCHDOG ---
            if now - self.bt_last_beat > timeout:
                logger.warning(f"SENTRY: Bluetooth Heartbeat Lost. RESETTING ADAPTER.")
                self.reset_bt_adapter()
                self.start_bt()
            
            # --- WIFI WATCHDOG ---
            if now - self.wifi_last_beat > (timeout * 3):
                logger.warning("SENTRY: Wi-Fi Heartbeat Lost. Restarting Scanner.")
                self.start_wifi()
                
            time.sleep(2)

    def stop(self):
        self.running = False
        if self.bt_thread: self.bt_thread.stop()
        if self.wifi_thread: self.wifi_thread.stop()

    def start_bt(self):
        if self.bt_thread and self.bt_thread.is_alive():
            self.bt_thread.stop()
        
        self.bt_last_beat = time.time() # Reset beat so we don't loop reset
        self.bt_thread = BluetoothMonitor(self)
        self.bt_thread.start()

    def start_wifi(self):
        if self.wifi_thread and self.wifi_thread.is_alive():
            self.wifi_thread.stop()
            
        self.wifi_last_beat = time.time()
        self.wifi_thread = WifiMonitor(self)
        self.wifi_thread.start()

    def reset_bt_adapter(self):
        """Hard reset of Bluetooth hardware."""
        try:
            subprocess.run(["sudo", "rfkill", "block", "bluetooth"], check=False)
            time.sleep(1)
            subprocess.run(["sudo", "rfkill", "unblock", "bluetooth"], check=False)
            time.sleep(2) # Wait for kernel init
            # Optional: hciconfig reset if available
            subprocess.run(["sudo", "hciconfig", "hci0", "reset"], check=False)
        except Exception as e:
            logger.error(f"SENTRY: Adapter Reset Failed: {e}")

    def update_beat(self, source):
        if source == "bt": self.bt_last_beat = time.time()
        if source == "wifi": self.wifi_last_beat = time.time()

    def process_signal(self, mac, rssi, source):
        """Fusion Engine Logic"""
        self.update_beat(source)
        
        now = time.time()
        mac = mac.upper()
        
        # Check Whitelist
        whitelist = CURRENT_CONFIG.get("whitelist", {})
        if mac in whitelist:
            # Device is known and trusted. Ignore.
            # Optional: Log trusted presence periodically?
            return

        # Initialize Tracking
        if mac not in self.tracking:
            self.tracking[mac] = {'rssi': rssi, 'ts': now, 'history': [rssi]}
            return

        # Delta Calculation
        prev_rssi = self.tracking[mac]['rssi']
        delta = rssi - prev_rssi
        
        # Update State
        self.tracking[mac]['rssi'] = rssi
        self.tracking[mac]['ts'] = now
        self.tracking[mac]['history'].append(rssi)
        
        # Keep history buffer size consistent
        if len(self.tracking[mac]['history']) > 5: self.tracking[mac]['history'].pop(0)

        # --- ALERT LOGIC ---
        delta_threshold = CURRENT_CONFIG.get("approach_delta", 5)
        rssi_threshold = CURRENT_CONFIG.get("rssi_threshold_alert", -85)
        
        if delta >= delta_threshold and rssi > rssi_threshold:
            msg = f"APPROACH DETECTED: Unknown Device ({mac}) | Delta: +{delta}dB | Signal: {rssi}dBm"
            
            logger.warning(f"SENTRY ALERT: {msg}")
            
            EVENT_QUEUE.append({
                "type": "alert", 
                "msg": msg, 
                "ts": now,
                "mac": mac,
                "rssi": rssi
            })


class BluetoothMonitor(threading.Thread):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.running = True
        self.proc = None

    def run(self):
        # Use btmon for passive, real-time streaming
        cmd = ["sudo", "btmon", "-t", "-T"]
        
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            
            # Regex for btmon output
            # Address: XX:XX:XX:XX:XX:XX (Random)
            # RSSI: -62 dBm
            addr_re = re.compile(r"Address:\s+([0-9A-F:]{17})")
            rssi_re = re.compile(r"RSSI:\s+(-?\d+)\s+dBm")
            
            current_mac = None
            
            for line in self.proc.stdout:
                if not self.running: break
                
                # Check Address
                m_addr = addr_re.search(line)
                if m_addr:
                    current_mac = m_addr.group(1)
                    continue
                
                # Check RSSI
                m_rssi = rssi_re.search(line)
                if m_rssi and current_mac:
                    rssi = int(m_rssi.group(1))
                    self.manager.process_signal(current_mac, rssi, "bt")
                    current_mac = None # Reset pair
                    
        except Exception as e:
            logger.error(f"SENTRY: BT Worker Died: {e}")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.proc:
            try: self.proc.terminate() 
            except: pass
            try: self.proc.kill()
            except: pass


class WifiMonitor(threading.Thread):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.running = True

    def run(self):
        # Active Scan Loop
        while self.running:
            try:
                # Use iw scan (Active)
                cmd = ["sudo", "iw", "dev", WIFI_IFACE, "scan"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                bss_re = re.compile(r"^BSS ([0-9A-Fa-f:]{17})")
                sig_re = re.compile(r"signal:\s*(-?\d+)\.\d+ dBm")
                
                curr_mac = None
                
                for line in res.stdout.split('\n'):
                    line = line.strip()
                    if line.startswith("BSS"):
                        m = bss_re.match(line)
                        if m: curr_mac = m.group(1).upper()
                    
                    if "signal:" in line and curr_mac:
                        m = sig_re.search(line)
                        if m:
                            rssi = int(m.group(1))
                            self.manager.process_signal(curr_mac, rssi, "wifi")
                            curr_mac = None
                            
            except subprocess.TimeoutExpired:
                pass # Just loop
            except Exception as e:
                logger.error(f"SENTRY: WiFi Worker Error: {e}")
                time.sleep(2) # Backoff
            
            time.sleep(3) # Pulse Interval

    def stop(self):
        self.running = False
