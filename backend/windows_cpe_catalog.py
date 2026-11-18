"""Windows programs the NVD matcher checks: display name and publisher -> NVD vendor:product.

Each product was checked against NVD on 2026-11-18 (CVEs are recorded under that vendor:product). A program no
entry names is counted as not checked. The first entry whose name and publisher match wins (ESR before Firefox).
A product NVD does not split into its parts is left out rather than guessed: the Wazuh agent shares "wazuh:wazuh"
with the Wazuh server, Zoom's client is split over zoom:zoom, zoom:meetings and zoom:workplace, and Microsoft
365 records carry no versions to compare. UltraViewer, Slack and OBS Studio have no CVEs under any NVD name.
``version`` "name" takes the first dotted number in the display name, for installers whose version field is an
MSI build number (Python 3.13.15 reports 3.13.15150.0; OpenVPN 2.7.7 reports 2.7.701).
"""
import re
from typing import Optional, Tuple

# label, NVD vendor:product, display name (whole name, any case), publisher (searched, any case), version from
CATALOG = (
    ("Google Chrome", "google:chrome", r"Google Chrome( (Beta|Dev|Canary))?", r"Google", "field"),
    ("Mozilla Firefox ESR", "mozilla:firefox_esr", r"Mozilla Firefox( [\d.]+)? ESR.*", r"Mozilla", "field"),
    ("Mozilla Firefox", "mozilla:firefox", r"Mozilla Firefox.*", r"Mozilla", "field"),
    ("Mozilla Thunderbird", "mozilla:thunderbird", r"Mozilla Thunderbird.*", r"Mozilla", "field"),
    ("Microsoft Edge", "microsoft:edge_chromium", r"Microsoft Edge", r"Microsoft", "field"),
    ("Visual Studio Code", "microsoft:visual_studio_code", r"Microsoft Visual Studio Code( \(User\))?", r"Microsoft", "field"),
    ("Git", "git-scm:git", r"Git( version [\d.]+)?", r"Git Development Community", "field"),
    ("Node.js", "nodejs:node.js", r"Node\.js", r"Node\.js Foundation|OpenJS", "field"),
    ("Python", "python:python", r"Python \d+\.\d+\.\d+( Core Interpreter)? \((64|32)-bit\)", r"Python Software Foundation", "name"),
    ("MongoDB Server", "mongodb:mongodb", r"MongoDB (Server )?\d[\d.]*( .*)?", r"MongoDB", "field"),
    ("Nmap", "nmap:nmap", r"Nmap [\d.]+", r"Nmap Project|Insecure\.Org", "field"),
    ("Npcap", "nmap:npcap", r"Npcap( OEM)?", r"Nmap Project|Insecure\.Org", "field"),
    ("OpenVPN Connect", "openvpn:connect", r"OpenVPN Connect", r"OpenVPN", "field"),
    ("OpenVPN", "openvpn:openvpn", r"OpenVPN \d.*", r"OpenVPN", "name"),
    ("FortiClient", "fortinet:forticlient", r"FortiClient( VPN)?", r"Fortinet", "field"),
    ("Cisco Secure Client", "cisco:secure_client", r"Cisco Secure Client - AnyConnect VPN", r"Cisco", "field"),
    ("Cisco AnyConnect", "cisco:anyconnect_secure_mobility_client", r"Cisco AnyConnect Secure Mobility Client", r"Cisco", "field"),
    ("XAMPP", "apachefriends:xampp", r"XAMPP", r"Apache Friends", "field"),
    ("7-Zip", "7-zip:7-zip", r"7-Zip [\d.]+.*", r"Igor Pavlov", "field"),
    ("WinRAR", "rarlab:winrar", r"WinRAR [\d.]+.*", r"win\.rar|RARLAB|Alexander Roshal", "field"),
    ("Notepad++", r"notepad-plus-plus:notepad\+\+", r"Notepad\+\+.*", r"Notepad\+\+ Team|Don HO", "field"),
    ("VLC media player", "videolan:vlc_media_player", r"VLC media player", r"VideoLAN", "field"),
    ("Adobe Acrobat Reader", "adobe:acrobat_reader_dc", r"Adobe Acrobat Reader( DC)?( \(64-bit\))?( - .*)?", r"Adobe", "field"),
    ("PuTTY", "putty:putty", r"PuTTY release [\d.]+.*", r"Simon Tatham", "field"),
    ("WinSCP", "winscp:winscp", r"WinSCP [\d.]+", r"Martin Prikryl", "field"),
    ("FileZilla", "filezilla-project:filezilla_client", r"FileZilla( Client)? [\d.]+", r"Tim Kosse", "field"),
    ("Wireshark", "wireshark:wireshark", r"Wireshark [\d.]+.*", r"Wireshark", "field"),
    ("VMware Workstation", "vmware:workstation", r"VMware Workstation", r"VMware|Broadcom", "field"),
    ("VMware Tools", "vmware:tools", r"VMware Tools", r"VMware|Broadcom", "field"),
    ("VirtualBox", "oracle:vm_virtualbox", r"Oracle (VM )?VirtualBox [\d.]+", r"Oracle", "field"),
    ("TeamViewer", "teamviewer:teamviewer", r"TeamViewer( \d+)?( Host)?", r"TeamViewer", "field"),
    ("AnyDesk", "anydesk:anydesk", r"AnyDesk", r"AnyDesk", "field"),
    ("Docker Desktop", "docker:desktop", r"Docker Desktop", r"Docker", "field"),
    ("KeePass", "keepass:keepass", r"KeePass Password Safe [\d.]+", r"Dominik Reichl", "field"),
    ("LibreOffice", "libreoffice:libreoffice", r"LibreOffice [\d.]+.*", r"Document Foundation", "field"),
    ("PostgreSQL", "postgresql:postgresql", r"PostgreSQL \d+", r"PostgreSQL Global Development Group", "field"),
    ("MySQL Server", "oracle:mysql", r"MySQL Server [\d.]+", r"Oracle", "field"),
    ("Foxit PDF Reader", "foxit:pdf_reader", r"Foxit (PDF )?Reader", r"Foxit", "field"),
    ("GIMP", "gimp:gimp", r"GIMP [\d.]+.*", r"GIMP Team", "field"),
    ("Citrix Workspace", "citrix:workspace", r"Citrix Workspace.*", r"Citrix", "field"),
)

_RULES = [(label, product, re.compile(name, re.I), re.compile(publisher, re.I), source)
          for label, product, name, publisher, source in CATALOG]
_DOTTED = re.compile(r"\d+(?:\.\d+)+")


def identify(name: Optional[str], publisher: Optional[str], version: Optional[str]) -> Optional[Tuple[str, str, str]]:
    """(label, NVD vendor:product, version) for a catalogued program with a version, else None."""
    name, publisher = str(name or "").strip(), str(publisher or "").strip()
    for label, product, name_re, publisher_re, source in _RULES:
        if name_re.fullmatch(name) and publisher_re.search(publisher):
            found = _DOTTED.search(name) if source == "name" else None
            got = found.group(0) if found else str(version or "").strip()
            return (label, product, got) if got else None
    return None
