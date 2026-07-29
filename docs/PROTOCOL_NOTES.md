# Protokollnotizen

Dieses Dokument ist das strukturierte Forschungstagebuch für das bislang
undokumentierte USB-/HID-Protokoll der ASUS TUF Gaming LC III 360 ARGB LCD.

Es dokumentiert Beobachtungen reproduzierbar und trennt sie von Hypothesen und
bestätigten Erkenntnissen. Originaldaten liegen in `../captures/` und werden
nicht überschrieben. Sicherheitsregeln und Freigabegrenzen stehen in
[SAFETY.md](SAFETY.md).

## Dokumentationskonvention

Jeder neue Eintrag soll nach Möglichkeit enthalten:

- Datum und Uhrzeit einschließlich Zeitzone,
- Betriebssystem, Kernel und relevante Werkzeugversionen,
- physischer Aufbau und Gerätezustand,
- Datenquelle oder Pfad zur unveränderten Originaldatei,
- verwendete Schnittstelle und Richtung,
- Beobachtung ohne Interpretation,
- daraus abgeleitete Hypothese,
- Methode und Ergebnis einer späteren Überprüfung,
- Status: `beobachtet`, `Hypothese`, `bestätigt` oder `widerlegt`.

Hexadezimale Daten werden byteweise notiert. Offsets beginnen bei null. Die
Richtung wird aus Sicht des Hosts als `Host → Gerät` oder `Gerät → Host`
bezeichnet. Ein Eintrag darf nur als bestätigt gelten, wenn er durch
reproduzierbare Beobachtung oder eine maßgebliche Spezifikation belegt ist.

## Gerätekontext

| Merkmal | Stand | Evidenzstatus |
| --- | --- | --- |
| Gerät | ASUS TUF Gaming LC III 360 ARGB LCD | bekannt |
| Vendor-ID | `0b05` | bestätigt |
| Product-ID | `1c7b` | bestätigt |
| Geräteklasse unter Linux | USB HID | bestätigt |
| Anzahl HID-Schnittstellen | 2 | bestätigt |
| Aktuelle HID-Raw-Pfade | `/dev/hidraw3`, `/dev/hidraw4` | beobachtet am 2026-07-29, nicht stabil |
| Frühere HID-Raw-Pfade | `/dev/hidraw7`, `/dev/hidraw8` | frühere Beobachtung, nicht stabil |

Die aktuelle Zuordnung zu den Interface-Nummern ist über udev- und
sysfs-Metadaten bestätigt. Die Funktion der Interfaces ist weiterhin offen.

## Erfassung 2026-07-29

### Datum und Systemzustand

| Merkmal | Beobachteter Wert |
| --- | --- |
| Zeitpunkt | `2026-07-29T00:35:22+02:00` |
| Zeitzone | Europe/Berlin, UTC+02:00 |
| Hostsystem | Ultramarine Linux 44 (Plasma Edition) |
| Kernel | `7.1.4-204.fc44.x86_64` |
| Architektur | `x86_64` |
| USB-Ort zum Erfassungszeitpunkt | Bus 001, Gerät 003, Port 008 |
| USB-Geschwindigkeit | High Speed, 480 Mbit/s |
| Gerätezustand | verbunden und durch `usbhid` gebunden |
| Analysemodus | ausschließlich passive Deskriptor- und Metadatenabfrage |

### Werkzeuge

| Befehl | Status/Version |
| --- | --- |
| `lsusb` | vorhanden, usbutils 019 |
| `usbhid-dump` | vorhanden, usbutils 019 |
| `udevadm` | vorhanden, systemd/udev 259 |
| `sensors` | vorhanden, lm-sensors 3.6.0 |

`sensors` wurde in diesem Ticket nur auf Verfügbarkeit und Version geprüft.
Sensorwerte waren nicht Gegenstand der USB-/HID-Bestandsaufnahme.

### Verwendete Befehle

Die folgenden lesenden Befehle wurden verwendet:

```text
lsusb -d 0b05:1c7b
lsusb -v -d 0b05:1c7b
lsusb -t
udevadm info --query=property --path=/sys/class/hidraw/<ermitteltes Gerät>
od -An -v -tx1 /sys/class/hidraw/<ermitteltes Gerät>/device/report_descriptor
usbhid-dump -m 0b05:1c7b -e descriptor
```

Der `usbhid-dump`-Aufruf wurde ohne Deskriptor-Ausgabe beendet, weil der aktuelle
Benutzer nicht die von libusb verlangten Zugriffsrechte auf
`/dev/bus/usb/001/003` besitzt. Es wurden dabei keine Reports gesendet oder
gesetzt. Die bereits vom Kernel gelesenen Report-Deskriptoren waren unter sysfs
weltweit lesbar und wurden deshalb dort passiv erfasst.

## USB-Deskriptoren

### Beobachtungen

- USB-Version `1.10`, High Speed mit 480 Mbit/s.
- EP0 besitzt eine maximale Paketgröße von 64 Byte.
- Geräteversion `0.49`.
- Herstellerstring `ASUS Tek`.
- Produktstring `TUF GAMING LC III 360 ARGB LCD`.
- Seriennummer `A247392SS000000`.
- Genau eine Konfiguration mit Wert 1.
- Bus-powered, deklarierte maximale Stromaufnahme 100 mA.
- Zwei Interfaces, jeweils HID-Klasse 3, Subklasse 0, Protokoll 0 und Alternate
  Setting 0.
- Beide HID-Deskriptoren deklarieren HID-Version 1.10 und einen 29 Byte langen
  Report-Deskriptor.
- `lsusb -v` meldete fehlenden direkten Gerätezugriff. Standard-, Konfigurations-
  und Stringinformationen wurden ausgegeben; die Report-Deskriptoren waren in
  dieser Ausgabe nicht verfügbar.

### Originaldaten

| Datum | Datei | Werkzeug/Befehl | Prüfsumme | Anmerkung |
| --- | --- | --- | --- | --- |
| 2026-07-29 | `../captures/usb-descriptor-0b05-1c7b.txt` | `lsusb -v -d 0b05:1c7b` | `e0cd9a4e947bfbed8218f4bd57551d63652ef5cf645cf2228960c00d52a4a55d` | Ausgabe meldet eingeschränkten direkten Gerätezugriff |
| 2026-07-29 | `../captures/hid-report-descriptors-0b05-1c7b.txt` | sysfs `report_descriptor`, Ausgabe mit `od` | `899262a7bd73808361c39b3faebb782ac7a111353f85d971a3f35f305cc1af23` | Beide 29-Byte-Deskriptoren |
| 2026-07-29 | `../captures/hidraw-udev-0b05-1c7b.txt` | `udevadm info --query=property` und sysfs | `ebc7013bc39b656894acdb85f2b9aee311db104cc64fdd7d0cbb9ab09273d350` | Aktuelle Zuordnung beider Interfaces |
| 2026-07-29 | `../captures/usb-topology.txt` | `lsusb -t` | `7118b99728c74648274d5aa7dd26b70724f2e43c02b173c1bf24aa38b524c357` | Vollständige Topologie zum Erfassungszeitpunkt |

## HID-Report-Deskriptoren

Für jede HID-Schnittstelle separat erfassen:

- Interface-Nummer und alternates Setting,
- Report-Deskriptor als unveränderte Binärdatei,
- Report-IDs,
- Input-, Output- und Feature-Reports,
- Report-Größen in Bits und Bytes,
- Usage Page und Usages,
- logische und physische Wertebereiche,
- Anzahl, Flags und Struktur der Felder.

### Schnittstelle 1

| Eigenschaft | Wert |
| --- | --- |
| Interface-Nummer | 0 |
| Funktion | unbekannt |
| Usage Page | `0xff06` (herstellerspezifisch) |
| Usage | `0x01` |
| Collection | Application |
| Logischer Wertebereich | 0 bis 255 |
| Report-IDs | keine im Deskriptor deklariert |
| Input-Report-Größe | 440 Felder × 8 Bit = 440 Byte |
| Output-Report-Größe | 440 Felder × 8 Bit = 440 Byte |
| Feature Reports | keine im Deskriptor deklariert |
| Originaldeskriptor | `../captures/hid-report-descriptors-0b05-1c7b.txt` |

### Schnittstelle 2

| Eigenschaft | Wert |
| --- | --- |
| Interface-Nummer | 1 |
| Funktion | unbekannt |
| Usage Page | `0xff06` (herstellerspezifisch) |
| Usage | `0x01` |
| Collection | Application |
| Logischer Wertebereich | 0 bis 255 |
| Report-IDs | keine im Deskriptor deklariert |
| Input-Report-Größe | 16 Felder × 8 Bit = 16 Byte |
| Output-Report-Größe | 1024 Felder × 8 Bit = 1024 Byte |
| Feature Reports | keine im Deskriptor deklariert |
| Originaldeskriptor | `../captures/hid-report-descriptors-0b05-1c7b.txt` |

## Interfaces und Endpunkte

| Interface | Alternate Setting | aktueller HID-Raw-Pfad | Endpunkt | Richtung | Transferart | Max. Paketgröße | Intervall | Funktion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | `/dev/hidraw3` | `0x01` | OUT | Interrupt | 440 Byte | 1 | unbekannt |
| 0 | 0 | `/dev/hidraw3` | `0x82` | IN | Interrupt | 440 Byte | 1 | unbekannt |
| 1 | 0 | `/dev/hidraw4` | `0x03` | OUT | Interrupt | 1024 Byte | 1 | unbekannt |
| 1 | 0 | `/dev/hidraw4` | `0x84` | IN | Interrupt | 16 Byte | 1 | unbekannt |

Die HID-Raw-Pfade dienen nur zur Zuordnung einer konkreten Beobachtung. Sie sind
keine Geräteidentität und dürfen nicht als dauerhafte Schnittstellenbezeichnung
verwendet werden.

### Aktuelle hidraw- und udev-Zuordnung

| Merkmal | Interface 0 | Interface 1 |
| --- | --- | --- |
| aktueller Gerätepfad | `/dev/hidraw3` | `/dev/hidraw4` |
| sysfs-Pfad | `/sys/devices/pci0000:00/0000:00:02.1/0000:05:00.0/0000:06:0c.0/0000:0c:00.0/usb1/1-8/1-8:1.0/0003:0B05:1C7B.0004/hidraw/hidraw3` | `/sys/devices/pci0000:00/0000:00:02.1/0000:05:00.0/0000:06:0c.0/0000:0c:00.0/usb1/1-8/1-8:1.1/0003:0B05:1C7B.0005/hidraw/hidraw4` |
| Vendor-ID | `0b05` | `0b05` |
| Product-ID | `1c7b` | `1c7b` |
| Hersteller | `ASUS Tek` | `ASUS Tek` |
| Produkt | `TUF GAMING LC III 360 ARGB LCD` | `TUF GAMING LC III 360 ARGB LCD` |
| Seriennummer | `A247392SS000000` | `A247392SS000000` |
| USB-Treiber laut udev | `usbhid` | `usbhid` |
| gebundener HID-Treiber in sysfs | `hid-generic` | `hid-generic` |
| stabiler udev-Link | ohne Interface-Suffix | mit Suffix `-if01-hidraw` |

Die Auswahl erfolgte durch Abgleich der udev-Eigenschaften `ID_VENDOR_ID=0b05`
und `ID_MODEL_ID=1c7b` über alle Einträge in `/sys/class/hidraw`. Die Nummern 3
und 4 waren kein Suchkriterium.

## Beobachtete Pakete

Noch keine Pakete dokumentiert.

Neue Beobachtungen werden in folgender Form ergänzt:

### Paketbeobachtung: `<kurze Kennung>`

| Feld | Wert |
| --- | --- |
| Datum/Zeit | `<ISO-8601 mit Zeitzone>` |
| Originalmitschnitt | `../captures/<datei>` |
| Interface/Endpunkt | `<Wert>` |
| Richtung | `<Host → Gerät oder Gerät → Host>` |
| Transfer-/Report-Typ | `<Wert>` |
| Report-ID | `<Wert oder nicht vorhanden>` |
| Länge | `<Byte>` |
| Gerätezustand | `<Wert>` |
| Auslösende Aktion | `<Wert>` |
| Wiederholungen | `<Anzahl>` |
| Status | `beobachtet` |

```text
Offset  Hexadezimale Bytes
0000    ...
```

**Beobachtung:** `<nur direkt Sichtbares>`

**Mögliche Bedeutung:** `<Interpretation, zunächst als Hypothese>`

**Nächste passive Prüfung:** `<reproduzierbare Prüfung ohne Geräte-Schreibzugriff>`

## Hypothesen

| ID | Hypothese | Grundlage | Gegenbeobachtungen | Geplante passive Prüfung | Status |
| --- | --- | --- | --- | --- | --- |
| H-001 | Interface 1 könnte wegen seines 1024-Byte-Output-Reports für umfangreichere LCD- oder Bilddaten vorgesehen sein. | Sein Output-Report ist größer als der 440-Byte-Report von Interface 0. | Es wurde noch kein Verkehr beobachtet; Reportgröße belegt keine Funktion. | Legitimen Referenzverkehr beider Interfaces passiv vergleichen. | offen |
| H-002 | Interface 0 könnte eine symmetrische Anfrage-/Antwortstruktur verwenden. | Input und Output sind jeweils 440 Byte groß. | Es wurde noch kein Verkehr beobachtet; gleiche Größen belegen keine Semantik. | Legitimen Referenzverkehr passiv erfassen und Transaktionen zeitlich zuordnen. | offen |

Hypothesen sind keine Implementierungsvorgaben. Sie werden bei neuen
Beobachtungen aktualisiert, bestätigt oder ausdrücklich widerlegt.

## Bestätigte Erkenntnisse

| ID | Erkenntnis | Evidenz | Bestätigt am |
| --- | --- | --- | --- |
| C-001 | Das Zielgerät verwendet USB-ID `0b05:1c7b`. | Linux-Geräteerkennung laut bisherigem Projektstand. | vor Beginn dieses Tagebuchs |
| C-002 | Das Gerät stellt die HID-Interfaces 0 und 1 mit jeweils zwei Interrupt-Endpunkten bereit. | USB-Deskriptor und USB-Topologie. | 2026-07-29 |
| C-003 | `/dev/hidrawX`-Nummern sind keine stabile Gerätekennung. | Dynamische Linux-Gerätenummerierung. | vor Beginn dieses Tagebuchs |
| C-004 | Interface 0 hat 440-Byte-Input- und 440-Byte-Output-Reports ohne Report-ID. | 29-Byte-HID-Report-Deskriptor aus sysfs. | 2026-07-29 |
| C-005 | Interface 1 hat einen 16-Byte-Input- und einen 1024-Byte-Output-Report ohne Report-ID. | 29-Byte-HID-Report-Deskriptor aus sysfs. | 2026-07-29 |
| C-006 | Beide Interfaces verwenden die herstellerspezifische Usage Page `0xff06` und Usage `0x01`. | HID-Report-Deskriptoren aus sysfs. | 2026-07-29 |
| C-007 | Aktuell sind Interface 0 und 1 `/dev/hidraw3` und `/dev/hidraw4` zugeordnet. | udev-Metadaten, gefiltert nach VID/PID. | 2026-07-29 |

Die Reportgrößen sind bestätigt. Inhalt, Felder und Befehlssemantik sind noch
nicht bekannt.

## Offene Fragen

### USB und HID

- Warum meldet das Gerät USB 1.10, arbeitet aber mit High Speed?
- Welche Bedeutung haben Usage Page `0xff06` und Usage `0x01` konkret für
  dieses Gerät?
- Gibt es Feature Reports oder Control Transfers außerhalb regulärer
  Interrupt-Transfers?
- Ist die Seriennummer über mehrere Geräteinstanzen hinweg eindeutig und
  dauerhaft stabil?

### LCD-Protokoll

- Welche Schnittstelle steuert das LCD?
- Welche Initialisierungs- und Statussequenzen sind erforderlich?
- Welche Displayauflösung, Orientierung und Pixelformate werden verwendet?
- Wie werden große Bilddaten segmentiert, nummeriert und bestätigt?
- Gibt es Prüfsummen, Längenfelder, Sequenznummern, Timeouts oder Keepalives?
- Welche Grenzen gelten für Bildrate, Animationsgröße und Übertragungsrate?

### Sensoranzeige

- Erwartet das Gerät fertige Bildframes oder strukturierte Sensordaten?
- Erfolgen Textlayout und Animation vollständig auf dem Host?
- Welche Aktualisierungsrate ist sinnvoll und geräteschonend?

### Sicherer Übergang zu Schreibtests

- Sind alle Reportgrößen und zulässigen Report-IDs dokumentiert?
- Ist die Befehlsstruktur durch wiederholten legitimen Referenzverkehr belegt?
- Sind erwartete Antworten, Fehlerfälle und Abbruchbedingungen bekannt?
- Existiert ein eng begrenzter Testplan mit Wiederherstellungsweg?
- Wurde der konkrete Schreibtest ausdrücklich freigegeben?

Solange diese Voraussetzungen nicht erfüllt sind, bleibt das Projekt bei
passiver Analyse.

## Verweis auf statische ASUS-Softwareanalyse

Am 2026-07-29 wurden die offiziell angebotene ASUS InfoHub Software
`1.0.0.15` und Firmware `51` ausschließlich statisch untersucht. Ergebnisse,
Prüfsummen, Evidenzgrenzen und offene Punkte stehen in
[STATIC_SOFTWARE_ANALYSIS.md](STATIC_SOFTWARE_ANALYSIS.md). Die Analyse ergab
bislang keine belastbare Funktionszuordnung der beiden HID-Interfaces und keine
bestätigten Paketfelder.

## Grenzen und nächste passive Schritte

- `lsusb -v` konnte das Gerät ohne zusätzliche Zugriffsrechte nicht öffnen und
  kennzeichnete Teile der Ausgabe als möglicherweise unvollständig.
- `usbhid-dump` ist installiert, konnte den Deskriptor aber ohne Schreibrecht
  auf den USB-Geräteknoten nicht öffnen. Diese libusb-Anforderung ist eine
  Berechtigungsfrage; es wurde kein `sudo` eingesetzt.
- Die Report-Deskriptoren konnten dennoch vollständig und passiv über sysfs
  gelesen werden; beide Längen stimmen mit den USB-HID-Deskriptoren überein.
- Es wurden keine Interrupt-Datenströme oder Referenzpakete aufgezeichnet.
- Für eine Wiederholung mit `usbhid-dump` wären eine menschlich freigegebene,
  temporäre Berechtigungsregel oder ein bewusst mit `sudo` ausgeführter,
  ausschließlich auf Deskriptoren begrenzter Aufruf erforderlich.
- Der nächste weiterhin passive Erkenntnisschritt ist ein autorisierter
  Mitschnitt legitimen Referenzverkehrs. Ohne solchen Verkehr bleibt die
  Funktionszuordnung der beiden Interfaces unbekannt.
