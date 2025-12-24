import signal
import time
import logging
import threading
import tkinter as tk
from tkinter import font
import rf_sentry

# Configure Logging
logger = logging.getLogger("gemini-sentry")

class AggressiveAlert(threading.Thread):
    """
    Displays a fullscreen, aggressive alert overlay.
    CAPTURES INPUT until acknowledged or timed out.
    """
    def __init__(self, message):
        super().__init__()
        self.message = message
        self.daemon = True # Ensure thread dies if main process dies

    def run(self):
        try:
            root = tk.Tk()
            root.title("GEMINI SENTRY ALERT")
            
            # --- SECURITY & LOCKING ---
            root.attributes('-fullscreen', True)
            root.attributes('-topmost', True)
            root.configure(background='red')
            root.update_idletasks()
            
            # Capture Input (The "Lock")
            root.grab_set()
            root.focus_force()
            
            # --- UI ELEMENTS ---
            # Flashing/Audio could go here
            
            lbl_font = font.Font(family="Helvetica", size=48, weight="bold")
            lbl = tk.Label(root, text=f"THREAT DETECTED\n\n{self.message}\n\n[PRESS CTRL + ESC TO DISMISS]", 
                           fg="white", bg="red", font=lbl_font, justify="center")
            lbl.pack(expand=True)
            
            # --- FAIL-SAFES (The Fix) ---
            
            def dismiss(event=None):
                logger.info("Alert acknowledged by user.")
                root.destroy()

            def timeout_kill():
                logger.warning("Alert timed out (45s). Auto-dismissing to prevent lockout.")
                root.destroy()
            
            # 1. Manual Dismiss (Strict: Only Ctrl+Esc)
            root.bind('<Control-Escape>', dismiss)
            
            # 2. Watchdog Timeout (prevent lock-screen deadlocks)
            root.after(45000, timeout_kill) 
            
            root.mainloop()
            
        except Exception as e:
            logger.error(f"Failed to launch GUI Alert: {e}")

def simulate_alert(signum, frame):
    """Signal Handler for SIGUSR1 - Injects Simulation."""
    logger.info("RECEIVED SIGNAL: SIGUSR1 - INJECTING SIMULATION")
    rf_sentry.EVENT_QUEUE.append({
        "type": "alert",
        "msg": "SIMULATED THREAT DETECTED (User Test)",
        "ts": time.time(),
        "mac": "FF:FF:FF:FF:FF:FF",
        "rssi": -50
    })

def main():
    # Setup Basic Logging if not already handled by rf_sentry
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Starting Gemini Sentry Daemon...")
    
    # Register Signal Handler for Simulation
    signal.signal(signal.SIGUSR1, simulate_alert)
    logger.info("Simulation Handler Ready. Trigger with: kill -SIGUSR1 <PID>")
    
    # 1. Start the Detection Watchdog
    sentry = rf_sentry.SentryWatchdog()
    sentry.start()
    
    logger.info("Detection Engine Online. Monitoring Queue...")
    
    # 2. Main Event Loop
    while True:
        try:
            if rf_sentry.EVENT_QUEUE:
                # Pop the oldest event
                event = rf_sentry.EVENT_QUEUE.pop(0)
                
                if event.get("type") == "alert":
                    msg = event.get("msg", "Unknown Threat")
                    logger.warning(f"PROCESSING ALERT: {msg}")
                    
                    # Launch the Aggressive Alert
                    # Run in a thread, but the GUI itself has a mainloop that blocks *that* thread.
                    # We join() to ensure we don't spawn 100 windows if the queue floods.
                    alert_thread = AggressiveAlert(msg)
                    alert_thread.start()
                    alert_thread.join() 
            
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            logger.info("Stopping Sentry Daemon...")
            sentry.stop()
            break
        except Exception as e:
            logger.error(f"Main Loop Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
