import signal

# ... (Logging setup) ...

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
    logger.info("Starting Gemini Sentry Daemon...")
    
    # Register Signal Handler for Simulation
    signal.signal(signal.SIGUSR1, simulate_alert)
    logger.info("Simulation Handler Ready. Trigger with: kill -SIGUSR1 <PID>")
    
    # 1. Start the Detection Watchdog
    # The Watchdog inside rf_sentry runs on its own threads (BT/WiFi)
    # and populates rf_sentry.EVENT_QUEUE
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
                    # We run this in a thread so the loop continues (though Tkinter mainloop blocks that thread)
                    alert_thread = AggressiveAlert(msg)
                    alert_thread.start()
                    alert_thread.join() # Wait for the alert to finish (or timeout) before processing next?
                    # Actually, we probably want to block new alerts while one is screaming.
            
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
