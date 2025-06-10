Simple script to test 802.1X on a wired ethernet port.  Prompts for interface, username/password, and provides status and reachability test after Success.  Gives option to leave the host state as is after the test or restore to pre-test state.

Usage:  sudo python dot1x-test.py

```
client1:~/dot1x-test $ sudo python dot1x-test.py 
Enter the network interface name (e.g., eth0): eth0
Enter 802.1X username: bob
Enter 802.1X password: 
[*] wpa_supplicant started (PID 2396)
[*] Waiting for 802.1X authentication…
[+] 802.1X Authentication SUCCESS
[*] Running DHCP client…
[+] IP Address acquired: 10.0.4.119/24
[*] Running reachability tests…
→ ping 10.0.4.1 … OK
→ ping 8.8.8.8 … OK
→ ping www.google.com … OK
Exit script and [l]eave as-is or [r]eset state? (l/r): r
[*] Sent 802.1X logoff
[*] Bringing interface down for reset…
[*] Bringing interface back up…
[*] Interface reset to pre-auth state.

Notes:
- Only setup to do EAP-PEAP
