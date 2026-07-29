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

Am 2026-07-29 wurde außerdem ein sicherer, noch nicht ausgeführter
[Werkzeug- und Extraktionsplan](TOOLING_PLAN.md) für `innoextract` und das
bereits installierte, RARv5-fähige `unar` dokumentiert. Installation und
vertiefte Extraktion warten auf gesonderte menschliche Freigabe.

## Statische Tiefenanalyse 2026-07-29

Nach erneuter Bestätigung der Originalprüfsummen wurde das Firmware-RAR mit
`lsar` geprüft und mit `unar` in einen neuen Unterordner extrahiert. Der
Firmware-Updater importiert HID- und SetupAPI-Funktionen und enthält einen
generischen Regex für HID-Gerätepfade mit VID, PID sowie optional MI und COL.
Firmware-/Bootloaderstrings und ARM-artige Daten in `.rdata` stützen die
Hypothese einer eingebetteten Firmware-Nutzlast; Paketfelder und deren Grenzen
sind noch nicht bestätigt. `innoextract` 1.9 konnte den als Inno Setup
`6.4.0.1` erkannten InfoHub-Installer nicht lesen, daher erfolgte dort keine
Tiefenextraktion. Details und Evidenzgrenzen stehen in
[STATIC_SOFTWARE_ANALYSIS.md](STATIC_SOFTWARE_ANALYSIS.md).

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

## Statische Updater-Funktionsanalyse 2026-07-29

### Beobachtet

- Der Updater verwendet `0x400` Byte Nutzinhalt mit zwei internen
  Steuerbytes und bis zu `0x3fe` Datenbytes. Die I/O-Schicht stellt davor ein
  Nullbyte und verwendet einen bis zu `0x401` Byte großen Puffer.
- Das zweite Steuerbyte führt einen 7-Bit-Folgewert; Bit 7 ist im ersten
  Segment gesetzt. Die Leseseite prüft denselben Aufbau.
- Overlapped-I/O wartet höchstens 3000 ms und wird bis zu dreimal versucht.
- Die 201692 Byte lange Region `VA 0x5c21b0..0x5f358c` wird in äußeren
  Blöcken bis `0x8000` Byte übertragen.
- Boot- und Abschlusswarten haben maximal 600 Durchgänge zu 100 ms.

### Abgeleitet

- Die Nutzblockgröße stimmt mit dem 1024-Byte-Output-Report von Interface 1
  überein. Das ist noch keine bestätigte Interfacezuordnung.
- Der 7-Bit-Wert ist funktional eine Segmentfolge.

### Hypothesen

- Das erste Steuerbyte könnte einen Befehl oder Kanal wählen.
- Die DWORDs `0x00100000`, `0x000313dc`, `1` nach dem Transfer könnten
  Zieladresse, Länge und Abschlussflag darstellen.

### Unbekannt

- Konkrete Opcodes, Zielinterface, Antwortsemantik und Prüfsumme.
- Ob MI oder COL zur Zielauswahl dienen.
- Interne Struktur und Architektur der übertragenen Firmwareregion.

Die Belege stehen in den `firmware-updater-*.md`-Berichten unter
`../research/reports/`. Es wurde weder eine Binärdatei ausgeführt noch ein
USB-/HID-Gerät geöffnet.

## InfoHub-Extraktionsplanung 2026-07-29

Die Prüfung eines sicheren, rein statischen Extraktionswegs für den
Inno-Setup-6.4.0.1-Installer ist in
[INFOHUB_EXTRACTION_PLAN.md](INFOHUB_EXTRACTION_PLAN.md) dokumentiert.

## Statische Anfragekandidaten 2026-07-29

Die vertiefte Querverweisanalyse der segmentierten Schreib-/Lesefunktionen und
der direkten `0x400`-Byte-Schreibfunktion ist in
[`../research/reports/firmware-updater-request-candidates.md`](../research/reports/firmware-updater-request-candidates.md)
dokumentiert.

### Beobachtete Fakten

- Alle gefundenen Aufrufe dieser Schreibpfade liegen im zentralen
  Firmware-Upgradeablauf.
- Der leere segmentierte Wert `0x45` erzeugt den bekannten Transportanfang
  `45 81`, gefolgt von Nullen. Der untere HID-Helfer stellt ein zusätzliches
  Nullbyte voran. Direkt davor zeigt die Anwendung „Wiping configuration“.
- Die zugehörige Lesefunktion verlangt Transportbyte 0 gleich `0x45`, wertet
  Byte 1 als Segmentsteuerung aus, kopiert vier Datenbytes ab Offset 2 und
  verlangt beim `0x45`-Pfad einen von null verschiedenen DWORD-Wert.
- `0x86` transportiert Firmwareblöcke; `0x09` transportiert die
  Drei-DWORD-Abschlussstruktur; der leere Wert `0x02` liegt unmittelbar vor
  einer Reenumerationswartephase.
- Direkte Rohpakete beginnen mit `88 01 00 80`; die Variante mit folgendem
  Byte `01` steht vor dem Boot-Warten, die genullte Variante im
  Post-Upgrade-Abschluss.
- Eine konkrete erfolgreiche Antwortkonstante, Versionsauswertung oder
  transportseitige Prüfsumme wurde nicht gefunden.

### Abgeleitete Zusammenhänge

- Die `0x400`-Byte-Transportgröße passt zur bestätigten
  1024-Byte-Outputgröße von Interface 1. Dies ist weiterhin keine direkt
  belegte MI- oder Interfacezuordnung.
- Die vier gelesenen Datenbytes verhalten sich wie ein Rückgabewert oder eine
  Bestätigung; ihre Bedeutung ist nicht belegt.

### Verworfene Hypothesen

- `0x45` wird nicht als Statusabfrage eingestuft. Trotz leerem Anfragekörper
  spricht der direkte Löschkontext gegen einen ungefährlichen Test.
- Die Rohpakete `88 01 00 80 ...` werden nicht als Geräte- oder
  Versionsabfrage eingestuft. Ihre ausschließliche Lage an Boot- und
  Abschlussübergängen macht sie für einen Test ungeeignet.
- Keiner der Werte `0x45`, `0x86`, `0x09` oder `0x02` wird ohne zusätzliche
  Evidenz als allgemeiner Opcode benannt.

### Unbekannte Punkte und Sicherheitsentscheidung

MI/COL des tatsächlich ausgewählten Handles, erfolgreiche Antwortwerte und
eine von Firmwareaktionen unabhängige Status-/Versionsabfrage bleiben
unbekannt. Daher wurde kein sicherer Anfragekandidat bestätigt. Ein
kontrollierter Einzeltest ist auf diesem Stand nicht vertretbar. Es wurde
nichts an ein USB- oder HID-Gerät gesendet.

## Extrahierte Gerätefirmware 2026-07-29

Die bytegenaue Kopie der vom Windows-Updater übertragenen Region liegt unter
`../research/extracted/device-firmware-v51-static/device-firmware-v51.bin`.
Die vertiefte statische Auswertung und Rohbefunde stehen in
[`../research/reports/device-firmware-static-analysis.md`](../research/reports/device-firmware-static-analysis.md).

### Beobachtete Fakten

- Dateioffset `0x1c15b0..0x1f298c` (Ende exklusiv), Länge `0x313dc` = 201692
  Byte; SHA-256 der Kopie:
  `c4679ec340fc5edd3dea960ee027281cf6bd81cbbf347afb40e0d0b4f40aeb9f`.
- Der Anfang enthält ARM-Little-Endian-Vektordaten; weitere Bereiche enthalten
  ARM- und Thumb-/Interworking-artige Muster.
- `USBR_GET_DESCRIPTOR pkt.wLength = %d` und ein USB-Request-Dispatcher mit
  Vergleichswerten `1, 2, 3, 6, 7, 0x21, 0x22` sind sichtbar.
- Ein gerätespezifischer Dispatcher vergleicht unter anderem `0x18..0x1f`,
  `0x80..0x87`, `0xfd..0xff`; ein weiterer vergleicht `0x03`, `0x06`,
  `0x38` und `0x3b`.
- Strings belegen `LCM_Init`, emWin, SPI-Flash, Boot-/Config-Pfade und eine
  JPG-Dateireferenz. PNG-, JPEG- und GIF-Signaturen wurden nicht gefunden.

### Ableitungen und Grenzen

Mehrere `0x0140`-Werte und der externe Dateiname `320x320` stützen eine
Auflösungshypothese; Breite, Höhe, Pixelformat, Interfacezuordnung und normale
LCD-Befehlsbedeutungen bleiben offen. Die bekannten HID-Deskriptoren und die
Reportgrößen 16/440/1024 wurden in der Nutzlast nicht direkt bestätigt.

Die Updaterwerte `0x45`, `0x86`, `0x09`, `0x02` und `88 01 00 80 ...` bleiben
klar vom gefährlichen Boot-/Upgradeablauf getrennt. Es wurde nichts ausgeführt,
kein USB-/HID-Gerät geöffnet und nichts an die AIO gesendet.

## Statische Ghidra-Analyse 2026-07-29

Ghidra 12.1 wurde mit dem portablen Temurin JDK 21.0.12+8 verwendet. Die
Firmware wurde als Raw Binary mit `ARM:LE:32:v5t:default` und Loader-Basis
`0x00100000` in ein getrenntes Projekt importiert. Der geladene Bereich ist
`0x00100000..0x001313db`. Details und reproduzierbare Parameter stehen in
[GHIDRA_ANALYSIS_PLAN.md](GHIDRA_ANALYSIS_PLAN.md); Firmwarekarte und Matrix
stehen in:

- `../research/reports/ghidra-firmware-map.md`
- `../research/reports/dispatcher-handler-matrix.tsv`

### Beobachtete Fakten

- Ghidra dekodiert den Start konsistent als 32-Bit ARM Little Endian und
  erkannte 694 Funktionen.
- `usb_event_dispatch_candidate` bei `0x0012ced0` ruft den
  USB-Setup-Dispatcher bei `0x0012c12c` direkt auf.
- Die Vergleiche `0x01`, `0x02`, `0x03`, `0x06`, `0x07`, `0x21`, `0x22`
  liegen innerhalb von `bRequest=0x06` und betreffen das High-Byte von
  `wValue`. Sie sind Descriptor-Typen, keine Geräteprotokollbefehle.
- Der Protokolltask bei `0x00129d84` registriert Geräte- und
  Transportdispatcher als Callbacks.
- Der 440-Byte-Empfangspfad verwendet ein 4-Byte-Steuerwort und `0x1b4` =
  436 Nutzbytes. Der Antwortbauer erzeugt ebenfalls exakt `0x1b8` = 440
  Byte.
- Ein zweiter Empfänger verwendet ein 4-Byte-Steuerwort und `0x3fc` = 1020
  Nutzbytes, insgesamt 1024 Byte.
- Im Steuerwort sind Byte 0 der Befehlswert, Bit 31 das Kennzeichen des
  ersten Pakets und Bits 8..30 Paketanzahl beziehungsweise Segmentindex.
- Im Gerätedispatcher ist `0x87` ein Zwei-Byte-Antwortpfad mit dem konstanten
  Wert `0x0051`. `0x1e` liest ein Halbwort; `0x80..0x85` geben kurze globale
  oder strukturbasierte Puffer zurück.
- `0x88` wird im Transportdispatcher gesondert behandelt und führt über
  `0x00128bc0` zu SPI-Lesen sowie bedingtem SPI-Schreiben im Bereich
  `0x21000`.

### Belastbare Ableitungen

Das 440-Byte-Format korreliert exakt mit dem bekannten 440-Byte-HID-Report,
das 1024-Byte-Format mit dem bekannten 1024-Byte-Outputreport. Ohne direkte
Xref auf Reportdeskriptor und Endpoint ist dies noch keine bestätigte MI- oder
Interfacezuordnung.

Für eine einpaketige leere `0x87`-Anfrage ergibt sich statisch als
Paketkandidat:

```text
87 01 00 80 00 ... 00     (440 Byte)
```

Die vom Antwortbauer erwartbare Struktur ist:

```text
87 01 00 80 51 00 00 ... 00     (440 Byte)
```

Belegt sind Headeralgorithmus, Befehl, Antwortkonstante und Längen. Nicht
belegt sind eine mögliche Host-seitige Report-ID, das konkrete Interface und
die vollständige indirekte Endpoint-/Callbackkette. `0x87` bleibt deshalb ein
statischer Versionskandidat, keine Sendefreigabe.

### Hypothesen

- `0x1e` könnte Status oder Diagnose liefern.
- `0x80..0x85` könnten Status-, Identitäts-, Display- oder
  Konfigurationswerte liefern.
- Der 1024-Byte-Pfad könnte Daten oder Bildinhalte transportieren.

Diese Bedeutungen sind nicht durch Symbole oder vollständige Datenflüsse
bestätigt.

### Ausgeschlossene Kandidaten

- `0x45`: im Updater Konfigurationslöschung.
- `0x86`: im Updater Firmwareblocktransfer; mögliche modusabhängige Semantik.
- `0x09`: im normalen Dispatcher zustands-/displayverändernd und im Updater
  Completion-Flag.
- `0x02`: im Updater Abschluss/Reenumeration, trotz einfachem normalem
  Dispatcherzweig.
- `88 01 00 80 ...`: Befehl `0x88` mit bestätigtem SPI-Lese-/Schreibpfad.
- `0x1f` und `0xff`: Boot-/indirekte Callbackpfade mit unvertretbar offenem
  Risiko.

### Unbekannte Punkte und Sicherheitsentscheidung

MI, Endpoint, Report-ID, die globalen Bedeutungen der kurzen Antwortwerte und
mehrere indirekte Callbackziele sind offen. Die Ghidra-Call-Graph-Suche konnte
LCM/emWin, Boot-/JPG- und SPI-String-Eigentümer wegen indirekter Aufrufe nicht
lückenlos mit den Dispatchern verbinden.

Ein kontrollierter Einzeltest ist auf diesem Stand nicht empfohlen. Es wurde
keine Firmware ausgeführt oder emuliert, kein USB-/HID-Gerät geöffnet und
nichts an die AIO gesendet.
