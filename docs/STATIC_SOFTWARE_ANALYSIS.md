# Statische Analyse offizieller ASUS-Software und -Firmware

Stand: 2026-07-29, Europe/Berlin. Die Untersuchung erfolgte ausschließlich
statisch unter Linux. Keine der heruntergeladenen oder extrahierten Dateien
wurde ausgeführt.

## Offizielle Quellen und Downloads

Offizielle Produkt-Supportseite:

<https://www.asus.com/motherboards-components/cooling/tuf-gaming/tuf-gaming-lc-iii-360-argb-lcd/helpdesk_download?model2Name=TUF-Gaming-LC-III-360-ARGB-LCD>

Offizielle Firmwareseite:

<https://www.asus.com/motherboards-components/cooling/tuf-gaming/tuf-gaming-lc-iii-360-argb-lcd/helpdesk_bios?model2Name=TUF-Gaming-LC-III-360-ARGB-LCD>

Am Untersuchungstag waren für das Zielgerät folgende einschlägige Versionen
sichtbar:

| Paket | Version | Veröffentlichung | ASUS-Angabe | Originaldatei |
| --- | --- | --- | --- | --- |
| ASUS InfoHub Software TUF GAMING, Windows 10/11 64-bit | `1.0.0.15` | 2026-01-19 | 85,82 MB | `ASUS_InfoHub_Software_TUF_GAMING_LC_III_360_ARGB_LCD_v1.0.0.15.zip` |
| ASUS InfoHub Firmware TUF GAMING, Windows 10/11 64-bit | `51` | 2025-07-10 | 1,27 MB | `ASUS_InfoHub_Firmware_TUF_GAMING_LC_III_360_ARGB_LCD_v51.rar` |

Die Downloadpfade liegen auf dem offiziellen ASUS-CDN
`dlcdnets.asus.com` unter
`/pub/ASUS/Accessory/Cooling/TUF_GAMING_LC_III_360_ARGB_LCD/`.
Die sichtbaren Supportseiten lieferten nur diese jeweils aktuelle einschlägige
InfoHub- und Firmwareversion; ältere Versionen wurden dort nicht angeboten.
Armoury Crate wurde nicht heruntergeladen, da es kein gerätespezifisches
InfoHub-Paket ist und der Auftrag die einschlägige Herstellerlösung betrifft.

## Prüfsummen und Dateiinventar

| Datei | Bytes | Typ | SHA-256 |
| --- | ---: | --- | --- |
| `ASUS_InfoHub_Software_TUF_GAMING_LC_III_360_ARGB_LCD_v1.0.0.15.zip` | 89.990.251 | ZIP (`PK`-Signatur; `file` meldet nur `data`) | `0d7124d700b07d1f49315d77aa15473f01c42c1492f2e8cece845f19c32d2a21` |
| `ASUS_InfoHub_Firmware_TUF_GAMING_LC_III_360_ARGB_LCD_v51.rar` | 1.331.080 | RAR5 | `267b1477374d28fca01be92b2ff11748591560d30c1a1392bf9d06493a43bfd8` |
| extrahiertes `ASUS-InfoHub-TUF-1.0.0.15.exe` | 90.476.632 | PE32 GUI, Intel i386, 11 Sektionen | `b7d867a13e8918be09675883330a801c6e3dfff2568afd32c3c18193e0ef9164` |

Beide Downloadprüfsummen stimmen bytegenau mit den auf ASUS veröffentlichten
SHA-256-Werten überein. Maschinenlesbare Metadaten stehen in
`../research/manifests/asus-downloads.tsv` und
`../research/manifests/extracted-files.tsv`.

Das ZIP enthielt genau eine Datei. Vor dem Entpacken wurden Namen mit absoluten
Unix-Pfaden, Windows-Laufwerkpräfixen oder `..`-Komponenten ausgeschlossen.
Extrahiert wurde mit Überschreibschutz (`unzip -n`) ausschließlich nach
`research/extracted/infohub-v1.0.0.15/`.

In der ersten Analysestufe konnte das RAR mit 7-Zip nicht geöffnet werden.
Am 2026-07-29 wurde es nach erneuter Prüfsummenprüfung mit dem inzwischen
vorhandenen `lsar` 1.10.7 vollständig aufgelistet. Es enthielt genau eine
reguläre, relative Datei und keine sichtbare Pfadtraversierung oder Links.
Anschließend wurde sie mit `unar` 1.10.7 und Überschreibschutz ausschließlich
nach `research/extracted/firmware-v51/` extrahiert:

| Datei | Bytes | Typ | SHA-256 |
| --- | ---: | --- | --- |
| `WW11_320x320_2.8inch_v51_TUF_20250626.exe` | 3.558.320 | PE32 GUI, Intel i386, 6 Sektionen | `037b581f2bd5bc95db7db1a6f68d25d7ac2c19afe9fa09888851f0d6e448fb65` |

Die InfoHub-Tiefenextraktion blieb dagegen blockiert: `innoextract` 1.9
erkennt Inno Setup `6.4.0.1`, unterstützt laut eigener Versionsausgabe nur bis
`6.0.5` und bricht bereits beim Lesen der Setup-Header ab. Es wurde keine
unsichere Ersatzextraktion versucht.

## Bestätigte USB-/HID-Hinweise

Im InfoHub-Installer wurden weiterhin **keine belastbaren direkten Treffer**
für folgende Kennungen gefunden:

- `0b05`, `1c7b`, `VID_0B05`, `PID_1C7B`
- `MI_00`, `MI_01`
- Usage Page `0xff06`
- HID-/WinUSB-API-Importe, die dem eigentlichen InfoHub-Gerätecode zugeordnet
  werden könnten
- belegbare Reportlängen, Paketheader, Opcodes oder Prüfsummenalgorithmen

Der untersuchte PE-Stub ist ein Inno-Setup-Installer. Seine direkten Imports
stammen aus `kernel32.dll`, `comctl32.dll`, `user32.dll`, `oleaut32.dll` und
`advapi32.dll`. Das belegt nur Installerfunktionalität. Die eigentlichen
InfoHub-Nutzdateien bleiben im Inno-Datenbereich komprimiert, weil die
vorhandene `innoextract`-Version das verwendete Inno-Setup-Format nicht
unterstützt.

Der extrahierte Firmware-Updater liefert dagegen direkte statische Hinweise:

- Imports aus `HID.DLL`: `HidD_GetAttributes`,
  `HidD_GetPreparsedData`, `HidP_GetCaps` und
  `HidD_FreePreparsedData`.
- Imports aus `SETUPAPI.dll`: `SetupDiGetClassDevsW`,
  `SetupDiGetDeviceInterfaceDetailW`, `SetupDiEnumDeviceInterfaces` und
  `SetupDiDestroyDeviceInfoList`.
- Ein UTF-16-Regex erkennt HID-Gerätepfade der Form
  `hid#vid_<VID>&pid_<PID>` mit optionalen `rev`, `mi` und `col`-Teilen.
- Diagnoseformate nennen `open dev`, `write ok`, `write abort`, `read ok`,
  `read abort`, `usb writex` und `usb readex`.

Damit ist bestätigt, dass der Updater HID-Geräte über SetupAPI aufzählt,
HID-Eigenschaften beziehungsweise Fähigkeiten abfragt und Lese-/Schreibpfade
besitzt. Nicht bestätigt sind die konkrete VID/PID-Konstante, das verwendete
Interface oder die Bedeutung übertragener Daten. `WinUSB`- und
`libusb`-Importe wurden nicht gefunden.

Numerische Vorkommen von `440` und `1024` in der `objdump`-Ausgabe liegen unter
anderem in PE-Relocationstabellen und sind **kein** Beleg für Reportgrößen.
Zufällige kurze Zeichenfolgen in komprimierten Daten wurden ebenfalls nicht als
semantische Treffer gewertet.

## Hinweise auf Paket- und Bildformate

Der offizielle ASUS-Produkttext nennt für das 2,8-Zoll-LCD anpassbare Inhalte,
GIFs und MP4-Videoclips. Dies bestätigt unterstützte Benutzermedien auf
Produktebene, aber weder das USB-Transportformat noch eine interne
Frame-Codierung.

Der im RAR5-Header statisch sichtbare Name
`WW11_320x320_2.8inch_v51_TUF_20250626.exe` enthält `320x320`, `2.8inch`,
`v51` und das Datum `20250626`. Direkt beobachtet ist nur dieser Dateiname.
Die Interpretation als Displayauflösung und Builddatum ist plausibel, bleibt
aber eine Ableitung aus der Benennung.

Der Firmware-Updater enthält libpng/APNG-, zlib-, Skia- und GDI+-Bestandteile
sowie JPEG-, GIF- und PNG-bezogene Decoder- beziehungsweise Fehlerstrings.
GDI+-Imports zur Ermittlung und Auswahl von Frames sind vorhanden. Dies belegt
Bildverarbeitung im Updater, aber nicht das Transportformat des Zielgeräts.
Ein belastbarer MP4-Verarbeitungshinweis wurde dort nicht gefunden.

Weiterhin fehlen belastbare Hinweise auf Chunkgrößen, Sequenznummern,
Paketheader, Rohpixelformate oder USB-seitige Bildsegmentierung.

## Firmwarefunde

- Offizielles Paket: Firmwareversion 51, veröffentlicht am 2025-07-10.
- ASUS-SHA-256 und lokal berechneter SHA-256 stimmen überein.
- Das RAR5 enthält genau die Datei
  `WW11_320x320_2.8inch_v51_TUF_20250626.exe`; RAR-Metadaten nennen
  3.558.320 Byte und CRC32 `0xa588501e`.
- Der Updater hat `FileVersion 1.0.0.1` und `ProductVersion 0.8.5.0`.
- Strings wie `SEGGER emWin V5481110`, `lcd_boot_proc`, `SPI flash id`,
  `N9H20 UDC Library`, `USBR_GET_DESCRIPTOR`, `c:\syst\boot` und
  `c:\syst\wapper.jpg` sowie ARM-artige Instruktionsdaten liegen in seiner
  `.rdata`-Sektion. Dies ist ein starker Hinweis auf eingebettete
  Gerätefirmware; deren exakte Grenzen wurden nicht bestätigt und deshalb
  nicht herausgeschnitten.
- Die Zeichenfolge `A247392SS000000` stimmt mit der zuvor am Gerät
  beobachteten Seriennummer überein. Ob sie ein Defaultwert, Testwert oder
  gerätespezifisches Feld der eingebetteten Firmware ist, bleibt offen.
- Es wurde weder ein Firmware-Updater ausgeführt noch Firmware übertragen.

## Beobachtete Fakten

- ASUS veröffentlicht gerätespezifische InfoHub-Software und ein separates
  Firmwarepaket im selben produktspezifischen CDN-Verzeichnis.
- Das InfoHub-ZIP enthält einen Inno-Setup-PE32-Installer.
- Der Installer-Ressourcenstring nennt Produkt `ASUS InfoHub` und
  `ProductVersion 1.0.0.15`.
- Der PE-Header enthält einen Linker-Zeitstempel 2025-02-12; dieser Wert ist
  nicht gleichbedeutend mit Veröffentlichungs- oder sicherem Builddatum.
- Die gegenwärtig zugängliche InfoHub-Installerhülle importiert keine HID- oder
  WinUSB-spezifische DLL.
- Der Firmware-Updater importiert HID- und SetupAPI-Funktionen und enthält
  einen generischen VID/PID/MI/COL-Gerätepfad-Regex.
- Exakte Texttreffer für `0b05`, `1c7b`, `VID_0B05`, `PID_1C7B`, `MI_00`,
  `MI_01` oder `0xff06` wurden im Updater nicht gefunden. Zufällige
  Bytefolgen und Relocationsoffsets gelten nicht als Treffer.

## Abgeleitete Erkenntnisse

- Der protokollrelevante Anwendungscode liegt wahrscheinlich in den vom
  Inno-Installer installierten Nutzdateien, nicht im analysierten Setup-Stub.
- Die Kombination aus ARM-artigen Daten und Embedded-System-Strings in
  `.rdata` spricht dafür, dass der Updater eine Firmware-Nutzlast statisch
  eingebettet hat.
- `320x320` ist ein starker Anhaltspunkt für eine quadratische
  gerätespezifische Bildgeometrie, aber noch keine unabhängig bestätigte
  Auflösung und keine Aussage zum Übertragungsformat.

## Hypothesen

| ID | Hypothese | Grundlage | Status |
| --- | --- | --- | --- |
| SA-H-001 | `320x320` im Firmware-Updaternamen bezeichnet die LCD-Pixelauflösung. | Interner Dateiname und 2,8-Zoll-Produktangabe | offen; nur Namensinterpretation |
| SA-H-002 | Protokollcode befindet sich in komprimierten InfoHub-Nutzdateien. | Analysiert wurde weiterhin nur der Inno-Setup-Stub; Inno 6.4.0.1 wird von `innoextract` 1.9 nicht unterstützt | offen |
| SA-H-003 | Das Firmware-Updater-PE enthält eine statisch eingebettete Firmware-Nutzlast. | ARM-artige Daten und Firmware-/Bootloaderstrings in `.rdata` | stark gestützt; Bytegrenzen nicht bestätigt |
| SA-H-004 | Der Updater verwendet HID-Reports für den Firmwaretransport. | HID-Caps-Imports und USB-Lese-/Schreibstrings | offen; Transferart und Aufrufpfade noch nicht disassembliert |

Es wird ausdrücklich **nicht** abgeleitet, dass Interface 1 Bilddaten,
Interface 0 Steuerbefehle oder ein 1024-Byte-Report automatisch einen
Bildblock überträgt.

## Offene Fragen

- Welche DLL oder EXE enthält die eigentliche Gerätekommunikation?
- Nutzt InfoHub HID-APIs direkt, dynamisch geladene Bibliotheken oder einen
  Dienst? Die InfoHub-Nutzdateien sind weiterhin nicht extrahiert.
- Wo werden VID/PID und Interfaceauswahl konfiguriert?
- Welche Paketheader, Opcodes, Längen-, Sequenz- oder Prüfsummenfelder gibt es?
- Welche Bedeutung haben die beiden HID-Interfaces tatsächlich?
- Ist `320x320` die reale Pixelauflösung?
- Wo beginnen und enden die mutmaßlichen Firmwaredaten in `.rdata`, und wie
  werden Länge, Zieladresse und Integrität kodiert?
- Welche VID/PID-Werte und HID-Interface-GUIDs werden im ausführbaren Code an
  die generische Geräteerkennung übergeben?
- Existieren auf ASUS noch ältere, nicht mehr auf der Supportseite gelistete
  Versionen?

## Empfohlener nächster Schritt

Der nächste rein statische Schritt ist eine kontrollierte Disassembly des
Firmware-Updaters mit Querverweisen auf HID-/SetupAPI-Imports,
Gerätepfad-Regex, `usb writex`/`usb readex` und die mutmaßliche
Firmware-Nutzlast. Parallel wird für den InfoHub-Installer eine bereits
vorhandene, Inno Setup 6.4 unterstützende statische Extraktionsmöglichkeit
benötigt; `innoextract` 1.9 genügt nicht. Unsichere Carving- oder
Ausführungsmethoden bleiben ausgeschlossen.

## Vertiefte statische Funktionsanalyse des Firmware-Updaters

Die Disassembly-Querverweise stehen in:

- `../research/reports/firmware-updater-imports-and-enumeration.md`
- `../research/reports/firmware-updater-hid-io.md`
- `../research/reports/firmware-updater-workflow-and-payload.md`

### Beobachtete Fakten

- SetupAPI zählt die HID-Interfaceklasse indexbasiert auf, ermittelt zunächst
  die Detailpuffergröße und liest dann den Gerätepfad. Ein Regex zerlegt VID,
  PID sowie optional REV, MI und COL.
- Kandidaten werden über `CreateFileW` geprüft; HID-Attribute und Caps werden
  gelesen. Konkrete Zielkennung und Interfaceauswahl sind noch nicht sicher.
- `usb writex`/`usb readex` referenzieren `WriteFile`/`ReadFile`-Schleifen mit
  Overlapped-I/O, 3000 ms Wartezeit, bis zu drei Versuchen und `0x401` Byte
  Puffer. Ein Nullbyte steht vor `0x400` Byte Nutzinhalt.
- Die höhere Schicht segmentiert in höchstens `0x3fe` Datenbytes hinter zwei
  Steuerbytes. Das zweite Byte enthält einen 7-Bit-Folgewert; beim ersten
  Segment ist Bit 7 gesetzt.
- Übertragen wird die `.rdata`-Region `VA 0x5c21b0..0x5f358c` beziehungsweise
  `Dateioffset 0x1c15b0..0x1f298c`, insgesamt `0x313dc` (201692) Byte.
  Äußere Transferblöcke sind höchstens `0x8000` Byte groß.
- Der Workflow zeigt Boot-Warten, Konfigurationslöschung,
  Firmwareübertragung, Completion-Flag-Austausch und Abschlusswartephase.

### Abgeleitete Zusammenhänge

- Die 1024-Byte-Nutzblöcke stimmen mit der bestätigten Output-Reportgröße von
  Interface 1 überein. Das ist keine direkte Interfacezuordnung.
- Die Bytegrenzen bestätigen die übertragene Region, nicht deren internes
  Firmwareformat oder CPU-Architektur.
- Der 7-Bit-Wert dient der Segmentreihenfolge; weitere Semantik ist offen.

### Hypothesen und unbekannte Punkte

- Das erste Steuerbyte könnte Befehle oder Kanäle unterscheiden; seine Werte
  werden nicht als bestätigte Opcodes bezeichnet.
- Eine transportseitige Prüfsumme wurde nicht erkannt. Versionsprüfung,
  Ziel-VID/PID und MI/COL-Filter bleiben offen.
- Die Drei-DWORD-Struktur nach dem Transfer enthält `0x00100000`,
  `0x000313dc` und `1`. Zieladresse und Flag sind unbestätigte Deutungen.

Keine untersuchte Datei wurde ausgeführt, und es erfolgte kein USB- oder
HID-Gerätezugriff.
