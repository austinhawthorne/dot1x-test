#!/usr/bin/env python3
import subprocess
import os
import time
import getpass
import signal
import sys

INTERFACE     = input("Enter the network interface name (e.g., eth0): ").strip()
USERNAME      = input("Enter 802.1X username: ").strip()
PASSWORD      = getpass.getpass("Enter 802.1X password: ")

WPA_CONF      = "/tmp/8021x_wpa.conf"
WPA_LOG       = "/tmp/wpa_supplicant.log"
WPA_PID_FILE  = "/tmp/wpa_supplicant.pid"
SUPPLICANT_PID = None

def create_wpa_config():
    cfg = f"""
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
ap_scan=0

network={{
    key_mgmt=IEEE8021X
    eap=PEAP
    identity="{USERNAME}"
    password="{PASSWORD}"
    phase2="auth=MSCHAPV2"
    eapol_flags=0
}}
"""
    with open(WPA_CONF, "w") as f:
        f.write(cfg)
    os.chmod(WPA_CONF, 0o600)

def start_supplicant():
    global SUPPLICANT_PID
    # clean up stale PID file
    try: os.remove(WPA_PID_FILE)
    except FileNotFoundError: pass

    cmd = [
        "wpa_supplicant",
        "-D", "wired",         # force wired 802.1X driver
        "-i", INTERFACE,
        "-c", WPA_CONF,
        "-f", WPA_LOG,
        "-B",                  # daemonize
        "-P", WPA_PID_FILE     # write PID here
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print("[!] wpa_supplicant binary not found. Please install it and ensure it's in your PATH.")
        sys.exit(1)

    if proc.returncode != 0:
        print("[!] wpa_supplicant failed to start (exit code {})".format(proc.returncode))
        print("    stderr:", proc.stderr.strip())
        raise RuntimeError("wpa_supplicant startup error")

    # wait for PID file
    for _ in range(5):
        if os.path.exists(WPA_PID_FILE):
            break
        time.sleep(1)
    else:
        raise RuntimeError("wpa_supplicant did not write PID file in time")

    with open(WPA_PID_FILE) as f:
        SUPPLICANT_PID = int(f.read().strip())
    print(f"[*] wpa_supplicant started (PID {SUPPLICANT_PID})")

def wait_for_auth(timeout=30):
    print("[*] Waiting for 802.1X authentication…")
    deadline = time.time() + timeout
    while time.time() < deadline:
        with open(WPA_LOG, "r", errors="ignore") as f:
            log = f.read()
            if "EAP authentication completed" in log:
                print("[+] 802.1X Authentication SUCCESS")
                return True
            if "authentication failed" in log.lower():
                print("[-] 802.1X Authentication FAILED")
                return False
        time.sleep(1)
    print("[-] 802.1X Authentication TIMED OUT")
    return False

def get_gateway():
    try:
        rt = subprocess.check_output(["ip", "route", "show", "default"]).decode()
        return rt.split()[2]
    except Exception:
        return None

def get_ip():
    out = subprocess.check_output(["ip", "-4", "addr", "show", INTERFACE]).decode()
    for line in out.splitlines():
        if "inet " in line:
            return line.strip().split()[1]
    return None

def run_dhcp():
    print("[*] Running DHCP client…")
    subprocess.run(["dhclient", INTERFACE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    ip = get_ip()
    if ip:
        print(f"[+] IP Address acquired: {ip}")
    else:
        print("[-] No IP address assigned")
    return ip

def run_tests(gw):
    print("[*] Running reachability tests…")
    for tgt in (gw, "8.8.8.8", "www.google.com"):
        if not tgt: continue
        print(f"→ ping {tgt} … ", end="", flush=True)
        res = subprocess.run(
            ["ping", "-c", "3", tgt],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("OK" if res.returncode == 0 else "FAIL")

def cleanup(reset=True):
    global SUPPLICANT_PID
    # 1) Send 802.1X logoff if we're resetting
    if reset:
        try:
            subprocess.run(
                ["wpa_cli", "-i", INTERFACE, "logoff"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print("[*] Sent 802.1X logoff")
            time.sleep(1)   # give the switch a moment
        except Exception as e:
            print(f"[!] Could not send EAPOL logoff: {e}")

    # 2) Kill wpa_supplicant
    if SUPPLICANT_PID:
        try:
            os.kill(SUPPLICANT_PID, signal.SIGTERM)
        except ProcessLookupError:
            pass

    # 3) Kill DHCP client
    subprocess.run(["pkill", "-f", f"dhclient.*{INTERFACE}"])
    if reset:
        # bring interface down, wait, then back up
        print("[*] Bringing interface down for reset…")
        subprocess.run(["ip", "link", "set", "dev", INTERFACE, "down"])
        time.sleep(10)
        print("[*] Bringing interface back up…")
        subprocess.run(["ip", "link", "set", "dev", INTERFACE, "up"])
        # flush any leftover IPs
        subprocess.run(["ip", "addr", "flush", "dev", INTERFACE])
        print("[*] Interface reset to pre-auth state.")

    # 4) Clean up temp files
    for path in (WPA_CONF, WPA_LOG, WPA_PID_FILE):
        try: os.remove(path)
        except FileNotFoundError: pass

def main():
    try:
        create_wpa_config()
        start_supplicant()

        if not wait_for_auth():
            cleanup()
            return

        ip = run_dhcp()
        gw = get_gateway()
        run_tests(gw)

        choice = input("Exit script and [l]eave as-is or [r]eset state? (l/r): ").strip().lower()
        cleanup(reset=(choice == "r"))
        if choice == "l":
            print(f"[*] Leaving interface authenticated with IP {ip}")

    except KeyboardInterrupt:
        print("\n[*] Interrupted by user.")
        cleanup()
    except Exception as e:
        print(f"[!] Fatal error: {e}")
        cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main()
