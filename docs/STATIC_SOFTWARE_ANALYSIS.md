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

Das RAR konnte nicht vollständig aufgelistet oder extrahiert werden: Das
vorhandene 7-Zip 26.02 besitzt laut `7z i` keinen RAR-Handler; `unrar` und
`bsdtar` fehlen. Deshalb war keine belastbare vollständige Pfadprüfung möglich
und es wurde bewusst nicht mit alternativen, nicht installierten Werkzeugen
weitergearbeitet. Die Details stehen in
`../research/reports/archive-inventory.txt`.

## Bestätigte USB-/HID-Hinweise

In den statisch zugänglichen Bestandteilen wurden **keine belastbaren direkten
Treffer** für folgende Kennungen gefunden:

- `0b05`, `1c7b`, `VID_0B05`, `PID_1C7B`
- `MI_00`, `MI_01`
- Usage Page `0xff06`
- HID-/WinUSB-API-Importe, die dem eigentlichen InfoHub-Gerätecode zugeordnet
  werden könnten
- belegbare Reportlängen, Paketheader, Opcodes oder Prüfsummenalgorithmen

Der untersuchte PE-Stub ist ein Inno-Setup-Installer. Seine direkten Imports
stammen aus `kernel32.dll`, `comctl32.dll`, `user32.dll`, `oleaut32.dll` und
`advapi32.dll`. Das belegt nur Installerfunktionalität. Die eigentlichen
InfoHub-Nutzdateien bleiben im Inno-Datenbereich komprimiert, weil
`innoextract` nicht vorhanden ist.

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

Es wurden keine belastbaren Hinweise auf Chunkgrößen, Sequenznummern,
Paketheader, Rohpixelformate, JPEG-/PNG-Transformation oder USB-seitige
GIF-/MP4-Verarbeitung gefunden.

## Firmwarefunde

- Offizielles Paket: Firmwareversion 51, veröffentlicht am 2025-07-10.
- ASUS-SHA-256 und lokal berechneter SHA-256 stimmen überein.
- Das RAR5 enthält dem sichtbaren Header nach mindestens die Datei
  `WW11_320x320_2.8inch_v51_TUF_20250626.exe`.
- Der Inhalt dieser EXE und eine mögliche darin eingebettete Firmwaredatei
  konnten wegen des fehlenden RAR-Decoders nicht statisch untersucht werden.
- Es wurde weder ein Firmware-Updater ausgeführt noch Firmware übertragen.

## Beobachtete Fakten

- ASUS veröffentlicht gerätespezifische InfoHub-Software und ein separates
  Firmwarepaket im selben produktspezifischen CDN-Verzeichnis.
- Das InfoHub-ZIP enthält einen Inno-Setup-PE32-Installer.
- Der Installer-Ressourcenstring nennt Produkt `ASUS InfoHub` und
  `ProductVersion 1.0.0.15`.
- Der PE-Header enthält einen Linker-Zeitstempel 2025-02-12; dieser Wert ist
  nicht gleichbedeutend mit Veröffentlichungs- oder sicherem Builddatum.
- Die gegenwärtig zugängliche Installerhülle importiert keine HID- oder
  WinUSB-spezifische DLL.
- Das Firmwarearchiv ist RAR5; sein sichtbarer interner EXE-Name enthält
  `320x320`.

## Abgeleitete Erkenntnisse

- Der protokollrelevante Anwendungscode liegt wahrscheinlich in den vom
  Inno-Installer installierten Nutzdateien, nicht im analysierten Setup-Stub.
- Das separate Firmwarepaket dürfte weitere Erkenntnisse liefern, sobald es
  mit einem bereits autorisiert vorhandenen RAR5-fähigen Werkzeug sicher
  entpackt werden kann.
- `320x320` ist ein starker Anhaltspunkt für eine quadratische
  gerätespezifische Bildgeometrie, aber noch keine unabhängig bestätigte
  Auflösung und keine Aussage zum Übertragungsformat.

## Hypothesen

| ID | Hypothese | Grundlage | Status |
| --- | --- | --- | --- |
| SA-H-001 | `320x320` im Firmware-Updaternamen bezeichnet die LCD-Pixelauflösung. | Interner Dateiname und 2,8-Zoll-Produktangabe | offen; nur Namensinterpretation |
| SA-H-002 | Protokollcode befindet sich in komprimierten InfoHub-Nutzdateien. | Analysiert wurde bislang nur der Inno-Setup-Stub | offen |
| SA-H-003 | Das Firmware-Updater-PE enthält eine separate Firmware-Nutzlast. | Übliche Paketform und separater Firmwaredownload | offen; Inhalt nicht extrahiert |

Es wird ausdrücklich **nicht** abgeleitet, dass Interface 1 Bilddaten,
Interface 0 Steuerbefehle oder ein 1024-Byte-Report automatisch einen
Bildblock überträgt.

## Offene Fragen

- Welche DLL oder EXE enthält die eigentliche Gerätekommunikation?
- Nutzt InfoHub HID-APIs direkt, dynamisch geladene Bibliotheken oder einen
  Dienst?
- Wo werden VID/PID und Interfaceauswahl konfiguriert?
- Welche Paketheader, Opcodes, Längen-, Sequenz- oder Prüfsummenfelder gibt es?
- Welche Bedeutung haben die beiden HID-Interfaces tatsächlich?
- Ist `320x320` die reale Pixelauflösung?
- Welche Firmware-Nutzlast und Versionsmetadaten enthält der Updater?
- Existieren auf ASUS noch ältere, nicht mehr auf der Supportseite gelistete
  Versionen?

## Empfohlener nächster Schritt

Ohne Ausführung und ohne Gerätezugriff sollte ein bereits vorhandenes,
RAR5-fähiges Entpackwerkzeug sowie `innoextract` in einer ausdrücklich
freigegebenen Analyseumgebung bereitgestellt werden. Danach:

1. RAR- und Inno-Inhaltslisten erneut gegen absolute Pfade und
   Pfadtraversierung prüfen.
2. Ausschließlich nach neuen Unterordnern in `research/extracted/` entpacken.
3. Nutzdateien inventarisieren und PE-Imports, Ressourcen, Konfigurationen und
   aussagekräftige ASCII-/UTF-16-Strings untersuchen.
4. Treffer für VID/PID, Interfacepfade, HID-Aufrufe und Paketkonstanten durch
   Disassembly-Querverweise validieren.

Erst diese statische Fortsetzung kann die derzeit fehlenden direkten
USB-/HID-Protokollbelege liefern. Sie autorisiert weiterhin keinerlei
HID-/USB- oder Firmware-Schreibzugriff.
