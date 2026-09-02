# Triage der ASUS-/InfoHub-Hostkomponente für den LCD-JPEG-Transfer

Stand: 2026-09-02

## Zweck und Grenze

Diese Triage sucht ausschließlich in den bereits lokal vorhandenen
ASUS-/InfoHub-Artefakten nach der Hostkomponente des normalen LCD-JPEG-
Transfers. Sie soll den Sender nicht rekonstruieren, sondern nur den
wahrscheinlich zuständigen Binärbestand, zugängliche Belege und den nächsten
engen Analysepfad bestimmen.

Verwendet wurden nur vorhandene Dateien, frühere statische Berichte sowie
lokale `file`-, `7z`-, `objdump`-, `strings`-, `grep`- und `xxd`-Abfragen. Es
gab keine Gerätekommunikation, Installation, Websuche, Windows-Ausführung,
Wine-, VM- oder Ghidra-Nutzung.

## Ergebnis

Die wahrscheinlich zuständige Komponente ist **eine noch nicht extrahierte
installierte InfoHub-Anwendungs-EXE oder -DLL im Inno-Datenbereich von
`ASUS-InfoHub-TUF-1.0.0.15.exe`**. Ihr konkreter Dateiname und ihre Funktionen
sind mit dem gegenwärtigen lokalen Extraktionsstand nicht zugänglich.

Der sichtbare PE-Code dieser Datei ist nur der Inno-Setup-Stub. Der zweite
zugängliche Hostkandidat,
`WW11_320x320_2.8inch_v51_TUF_20250626.exe`, ist ein separater
Firmware-Updater. Er implementiert HID-I/O und einen 1024-Byte-
Firmwaretransport, aber keinen belegten normalen LCD-JPEG-Sender.

Damit ist die Triage an der geforderten Abbruchgrenze angekommen: Eine weitere
Suche in komprimierten Overlaybytes oder eine breitere Analyse des Updaters
kann die fehlende InfoHub-Nutzdatei nicht ersetzen.

## 1. Lokal vorhandene Hostartefakte

| Artefakt | Lokal zugänglicher Inhalt | Eignung als normaler LCD-Sender |
| --- | --- | --- |
| `research/extracted/infohub-v1.0.0.15/ASUS-InfoHub-TUF-1.0.0.15.exe` | 90.476.632-Byte-Inno-6.4.0.1-Installer; sichtbarer PE-Stub plus komprimierter Overlaydatenbereich | **wahrscheinlich enthält er die zuständige Komponente**, diese ist aber nicht als Einzeldatei extrahiert |
| `research/extracted/firmware-v51/WW11_320x320_2.8inch_v51_TUF_20250626.exe` | vollständig zugänglicher x86-Firmware-Updater mit eingebetteter ARM-Gerätefirmware | **nicht der normale JPEG-Sender**; nur Upgrade-HID-Pfad belegt |
| `research/extracted/device-firmware-v51-static/device-firmware-v51.bin` | ARM-Gerätefirmware, also Consumer des LCD-Protokolls | kein Hostproducer |

### 1.1 Grenze des InfoHub-Installers

`7z` erkennt beim InfoHub-Installer ein PE-Abbild von nur 942.080 Byte und
danach den undifferenzierten Eintrag `[0]` mit 89.580.200 Byte. Dieser
Overlaybereich endet unmittelbar vor dem Authenticode-Bereich. Er enthält die
Inno-Nutzdaten, aber keine mit lokalen Werkzeugen zuverlässig rekonstruierte
Dateiliste.

Der vorhandene `innoextract 1.9` erkennt die Setupversion `6.4.0.1`, scheitert
jedoch bereits beim Setup-Header mit `Stream error while parsing setup
headers`. Es werden deshalb weder installierte Dateinamen noch einzelne
EXE-/DLL-Inhalte geliefert. Dieser Fehler wurde in
`research/reports/infohub-innoextract-list.txt` bereits reproduzierbar
gespeichert und in dieser Triage unverändert bestätigt.

Der Stub importiert aus `kernel32.dll`, `comctl32.dll`, `user32.dll`,
`oleaut32.dll` und `advapi32.dll`. Seine `ReadFile`-, `WriteFile`- und
`CreateFileW`-Importe gehören ohne HID-/SetupAPI-Bezug zur generischen
Installerhülle und sind kein Geräte-I/O-Beleg. Es fehlen im sichtbaren Stub:

- `HID.DLL`-/HidD-/HidP-Importe;
- SetupAPI-Geräteaufzählung;
- ein belegter VID/PID- oder MI-Filter;
- xrefs auf 1024-/440-/16-Byte-HID-Reports;
- ein zugänglicher JPEG-Chunkbuilder.

Die gezielte ASCII-/UTF-16-Suche fand im Stub keine belastbaren Treffer für
`0b05:1c7b`, `VID_0B05`, `PID_1C7B`, `320x320`, JPEG/JPG, HID-Endpunkte oder
die bekannten Reportgrößen. Scheinbare Groß-/Kleinschreibungsfragmente wie
`JpG`, `uSB` oder `440` liegen massenhaft in komprimierten Daten und besitzen
weder Stringgrenzen noch Code-xrefs; sie sind keine Evidenz.

Auch die Markersuche hilft nicht: Im gesamten Installer kommen `ff d8` 1409-
mal und `ff d9` 1418-mal vor. In einem komprimierten 89,58-MB-Datenbereich
belegen solche Zweibytemuster weder JPEG-Dateigrenzen noch Senderlogik. Ohne
gültige Inno-Dateitabelle wurde deshalb kein Marker-Carving fortgesetzt.

## 2. Firmware-Updater als negativer Vergleichskandidat

Der Firmware-Updater enthält echte Host-HID-Funktionen. Sie erklären mehrere
gesuchte Signaturen, grenzen ihn aber zugleich vom normalen LCD-Transfer ab.

### 2.1 Relevante zugängliche Funktionen

| Virtuelle Adresse | Funktion | Aussage für diese Triage |
| --- | --- | --- |
| `0x40ba93..0x40be9c` | SetupAPI-Aufzählung von HID-Interfaces | echter Host-Gerätepfad, aber konkrete Ziel-ID und Interfaceauswahl nicht belegt |
| `0x40b670` ff. | Parser für `hid#vid_...&pid_...` mit optionalem REV/MI/COL | generische HID-Pfadanalyse, kein sichtbarer fester ASUS-Filter |
| `0x40b380` | `WriteFile`-Helfer, `0x401` Byte mit führender Null | echter HID-Write des Updaters |
| `0x40b4e0` | `ReadFile`-Helfer, derselbe `0x401`-Byte-Rahmen | echter HID-Read des Updaters |
| `0x402460` | segmentierter Write-Builder: 2 Steuerbyte + bis zu `0x3fe` Datenbyte | **abweichend** vom LCD-JPEG-Modell 4 + `0x3fc` |
| `0x4027c0` | segmentierter Antwortleser mit Byte-0- und 7-Bit-Folgeprüfung | Upgradeantwort, kein 16-Byte-Bild-IN-Pfad |
| `0x40c230` | direkter vollständiger `0x400`-Byte-Write | verwendet für feste Upgrade-Rohpakete |
| `0x402b40..0x403168` | zentraler Upgradeworkflow | Boot-Warten, Konfiguration löschen, Firmware `0x86`, Completion und Reenumeration |

Zugehörige Diagnose-/Gerätestrings liegen an folgenden Dateioffsets:

| Dateioffset | String |
| ---: | --- |
| `0x1f3ffc` | `usb writex(%d):%08x` |
| `0x1f4070` | `usb readex(%d):%08x` |
| `0x1f4090` | `hid#vid_...&pid_...`-Regex |
| `0x1f3070` | `Wiping configuration` |
| `0x1f31d0` | `Waiting to write upgrade completion flag...` |

### 2.2 Warum dies nicht der normale LCD-JPEG-Sender ist

Der belegte höhere Updatertransport verwendet:

```text
Byte 0      Transportwert, etwa 0x45 / 0x86 / 0x09 / 0x02
Byte 1      7-Bit-Segmentwert plus Erstsegmentbit
Byte 2..    höchstens 0x3fe = 1022 Datenbyte
```

Der normale LCD-Transport benötigt dagegen:

```text
Byte 0..3   Little-Endian-Controlword, Command 0x08
Byte 4..    exakt 0x3fc = 1020 JPEG-Byte
```

Alle rekonstruierten Aufrufer des Updaterbuilders gehören zum
Firmwareworkflow: `0x45` Konfigurationslöschung, `0x86` Firmwareblock,
`0x09` Completionstruktur, `0x02` Abschluss/Reenumeration sowie direkte
`0x88`-Rohpakete. Es gibt keinen belegten normalen `0x08`-Aufrufer, keinen
1020-Byte-JPEG-Chunkpfad, keinen 440-Byte-Controlpfad und keinen 16-Byte-
Bild-IN-Read. Die vorhandenen JPEG-/Bildstrings stammen aus allgemeinen
Bildbibliotheken oder der eingebetteten Gerätefirmware:

- `progressive jpeg` bei Dateioffset `0x195dd0` ist ohne Sender-xref nur ein
  Decoder-/Bibliotheksstring;
- `c:\syst\wapper.jpg` bei `0x1e8e8c` liegt innerhalb der als ARM-Firmware
  übertragenen Region `0x1c15b0..0x1f298c` und ist kein x86-Hostpfad;
- `320x320` ist im äußeren Dateinamen vorhanden, nicht als belegte
  Hostencodergeometrie.

Die exakte Little-Endian-Folge `05 0b 7b 1c` kommt bei Dateioffset
`0x1f0160` und `0x1f2798` vor. Beide Positionen liegen ebenfalls innerhalb
der eingebetteten ARM-Firmware. Bei `0x1f2798` ist die Folge Teil des
USB-Gerätedeskriptors; bei `0x1f0160` steht sie in einer Firmware-Datentabelle
neben `08 81` und `0x51`. Diese Treffer identifizieren das eingebettete
Zielimage, aber keinen x86-Aufrufer, der den normalen LCD-Hosttransfer
implementiert.

Numerische Funde zu `1024`, `440`, `16`, `0x08`, `0x19` oder `0x80..0x87`
außerhalb der genannten kontrollflussbelegten Funktionen sind wegen PE-
Relocations, Ressourcen, Bibliotheken und eingebetteter Firmware nicht
semantisch verwertbar. Insbesondere ist nur `0x86` im Host-Upgradekontrollfluss
belegt; die vollständige normale Controlfamilie stammt aus dem ARM-Consumer,
nicht aus zugänglicher InfoHub-Senderlogik.

## 3. Wahrscheinlich zuständige Komponente

Die Evidenz führt zu folgender Rangfolge:

1. **Noch nicht extrahierte InfoHub-Anwendungs-EXE/DLL:** sehr wahrscheinlich
   zuständig. Das offizielle InfoHub-Paket stellt die normale Bild-/Medien-
   Benutzerfunktion bereit; seine eigentlichen installierten Nutzdateien
   liegen ausschließlich im nicht extrahierten Inno-Overlay.
2. **Firmware-Updater-PE:** als normaler JPEG-Sender ausgeschlossen, soweit
   seine vorhandenen statischen Aufrufer reichen. Es besitzt nur den getrennten
   Upgradepfad.
3. **ARM-Gerätefirmware:** bestätigt den Consumer, kann aber den gesuchten
   Windows-Hostproducer nicht enthalten.

Ein genauer Modulname wie `InfoHub.exe`, eine gerätespezifische DLL oder ein
Dienstname kann aus dem lokalen Bestand nicht seriös benannt werden. Solche
Namen wären ohne extrahierte Inno-Dateitabelle erfunden.

## 4. Ist die Senderlogik zugänglich?

**Nein.** Die relevante normale Senderlogik ist in den vorhandenen Artefakten
wahrscheinlich physisch enthalten, aber nicht als analysierbare Datei
extrahiert. Der zugängliche Installerstub ist nicht die Anwendung. Der
zugängliche Firmware-Updater enthält nur eine andere, gefährliche
Upgrade-Transportimplementierung.

Damit sind gegenwärtig nicht bestimmbar:

- konkreter Modulname und PE-Hash des LCD-Senders;
- Funktionsadressen des JPEG-Encoders und `0x08`-Chunkbuilders;
- ASUS-seitige Nullpaddingfunktion;
- Interface-1-Auswahl sowie 16-Byte-IN-Readfolge;
- begleitende normale Interface-0-Befehle einschließlich `0x19` und
  `0x80..0x87`.

## 5. Nächster enger Analysepfad

Der nächste Analyseblock beginnt erst nach einer sicheren, vollständigen und
statischen Extraktion des vorhandenen Inno-6.4.0.1-Datenbereichs. Er soll dann
nicht alle Nutzdateien breit disassemblieren, sondern in dieser Reihenfolge
triagieren:

1. Dateiliste, Größe, Typ und SHA-256 aller installierten EXE/DLL/SYS/JSON/XML-
   Dateien erfassen.
2. Ausschließlich diese Dateien nach ASCII/UTF-16 `VID_0B05`, `PID_1C7B`,
   `0b05`, `1c7b`, `320x320`, JPEG/JPG und HID-/SetupAPI-Namen durchsuchen;
   zusätzlich die gepaarten 16-Bit-Konstanten `0x0b05`/`0x1c7b` prüfen.
3. Nur in treffenden Modulen xrefs auf `SetupDi*`, `CreateFileW`, `WriteFile`,
   `ReadFile`, `HidD_SetOutputReport`, `HidD_GetInputReport`,
   `DeviceIoControl` und gegebenenfalls dynamische `GetProcAddress`-Auflösung
   verfolgen.
4. Den engsten Write-Aufrufer suchen, der gleichzeitig einen `0x400`-Byte-
   Report, Controlword `0x80000008`, Kopierlänge `0x3fc` und fortlaufende
   Indexwörter bildet. Das ist der primäre Senderkandidat.
5. Von diesem Builder genau einen Schritt rückwärts zum JPEG-Speicherproducer
   und einen Schritt vorwärts zum HID-Write verfolgen. Dabei nach SOI/EOI,
   `0x140 × 0x140`, Nullinitialisierung des letzten Reports und Segmentzahl
   suchen.
6. Den zugehörigen Read-Aufrufer mit Länge `0x10` sowie den getrennten
   `0x1b8`-Controlbuilder auf `0x19` und `0x80..0x87` prüfen.

Die bereits bekannten Updateradressen `0x40b380`, `0x40b4e0`, `0x402460`,
`0x4027c0` und `0x40c230` dienen dabei nur als Architekturvergleich. Eine
weitere Analyse ihrer Upgradeaufrufer verspricht für den normalen JPEG-Sender
keinen Erkenntnisgewinn und ist nicht der nächste Pfad.
