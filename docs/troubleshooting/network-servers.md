# Network Servers is empty / cannot open a Windows share

Applies to Spaced Linux 9.26.3 and later (installed systems receive the
needed packages through Spaced Update). All commands below run in
MATE Terminal. This system uses sysvinit: there is no `systemctl` here;
services are managed with `/etc/init.d/<name> status`.

## 1. Set up something to find

You need at least one other computer sharing files on the same local
network (same Wi-Fi or same router; no VPN in between).

### Windows 10/11 PC with a shared folder

1. On the Windows PC, create a folder (for example `C:\Share`), right-click
   it, choose **Properties**, open the **Sharing** tab, and click **Share**.
   Add the user account that is allowed to open it. Note the network path
   Windows shows, for example `\\DESKTOP-ABC123\Share`.
2. Turn on discovery on the Windows PC: open **Settings > Network &
   internet**, click your connection, and set the **Network profile** to
   **Private** (the Public profile blocks discovery). Then open
   **Control Panel > Network and Sharing Center > Advanced sharing
   settings** and turn on **Network discovery** and **File and printer
   sharing** for the Private profile.
3. Leave the Windows PC awake and connected to the same network as the
   Spaced machine.

### Optional: a second source

- A NAS box or a Linux server with Samba file sharing turned on, or
- a Mac with **System Settings > General > Sharing > File Sharing**
  enabled.

## 2. Browse from Spaced Linux

1. Double-click the **Network Servers** icon on the desktop, or open Caja
   and click **Network** (sometimes shown as **Browse Network**) in the
   sidebar.
2. Wait up to a minute. Browsing is not instant: the system sends
   discovery queries and each computer answers in its own time. Press
   **Reload** (or Ctrl+R) once after waiting if the window is still empty.
3. What you should see:
   - Macs, Linux servers, NAS devices and network printers appear as
     hosts (found through mDNS/DNS-SD).
   - Windows 10/11 PCs appear through WS-Discovery. Caja's `gvfsd-wsdd`
     backend starts the `wsdd` program in discovery-only mode while you
     browse; it does not announce this computer and is not a system service.
   - Very old devices that only speak NetBIOS/SMB1 browsing usually do
     **not** appear. That list has been empty on modern networks for
     years; it is not a Spaced bug. Use the direct connection in step 3
     instead.
4. One-way street: Spaced Linux finds other computers, but other computers
   do **not** see the Spaced machine in their network browser. Spaced ships
   no file-sharing server, only the tools to open other computers' shares.

## 3. Connect directly (works even when browsing finds nothing)

In Caja, choose **Go > Connect to Server**, or press **Ctrl+L** and type
the address directly. Try these forms in order, replacing `PC-NAME`,
`IP-ADDRESS` and `share` with yours:

- `smb://PC-NAME/share`
- `smb://IP-ADDRESS/share` (most reliable; numbers never depend on
  name resolution)
- `smb://PC-NAME.local/share` (needs mDNS; see step 4)

You can find the Windows IP address on that PC with `ipconfig` in
Command Prompt (look for the IPv4 address).

When the share opens, a password dialog appears:

- **Username:** the Windows account name allowed on the share. If the
  Windows PC signs in with a Microsoft account, use the full email
  address as the username.
- **Domain:** leave as suggested, or use the Windows computer name when
  the account is a local (non-Microsoft) account.
- Tick **Remember password** (or **Save in keyring**) to store it in the
  login keyring so you are not asked again. The keyring unlocks at login.

To keep the share handy, open it once and choose **Bookmarks > Add
Bookmark** in Caja, or save the connection in **Gigolo** (installed by
default).

## 4. Diagnostics: run these and read what they say

Run each command in MATE Terminal on the Spaced machine.

### `gio list network:///`

Lists what the file manager sees. An empty result right after opening the
folder is normal; wait a minute and run it again. If it stays empty but
step 3 works, only browsing (discovery) is broken, not file access.

### mDNS lookups: `getent hosts NAME.local` and `ping NAME.local`

Replace `NAME` with the other computer's name, for example
`getent hosts mynas.local`:

- If an address is printed, mDNS resolution works.
- If nothing is printed, check the two prerequisites below, then suspect
  the network (VPN, guest Wi-Fi isolation, or the other computer not
  publishing mDNS).

### Is the discovery service running?

```
/etc/init.d/avahi-daemon status
```

Expected: `avahi-daemon is running`. If not, start it:

```
sudo /etc/init.d/avahi-daemon start
```

The service is enabled automatically when the package is installed or
upgraded, so a stopped daemon usually means it was stopped manually or
the install did not finish.

### Is name resolution configured?

```
grep hosts /etc/nsswitch.conf
```

Expected: the `hosts:` line contains `mdns4_minimal [NOTFOUND=return]`,
for example:

```
hosts:          files mdns4_minimal [NOTFOUND=return] dns
```

That entry is added automatically when `libnss-mdns` is installed. If it
is missing, reinstall the package (`sudo apt install --reinstall
libnss-mdns`) and check again. Do not edit the file by hand.

### List every mDNS/DNS-SD announcement (optional tool)

`avahi-browse` is **not** installed by default. To get it:

```
sudo apt install avahi-utils
```

Then run:

```
avahi-browse -art
```

It prints every mDNS announcement on the network: computers
(`_workstation._tcp`, `_smb._tcp`), printers (`_ipp._tcp`), and anything
else publishing. Let it run for 30 seconds, then stop it with Ctrl+C.

- Your Windows PC, NAS or Mac shows up here but not in Caja: report it,
  including this output (see step 6).
- Nothing shows up here at all: the announcements never reach this
  machine. Suspect Wi-Fi client isolation, a VPN, or the Windows
  firewall (step 5).

### List a Windows PC's shares directly

```
smbclient -L //IP-ADDRESS -U username
```

Replace `IP-ADDRESS` and `username`. You will be asked for the password,
then see the share list (or an error):

- `NT_STATUS_LOGON_FAILURE`: wrong username or password. For a Microsoft
  account, use the full email address. Windows 11 with only a PIN or
  Hello sign-in still needs the account password here.
- `NT_STATUS_BAD_NETWORK_NAME` or timeout: the address is wrong, the PC
  is asleep, or its firewall blocks SMB.
- `NT_STATUS_ACCESS_DENIED` with guest/anonymous login: expected.
  Windows 11 disables guest access by default; sign in with a real
  account instead.

### Are the file-manager backends alive?

```
ps aux | grep -E "gvfsd-(network|smb|dnssd|wsdd)" | grep -v grep
```

While a Network Servers window is open you should see `gvfsd-network`,
and `gvfsd-smb-browse`, `gvfsd-dnssd` or `gvfsd-wsdd` appear as Caja
asks for each kind of listing. If `gvfsd-network` is missing entirely,
log out and back in and try again.

## 5. Common failures

- **"Network discovery" is off on Windows**, or the Windows network
  profile is **Public**. Both block all announcements and all SMB
  connections. Set the profile to Private and turn discovery on (step 1).
- **Windows firewall.** Third-party firewalls (and hardened Windows
  Firewall rules) can block discovery and SMB even on a Private network.
  If `smbclient -L //IP-ADDRESS` times out while the PC answers `ping`,
  the firewall is the prime suspect.
- **Old NAS that only speaks SMB1.** Modern Samba refuses the SMB1
  protocol because it is insecure and was the WannaCry vector. Do
  **not** turn SMB1 back on. Update the NAS firmware so it offers SMB2
  or newer, then connect directly with `smb://IP-ADDRESS/share`.
- **Microsoft-account logins.** Use the full email address as the SMB
  username and the account password (not the Hello PIN). If sign-in uses
  a passkey only, create a local Windows account for sharing instead.
- **Guest access.** Windows 11 disables unauthenticated guest shares by
  default, and Spaced will not connect to them. Share the folder with a
  named user and sign in (step 3).
- **VPNs.** A VPN routes traffic away from the local network, and mDNS
  announcements never cross it. Disconnect the VPN to browse and open
  local shares; direct `smb://IP-ADDRESS/share` sometimes still works
  over a VPN that routes the LAN, but browsing will not.
- **Guest Wi-Fi / client isolation.** Many guest networks block devices
  from seeing each other. Nothing can fix that except joining the main
  network.

## 6. What to include in a bug report

Report reproducible issues at
<https://github.com/crhy/spaced/issues> with:

1. Spaced version (`cat /etc/os-release`) and whether this is the live
   USB or an installed system.
2. What the other computer is (Windows 10/11, macOS, NAS model, Samba
   server) and how the folder is shared.
3. Which step fails: browsing (step 2), direct connection (step 3), or a
   specific diagnostic (step 4).
4. The exact address typed and the exact error message or dialog text.
5. Output of: `gio list network:///`, `getent hosts NAME.local`,
   `/etc/init.d/avahi-daemon status`, `grep hosts /etc/nsswitch.conf`,
   and, if installed, `avahi-browse -art` (30 seconds) and
   `smbclient -L //IP-ADDRESS -U username`.
