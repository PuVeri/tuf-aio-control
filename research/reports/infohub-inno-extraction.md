# Statische Extraktion von ASUS InfoHub 1.0.0.15

Stand: 2026-09-02

## Zweck und Sicherheitsgrenze

Dieser Bericht inventarisiert und extrahiert den vorhandenen Installer
`ASUS-InfoHub-TUF-1.0.0.15.exe` ausschließlich lesend unter Linux. Der
Installer und seine extrahierten Windows-Dateien werden niemals ausgeführt.
Es gibt keine Gerätekommunikation, keine HID-Zugriffe, kein Wine, keine VM und
keine Firmwareaktion.

Status: **erfolgreich abgeschlossen**. Alle Nutzdateien wurden statisch
extrahiert und checksumgeprüft; die enge EXE-/DLL-Triage ist abgeschlossen.

## 1. Eingangsartefakt und PE-Struktur

| Eigenschaft | Wert |
| --- | --- |
| Dateigröße | 90.476.632 Byte (`0x05649058`) |
| SHA-256 | `b7d867a13e8918be09675883330a801c6e3dfff2568afd32c3c18193e0ef9164` |
| Typ | PE32, Intel i386, Windows GUI, 11 Sektionen |
| PE-Zeitstempel | 2025-02-12 06:53:16 UTC |
| Ende der letzten PE-Sektion | `0x000d7a00` |
| Authenticode-Offset | `0x05645ca8` |
| Authenticode-Größe | 13.232 Byte (`0x33b0`) |
| Dateiende | `0x05649058` |

Die letzte Sektion `.rsrc` beginnt bei `0x000bd200`, besitzt eine rohe Größe
von `0x1a800` Byte und endet exakt bei `0x000d7a00`. Der vor der
Authenticode-Tabelle liegende Inno-Overlay-/Nutzdatenbereich ist damit:

```text
Start: 0x000d7a00 (883.200)
Ende:  0x05645ca8 (90.463.400), exklusiv
Größe: 0x0556e2a8 (89.580.200 Byte)
```

Die Authenticode-Tabelle folgt unmittelbar und reicht bis zum Dateiende. Sie
gehört nicht zum extrahierbaren Inno-Datenstrom.

## 2. Inno-Loader, Header und eingebettete Streams

Die PE-Ressource `RCDATA/11111` liegt bei Dateioffset `0x000d6a28`, ist 44
Byte groß und beginnt mit der Inno-Loader-Signatur:

```text
72 44 6c 50 74 53 cd e6 d7 7b 0b 2a  = rDlPtS + Signaturbytes
```

Die anhand des offiziellen `innoextract`-Loaderformats dekodierten Felder sind:

| Feld | Wert |
| --- | ---: |
| Loaderrevision | `1` |
| eingebettetes Setup-Modul | `0x0554d93f` |
| unkomprimierte Größe des Setup-Moduls | 3.526.144 Byte (`0x35ce00`) |
| CRC-32 des unkomprimierten Setup-Moduls | `0x916c270f` |
| Setup-Header | `0x05539fae` |
| Setup-Daten | `0x000d7a00` |
| Loaderheader-CRC-32 | `0x263c19a4` |

Am Headeroffset steht die 64-Byte-Inno-Versionssignatur
`Inno Setup Setup Data (6.4.0.1)`. Der lokale
`innoextract 1.9` bestätigt diese Datenversion mit `--data-version`, kann den
darauffolgenden modernen Header jedoch nicht lesen. Sein reproduzierbarer
Fehler ist bereits in `research/reports/infohub-innoextract-list.txt`
festgehalten.

Der Setup-Datenstrom beginnt bei `0x000d7a00` mit `zlb`, der Inno-
Chunksignatur. Der erfolgreich dekodierte Header ergibt folgende Struktur:

| Struktur | Ergebnis |
| --- | --- |
| primärer Setup-Headerblock | 73.623 Byte gespeichert, 580.384 Byte dekomprimiert, LZMA1 |
| sekundärer Dateilokationsblock | 6.568 Byte gespeichert, 12.789 Byte dekomprimiert, LZMA1 |
| Dateieinträge | 149 |
| Dateilokationen/Nutzobjekte | 147 |
| Nutzdatenchunks | 1 |
| Nutzdatenkompression | LZMA1, Solid-Chunk |
| Chunkoffset relativ zu Setup-Daten | `0x0` |
| komprimierte Chunkgröße | `0x054625aa` = 88.483.242 Byte |
| Verschlüsselung | keine |

Der Chunk beginnt unmittelbar bei `0x000d7a00`. Seine Größenangabe endet bei
`0x05539faa`; danach folgen vier Formatbyte und bei `0x05539fae` die Setup-
Headersignatur. Das eingebettete komprimierte Setup-Modul beginnt anschließend
bei `0x0554d93f`. Es gibt keine externen `.bin`-Slices.

Die Differenz zwischen 149 Dateieinträgen und 147 Nutzobjekten ist erklärt:
Ein erster besonderer Dateieintrag besitzt keine Nutzlokation, und zwei
Einträge für `{app}\ASUS InfoHub.exe` referenzieren dieselbe Lokation 0. Die
Extraktion erzeugt deshalb korrekt 147 eindeutige Dateien.

## 3. Bewertung statischer Linux-Werkzeuge

### 3.1 Gewählter Weg: offizieller `innoextract`-Entwicklungsstand

Das offizielle Repository `https://github.com/dscharrer/innoextract` wurde
projektlokal und git-ignoriert nach
`research/extracted/tooling/innoextract/` geklont. Verwendeter und für die
Reproduzierbarkeit festgehaltener Stand:

```text
Commit: 6e9e34ed0876014fdb46e684103ef8c3605e382e
Datum:  2025-02-06T22:15:28+01:00
```

Der Quellcode registriert die exakte Signatur
`Inno Setup Setup Data (6.4.0.1)` als Inno Setup 6.4.0. Die Datei `VERSION`
nennt weiterhin nur 6.3.3; das Upstream-Issue 186 dokumentiert diesen
veralteten Anzeigetext nach dem 6.4.0-Supportcommit. Der Parser ist
quelloffen (zlib-Lizenz), liest Installer statisch und führt enthaltene
Skripte oder Windows-Code nicht aus.

Quellen:

- `https://github.com/dscharrer/innoextract/commit/e58f295d80c3bbd18fb01c18983855064ebc361f`
- `https://github.com/dscharrer/innoextract/issues/186`
- `https://github.com/dscharrer/innoextract/blob/6e9e34ed0876014fdb46e684103ef8c3605e382e/src/setup/version.cpp`

### 3.2 Vor einem Build dokumentierte Abhängigkeiten

Ein Quellbuild ist nötig, weil die installierte Version 1.9 den 6.4-Header
nicht unterstützt und Upstream keinen aktuellen Linux-Release-Build
veröffentlicht. Es wird kein fremdes Windows-Binärprogramm verwendet.

Vorhanden sind GNU `make`, die Laufzeitbibliotheken von Boost 1.90, liblzma,
bzip2 und zlib sowie die Entwicklungsheader von liblzma und zlib. Es fehlen:

| Paket | Begründung |
| --- | --- |
| `gcc-c++` | C++-Compiler; nur der C-Compiler ist vorhanden |
| `cmake` | vom Upstream-Buildsystem vorgeschriebener Konfigurator |
| `boost-devel` | benötigte Boost-Header für iostreams, filesystem, date_time, system und program_options |
| `bzip2-devel` | Header/Linkmetadaten für den von Boost.Iostreams unterstützten BZip2-Pfad |

Die Pakete sind reine Buildvoraussetzungen; sie werden weder Produktions- noch
Laufzeitabhängigkeiten von `tuf-aio-control`. Vor dieser Dokumentation wurde
kein Paket installiert.

Die anschließend freigegebene Systeminstallation scheiterte vor jeder
Änderung am lokal erforderlichen `sudo`-Passwort. Stattdessen wurden die
benötigten Fedora-44-RPMs mit `dnf download` ausschließlich in
`research/extracted/tooling/rpms/` geladen, mit `rpm -Kv` gegen den Fedora-
Schlüssel `36f612dcf27f7d1a48a835e4dbfcf71c6d9f90a6` geprüft und in einen
projektlokalen Sysroot entpackt. Alle Header-, Signatur- und Payloadprüfungen
meldeten `OK`. Installiert oder in `/usr` verändert wurde nichts.

Der unveränderte Upstream-Quellstand wurde in
`research/extracted/tooling/innoextract-build-6/` gebaut. Das resultierende
Linux-ELF hat SHA-256
`f560bb9dc3e59dcf531399c0d1f11fd111a3f64a89b5ba0297ad354edcaf9987`.
Alle Quell-, RPM-, Sysroot- und Builddateien liegen unter `research/extracted/`
und sind git-ignoriert.

### 3.3 Nicht gewählte Alternativen

- `innoextract 1.9`: statisch und seriös, aber nur bis 6.0.5 freigegeben; der
  konkrete Header scheitert reproduzierbar.
- `7z 26.02`: inventarisiert PE, Overlay und Zertifikat korrekt, rekonstruiert
  aber weder Inno-Dateitabelle noch Nutzdateien.
- `unar`: erkennt diesen modernen Inno-Datenstrom nicht vollständig.
- `uninno`: quelloffener Perl-Parser, verlangt mehrere lokal fehlende Module;
  explizite belastbare 6.4.0.1-Unterstützung ist nicht nachgewiesen.
- Rust-Bibliotheken `inno` und `innospect`: statische, quelloffene und moderne
  Parser mit 6.4-Unterstützung, lokal fehlt jedoch die gesamte Rust-Toolchain.
  Für den exakt benötigten Stand ist der offizielle Innoextract-Supportweg
  enger und besser belegt.
- Fremde vorgebaute Windows-Forks oder Einzel-Skripte werden nicht ausgeführt.

## 4. Extraktion und Reproduzierbarkeit

Bis zur Extraktion verwendete rein lesende Prüfungen:

```sh
stat --printf='%s\n' ASUS-InfoHub-TUF-1.0.0.15.exe
sha256sum ASUS-InfoHub-TUF-1.0.0.15.exe
file ASUS-InfoHub-TUF-1.0.0.15.exe
7z l -slt ASUS-InfoHub-TUF-1.0.0.15.exe
objdump -x ASUS-InfoHub-TUF-1.0.0.15.exe
innoextract --data-version ASUS-InfoHub-TUF-1.0.0.15.exe
```

PE-Sektionsenden, Security Directory und `RCDATA/11111` wurden zusätzlich mit
dem bereits systemweit vorhandenen Python-Modul `pefile` gegengeprüft. Es wurde
nichts am Installer verändert.

Vor der Extraktion las `--list --list-sizes --list-checksums` die vollständige
Dateitabelle fehlerfrei. `--test` dekomprimierte anschließend sämtliche
Nutzobjekte und prüfte deren im Installer gespeicherte Checksummen ohne
Schreibzugriff. Erst danach erfolgte die Extraktion:

```sh
LD_LIBRARY_PATH="$PWD/research/extracted/tooling/sysroot/usr/lib64" \
  research/extracted/tooling/innoextract-build-6/innoextract \
  --extract --timestamps=UTC \
  --output-dir research/extracted/infohub-1.0.0.15 \
  research/extracted/infohub-v1.0.0.15/ASUS-InfoHub-TUF-1.0.0.15.exe
```

Ergebnis:

| Eigenschaft | Wert |
| --- | ---: |
| eindeutige extrahierte Dateien | 147 |
| Gesamtgröße | 248.549.932 Byte |
| EXE/DLL-Dateien | 11 |
| Extraktionsfehler | 0 |
| Manifestprüfungen | 147 erfolgreich, 0 fehlgeschlagen |

Der Zielpfad `research/extracted/infohub-1.0.0.15/` ist durch `.gitignore`
abgedeckt. Ursprüngliche relative Pfade, Groß-/Kleinschreibung und die im
Installer verfügbaren Zeitstempel wurden durch `innoextract` übernommen. Die
erste der beiden identischen `ASUS InfoHub.exe`-Zuordnungen wurde wie vom
Header vorgesehen durch dieselbe Datenlokation überschrieben; es ging dabei
kein unterschiedliches Nutzobjekt verloren.

Das versionierbare TSV-Manifest
`research/manifests/infohub-1.0.0.15-files.sha256` besitzt die Spalten
`sha256`, `size` und `path`. Alle Pfade sind relativ zum Extraktionsroot und
byteweise sortiert. Eine unabhängige Nachprüfung gegen die extrahierten Dateien
ergab 147 von 147 passenden Größen und SHA-256-Werten.

## 5. Minimale EXE-/DLL-Triage

Die Triage blieb auf importierte APIs, ASCII-/UTF-16-Zeichenketten und exakte
Bytemuster in den elf extrahierten EXE/DLLs beschränkt. Es gab keine
Disassemblierungs- oder Senderrekonstruktion.

### 5.1 Primärer Kandidat: `app/ASUS InfoHub.exe`

SHA-256:
`7eeb0c61904a36f8fab3945209d8472088db8b093250387e3b06228b81d356e0`

Die stärksten kombinierten Treffer sind:

- UTF-16 bei Dateioffset `0x12e7b0`: `VID_0B05&PID_1C7B&MI_00`;
- ASCII bei `0x12e7fc`: `Device connected and recognized
  (VID_0B05&PID_1C7B&MI_00)`;
- ASCII bei `0x12e878`: Diagnose mit `usagePage`, `usage`, HID-Pfad und
  Matchstatus;
- ASCII bei `0x130dd0`: `EnumerateLEDDevice done, hid1=%d hid2=%d`;
- ASCII bei `0x130dfc` und `0x130e18`: getrennte Meldungen für `LED HID2` und
  `LED HID1`, bei HID1 zusätzlich `fw=%d`;
- statische Imports aus `SETUPAPI.dll`: `SetupDiGetClassDevsA`,
  `SetupDiEnumDeviceInterfaces`, `SetupDiGetDeviceInterfaceDetailA` und
  weitere Geräteenumerationsfunktionen;
- statische Imports aus `HID.DLL`: `HidD_GetAttributes`,
  `HidD_GetPreparsedData`, `HidP_GetCaps` und `HidD_FreePreparsedData`;
- statische `CreateFileA/W`-, `ReadFile`- und `WriteFile`-Imports;
- dynamisch aufgelistete HID-Namen einschließlich `HidD_GetFeature` und
  `HidD_SetFeature`;
- `Image Files (*.gif;*.jpg;*.jpeg;*.png;*.bmp;*.mp4;*.avi)`, `.jpg`, `.jpeg`
  sowie der Buildpfadteil `(320x320)\Project\TUF Cooler-...`;
- direkte Imports der unten genannten JPEG-/GIF-/OpenCV-Funktionen aus
  `XYUI.dll`, darunter `SaveJpgImageFile`.

Diese Kombination belegt die Geräteerkennung, zwei HID-Verbindungen und die
Bild-/Medienintegration in derselben EXE. Sie macht `ASUS InfoHub.exe` zum
eindeutigen nächsten Host-Senderkandidaten, ohne bereits eine konkrete
Reportbuilderfunktion zu behaupten.

### 5.2 Sekundärer Kandidat: `app/XYUI.dll`

SHA-256:
`932fe1821b04584e0ef48c7a5c5b2e6a573da14519daac7031965860fcd52913`

Starke Bildaufbereitungstreffer sind:

- UTF-16 `image/jpeg`, `_%s\frame_%d.jpg` und `%s/frame_%d.jpg`;
- exportierte C++-Funktionen `SaveJpgImageFile@GIFViewCtrl`,
  `SaveGIFImageFile`, `DrawFrame`, `GetFrameThumbnail` und
  `OpenCVViewCtrl`;
- Import von `opencv_world490.dll`;
- derselbe `(320x320)\Project\TUF Cooler-...`-Buildpfadteil.

`XYUI.dll` ist damit der wahrscheinliche JPEG-/Frame-Aufbereitungshelfer. Es
importiert weder HID noch SetupAPI und ist kein belegter Geräte- oder
Transportproducer.

### 5.3 Abgrenzung der übrigen DLLs und numerischen Muster

`opencv_world490.dll`, `opencv_world490d.dll` und
`opencv_videoio_ffmpeg490.dll` enthalten erwartungsgemäß viele generische
JPEG-/Codec-Treffer. Die HWiNFO- und Microsoft-Runtime-DLLs liefern ebenfalls
zufällige Rohmuster, aber keine Kombination aus Ziel-ID, HID-/SetupAPI und
InfoHub-Bildlogik. Sie sind für das nächste Ticket keine primären Kandidaten.

Die Rohmuster für `1024`, `1020`, `440`, `16`, `08 00 00 80`, JPEG SOI/EOI
und einzelne Bytes `0x80..0x87` kommen in großen PE-, Runtime- und
Codecdateien häufig vor. Insbesondere die einzige aufsteigende Folge
`80 81 ... 87` in `ASUS InfoHub.exe` ist Teil einer vollständigen
`00..ff`-Bytetabelle und keine Befehlstabelle. Ohne Kontrollflussbezug werden
diese Treffer deshalb nicht als Protokollbeleg gewertet. Die exakten
VID/PID-/MI_00-Zeichenketten und API-/Diagnosekombinationen sind die stärkere
Evidenz.

## 6. Nächster konkreter Analysepfad

Das nächste Ticket sollte ausschließlich `ASUS InfoHub.exe` statisch öffnen
und in dieser Reihenfolge arbeiten:

1. Von den belegten `SetupDi*`-/`HidD_*`-Imports und den Diagnosezeichenketten
   `EnumerateLEDDevice`, `LED HID1` und `LED HID2` zu den beiden Handle-
   Strukturen gehen.
2. Xrefs auf `WriteFile` und `ReadFile` nach diesen Handles trennen und nur die
   Aufrufer mit 440-, 1024- beziehungsweise 16-Byte-Puffern verfolgen.
3. Im 1024-Byte-Zweig gezielt den Builder für vier Byte Controlword plus 1020
   Byte Nutzlast suchen; erst dort `0x80000008` und Folgeindizes bewerten.
4. Genau einen Schritt rückwärts zum JPEG-Pufferproducer und zu den importierten
   `XYUI.dll`-Funktionen gehen, um EOI/Suffix und letzte Blockinitialisierung zu
   bestimmen.
5. Den 440-Byte-Zweig anschließend nur auf begleitende `0x19`- und
   `0x80..0x87`-Aufrufer eingrenzen.

Dieser Pfad bleibt vollständig statisch. Gerätekommunikation, Ausführung der
Windows-Dateien und eine breite Analyse der Drittanbieter-DLLs sind dafür nicht
nötig.
