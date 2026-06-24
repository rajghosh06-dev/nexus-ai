import time
import csv
import os
from datetime import datetime
from ping3 import ping

# --- Configuration ---
# We use major DNS servers as reliable proxies for network stability.
# You can replace these with exact game server IPs if you find them.
SERVERS = {
    "Google_DNS": "8.8.8.8",
    "Cloudflare": "1.1.1.1"
}

# Go up one directory from 'src' to reach 'data'
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "raw_pings.csv")
PING_INTERVAL = 10  # Time in seconds between pings


def setup_csv():
    """Creates the data directory and CSV with headers if they don't exist."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            # Headers for our dataset
            writer.writerow(["timestamp", "server_name", "ip_address", "latency_ms"])
        print(f"[*] Created new log file at {LOG_FILE}")


def start_tracking():
    """Main loop that pings servers and logs the latency."""
    setup_csv()
    print(f"[*] Starting NexusAI Latency Tracker...")
    print(f"[*] Logging data to: {os.path.abspath(LOG_FILE)}")
    print("[*] Press Ctrl+C to stop.\n")

    try:
        while True:
            # Open file in append mode
            with open(LOG_FILE, mode='a', newline='') as file:
                writer = csv.writer(file)

                for name, ip in SERVERS.items():
                    # ping() returns delay in seconds. Timeout is 2 seconds.
                    delay = ping(ip, timeout=2)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    if delay is None or delay is False:
                        # -1.0 represents a dropped packet (timeout)
                        latency_ms = -1.0
                        print(f"[{timestamp}] {name} ({ip}) - TIMEOUT / PACKET LOSS")
                    else:
                        # Convert to milliseconds
                        latency_ms = round(delay * 1000, 2)
                        print(f"[{timestamp}] {name} ({ip}) - {latency_ms} ms")

                    # Write row to CSV
                    writer.writerow([timestamp, name, ip, latency_ms])

            # Wait before next ping cycle
            time.sleep(PING_INTERVAL)

    except KeyboardInterrupt:
        print("\n[*] Latency tracking stopped by user.")


if __name__ == "__main__":
    # Ensure ping3 doesn't require root/admin privileges on your OS setup
    start_tracking()