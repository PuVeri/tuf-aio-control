# Statische Rekonstruktion des ASUS-InfoHub-LCD-Senders

Stand: 2026-09-02

## Zweck und Sicherheitsgrenze

Analysiert wurden ausschließlich die extrahierten Dateien
`ASUS InfoHub.exe` und, weil der Datenpfad direkt dorthin führt, `XYUI.dll`.
Beide PE-Dateien wurden nur als Daten in Ghidra 12.1 und mit vorhandenen
Linux-Werkzeugen gelesen. Es gab keine Ausführung von Windows-Code, kein Wine,
keine VM, keine Gerätekommunikation, keine HID-Zugriffe und keine Installation
weiterer Pakete.

Die reproduzierbaren, read-only Ghidra-Exporte liegen in:

- `research/ghidra-scripts/ExportInfoHubLcdSender.java`
- `research/ghidra-scripts/ExportInfoHubXyuiJpeg.java`

Beispielaufruf nach dem einmaligen statischen PE-Import in ein git-ignoriertes
Ghidra-Projekt:

```text
analysis_tmp=$(mktemp -d /tmp/tuf-infohub-analysis.XXXXXX)
env XDG_CONFIG_HOME="$analysis_tmp/config" \
  /home/l/HeartdriveLAB/shared/tools/ghidra/ghidra_12.1_PUBLIC/support/analyzeHeadless \
  research/ghidra-projects infohub-1.0.0.15-ghidra12-1 \
  -process "ASUS InfoHub.exe" -readOnly -noanalysis \
  -scriptPath research/ghidra-scripts \
  -postScript ExportInfoHubLcdSender.java "$analysis_tmp/infohub.txt"

env XDG_CONFIG_HOME="$analysis_tmp/config" \
  /home/l/HeartdriveLAB/shared/tools/ghidra/ghidra_12.1_PUBLIC/support/analyzeHeadless \
  research/ghidra-projects xyui-infohub-1.0.0.15-ghidra12-1 \
  -process "XYUI.dll" -readOnly -noanalysis \
  -scriptPath research/ghidra-scripts \
  -postScript ExportInfoHubXyuiJpeg.java "$analysis_tmp/xyui.txt"
```

## Ergebnis in Kürze

InfoHub ordnet HID1 und HID2 nicht anhand der geparsten `&mi_`-Nummer zu,
sondern anhand von `HIDP_CAPS.OutputReportByteLength`: 441 Windows-API-Byte
werden HID1/Interface 0 zugeordnet, 1025 Byte HID2/Interface 1. Der
JPEG-Sender `0x00416bc0` erzeugt exakt die bereits aus v51 bekannte
`08 N 00 80`-/`08 i 00 00`-Folge. Jede Windows-`WriteFile`-Operation umfasst
1025 Byte: ein führendes Nullbyte als unnummerierte Report-ID plus den
1024-Byte-Report. Der letzte 1020-Byte-Payloadblock wird mit Nullen aufgefüllt.

Das Nutzerbild wird nicht unverändert übertragen. `XYUI.dll` rendert einen
neuen 320×320-Frame und encodiert diesen mit dem GDI+-JPEG-Encoder bei Qualität
60 oder 90. Nach dem letzten erfolgreichen OUT gibt es weder einen
16-Byte-Read noch eine Prüfung auf `08 81`. Auch ein Interface-0-`0x19` oder
ein Befehl `0x80..0x87` gehört in dieser InfoHub-Version nicht zum erfolgreichen
Bildtransfer.

## 1. HID1/HID2 und die Windows-HID-Grenze

### 1.1 Enumeration und Öffnen

`0x00422500` enumeriert mit SetupAPI die HID-Interfaceklasse
`{4d1e55b2-f16f-11cf-88cb-001111000030}`. Für jeden Pfad wird zunächst ein
Metadatenhandle ohne Lese-/Schreibzugriff geöffnet. VID, PID, Versionswert und
HID-Caps werden erfasst; eine im Pfad vorhandene Zeichenfolge `&mi_XX` wird
zwar als Zahl gespeichert, später bei der HID1/HID2-Auswahl aber nicht benutzt.

`0x00421df0` filtert auf VID `0x0b05` und PID `0x1c7b` und öffnet jeden
Kandidaten erneut über `0x00422970`:

```text
CreateFileA(path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            NULL, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, NULL)
```

`0x00422970` speichert aus `HIDP_CAPS` insbesondere:

| Handlefeld | Bedeutung |
| --- | --- |
| `+0x00` | Windows-Handle |
| `+0x08` | `OutputReportByteLength` |
| `+0x0c` | `InputReportByteLength` |
| `+0x10` | `FeatureReportByteLength` |

Die anschließende Zuordnung in `0x00421df0` lautet exakt:

| Windows-Ausgabelänge | InfoHub-Name | Objektfeld | Geräteinterface |
| ---: | --- | ---: | --- |
| `0x1b9` = 441 | HID1 | `+0x34` | Interface 0, 440 Drahtbyte |
| `0x401` = 1025 | HID2 | `+0x38` | Interface 1, 1024 Drahtbyte |

Damit wird die Interfacezuordnung durch die Reportgröße entschieden; `MI_00`
ist nur ein Diagnose-/Arrival-Match, keine Voraussetzung der HID1/HID2-
Klassifikation.

### 1.2 Gemeinsamer Writer und konkrete Größen

`0x00422b00` ist der einzige Writer dieses HID-Stacks. Ist der übergebene
Puffer kürzer als `OutputReportByteLength`, allokiert er einen Puffer der
vollen Caps-Länge, kopiert die Eingabe und füllt den Rest mit `00`. Dann folgt:

```text
WriteFile(handle, buffer, OutputReportByteLength, NULL, &overlapped)
GetOverlappedResult(handle, &overlapped, &transferred, TRUE)
```

Ein unmittelbarer Fehler außer `ERROR_IO_PENDING` oder ein fehlgeschlagenes
`GetOverlappedResult` liefert `-1` und markiert das Handle fehlerhaft.

- `0x00421ed0` ist der Interface-0-Adapter. Er baut einen Windows-Puffer mit
  führendem `00` und ruft den Writer für den 440-Byte-Datenpfad auf; die
  Caps-Länge erzwingt am Ende 441 API-Byte beziehungsweise 440 Drahtbyte.
- `0x00416bc0` baut den 1024-Byte-Interface-1-Report, stellt ihm explizit ein
  Nullbyte voran und übergibt direkt `0x401` = 1025 Byte.
- Keine HID-Funktion führt einen 16-Byte-Read aus. Die drei statischen
  `ReadFile`-Aufrufer `0x004290c0`, `0x00429150` und `0x004292a0` sind
  Datei-/Archivleser und benutzen kein HID-Handle. Das dynamisch geladene
  `HidD_GetFeature` wird nach dem Laden ebenfalls nicht aufgerufen.

## 2. Exakter Interface-1-Segmentbuilder

Der vollständige Sender liegt in `ASUS InfoHub.exe` bei `0x00416bc0`. Seine
Quelle ist der 409.600-Byte-Puffer bei `DeviceMainDlg+0x8b8`; der Konstruktor
`0x0040a7e0` allokiert ihn mit Größe `0x64000`. `GetLEDData` liefert zusätzlich
die exakte JPEG-Länge `L`.

Bytegenaue Host-Pseudobeschreibung des erfolgreichen Pfads:

```text
if not both_hids_connected or transfer_suppressed:
    return

ok, L = LEDModeCtrl.GetLEDData(jpeg_buffer)
if not ok:
    return

N = L / 1020
if L != N * 1020:
    N += 1

for i = 0 .. N-1:
    report[0..1023] = 00
    report[0] = 08
    if i == 0:
        report[1] = low8(N)
        report[2] = 00
        report[3] = 80
    else:
        report[1] = low8(i)
        report[2] = 00
        report[3] = 00

    report[4..1023] = jpeg_buffer[i*1020 .. i*1020+1019]
    windows_buffer = 00 || report

    if hid2_write(windows_buffer, 1025) <= 0:
        Sleep(100 ms)
        if hid2_write(windows_buffer, 1025) <= 0:
            send_hid1_failure_controlword(FF 01 00 00)
            return
```

Wichtige Präzisierungen:

- Der Befehl ist exakt `0x08`.
- Das erste Controlword ist `08 N 00 80`; Folgesegmente sind
  `08 i 00 00` mit `i = 1..N-1`.
- InfoHub berechnet `N = ceil(L/1020)` als 32-Bit-Integer, schreibt aber nur
  dessen Low-Byte in Byte 1. Ebenso wird nur das Low-Byte des Folgeindex
  geschrieben. Bytes 2 und die unteren sieben Bits von Byte 3 bleiben null;
  der Host nutzt also nur acht der firmwareseitig möglichen 23 Feldbits und
  prüft keinen Überlauf über 255.
- Jeder Payload ist exakt 1020 Byte groß. Es gibt kein Längenfeld für das
  letzte Segment und keinen gesonderten Abschlussreport.
- Ohne Fehler sind es exakt `N` Aufrufe von `WriteFile`, jeweils mit 1025
  API-Byte. Jeder einzelne Report darf nach 100 ms genau einmal wiederholt
  werden. Ein trotz solcher Retries vollständig erfolgreicher Transfer hat
  daher zwischen `N` und `2N` Bild-Writes; beim zweiten Fehlschlag desselben
  Reports wird abgebrochen und zusätzlich ein 441-Byte-HID1-Write versucht.
- Das API-Nullbyte ist eindeutig vorhanden. Es ist das von Windows HID für
  den unnummerierten Report erwartete Report-ID-Feld und gehört nicht zu den
  1024 Drahtbytes.
- `FF 01 00 00` auf HID1 ist ausschließlich der Pfad nach zwei
  fehlgeschlagenen HID2-Writes. Er wird nach einem erfolgreichen Bildtransfer
  nicht gesendet.

## 3. Letzter Block und Padding

Das Padding ist statisch vollständig bestimmt. `XYUI::LEDModeCtrl::GetLEDData`
bei `0x10052030` führt zuerst

```text
memset(caller_buffer, 0, 0x64000)
```

aus und kopiert danach nur die `L` JPEG-Bytes an den Pufferanfang. InfoHub
kopiert für jedes Segment trotzdem exakt 1020 Byte aus diesem Puffer. Deshalb
gilt für den letzten Payload:

```text
jpeg[L % 1020 verbleibende Bytes] || 00 ... 00
Paddinglänge = N * 1020 - L
```

Ist `L` ein exaktes Vielfaches von 1020, gibt es kein Padding. Andernfalls
sind sämtliche Bytes nach dem JPEG bis zum Ende des letzten 1020-Byte-Blocks
konkret `00`. Ein EOI-Scan findet nicht statt; die bekannte Streamlänge
bestimmt allein `N`.

## 4. JPEG-Erzeugung in XYUI.dll

Der Pfad führt direkt von `GetLEDData` zu
`XYUI::LEDModeCtrl::DrawHideControl` bei `0x10052930`:

1. `0x10054e30` erzeugt ein top-down 32-Bit-DIB mit exakt 320×320 Pixeln.
2. Der Frame wird mit schwarzem Hintergrund gerendert. Das geladene
   Nutzerbild beziehungsweise der aktive Animations-/Videoframe wird über den
   GDI+-Zeichenpfad skaliert/positioniert; Clock- und Overlaypfade können in
   denselben Frame zeichnen.
3. `0x10050530` sucht aus den installierten GDI+-Encodern anhand des exakten
   MIME-Strings `image/jpeg` die JPEG-Encoder-CLSID.
4. `GdipSaveImageToStream` encodiert den 320×320-Frame neu in einen
   `IStream`. Als einziger Encoderparameter wird
   `EncoderQuality={1d5be4b5-fa4a-452d-9cdd-5db35105e7eb}` mit Typ `Long`
   übergeben.
5. Qualität ist `60`, wenn der LED-Modus `1` oder `7` ist, sonst `90`. Das von
   InfoHub für den LCD-Sender verwendete `LEDModeCtrl` wird zunächst mit Modus
   `1` eingerichtet; spätere Modusänderungen können die Auswahl verändern.
6. `IStream::Stat` liefert die fertige JPEG-Länge. Genau diese Länge wird in
   `LEDModeCtrl+0x1bc` gespeichert und anschließend von `GetLEDData` an
   InfoHub zurückgegeben. Die Länge ist also vor der Segmentierung bekannt.

Das ausgewählte Original-JPEG wird folglich nicht bytegleich gesendet. Selbst
bei einem JPEG als Eingabe entsteht ein neu gerenderter und neu encodierter
320×320-Frame. Baseline/Progressive, YCbCr-Subsampling und die konkrete
Quantisierung außer dem Qualitätswert werden im Programm nicht gewählt,
sondern dem externen Windows-GDI+-JPEG-Codec überlassen. Statisch belegt sind
daher JPEG/MIME, 320×320 und Qualität 60/90; ein bestimmter SOF-Typ oder
4:4:4/4:2:2/4:2:0 ist aus diesen beiden PE-Dateien allein nicht beweisbar.

## 5. Interface-1-IN nach dem Bild

Nach dem letzten erfolgreichen Segment verzweigt `0x00416bc0` unmittelbar zum
Funktionsende. Es gibt:

- keinen `ReadFile`-Aufruf,
- keinen 16-Byte-Puffer,
- keinen Timeout für eine Antwort,
- keinen Vergleich mit `08 81`,
- keinen Drain-Read und keine weiteren Reads,
- keine Abhängigkeit des weiteren Hostablaufs von einem Interface-1-IN-Inhalt.

InfoHub 1.0.0.15 ignoriert damit die von v51 bekannte frühe
Queueannahme-/Startnachricht vollständig. Die einzige Wartezeit im Sender sind
100 ms zwischen erstem fehlgeschlagenen Write und genau einem Retry; sie ist
kein Antworttimeout.

## 6. Begleitende Interface-0-Befehle

Der normale Worker `0x00414ff0` ruft den JPEG-Sender nur in seinem Leerlaufzweig
auf. Ereignisgesteuerte Interface-0-Aktionen liegen in einem alternativen
Zweig desselben Workeraufrufs und sind nicht als Vor-/Nachsequenz an einen
erfolgreichen JPEG-Transfer gekoppelt.

Alle statischen Aufrufer des HID-Writers in diesem Stack ergeben:

| Funktion | Interface | belegte Controlwords |
| --- | --- | --- |
| `0x004148d0` | HID1 | `1F 01 00 80` |
| `0x00416a00` | HID1 | `10 01 00 80`, `12 01 00 80` |
| `0x00416bc0` | HID2 | JPEG `08 ...`; bei endgültigem Fehler HID1 `FF 01 00 00` |

Damit gilt für genau einen erfolgreichen Bildtransfer:

- kein zwingender Interface-0-Befehl davor oder danach;
- kein Interface-0-Unterbefehl `0x19`;
- kein Befehlsbyte `0x80..0x87`;
- keine hostseitige Änderung von `config+0x108` beziehungsweise der
  Decoderquellen-Lease;
- die sichtbaren `0x80`-Bytes in Byte 3 sind ausschließlich das
  Erstsegmentbit des gemeinsamen Controlwords, keine `0x80`-Befehlsfamilie.

Die Befehle `0x10`, `0x12` und `0x1f` sind separate Modus-/Sleep-Aktionen.
`FF 01 00 00` ist eine Fehlerbenachrichtigung nach abgebrochenem HID2-Transfer.
Keine davon ist für den erfolgreichen JPEG-Pfad erforderlich.

## 7. Vergleich mit den bestätigten v51-Befunden

| Befund | Bewertung |
| --- | --- |
| Interface 0 = 440 Drahtbyte, Interface 1 = 1024 OUT | exakt übereinstimmend |
| 4-Byte-Controlword plus 1020 Payload | exakt übereinstimmend |
| Befehl `0x08`; erstes Wort `08 N 00 80` | exakt übereinstimmend |
| Folgeindex `1..N-1` | exakt übereinstimmend |
| vollständige 1020-Byte-Kopie auch im letzten Segment | exakt übereinstimmend |
| ursprüngliche JPEG-Länge wird nicht zum Gerät übertragen | exakt übereinstimmend |
| Windows-API-Puffer `00 || report[1024]` | hostseitig neu bestätigt |
| letzter Suffix besteht ausschließlich aus Nullbytes | hostseitig neu bestätigt |
| 320×320-Neurendering und GDI+-JPEG-Qualität 60/90 | hostseitig neu bestätigt |
| Firmwarefeld ist 23 Bit, InfoHub schreibt nur Byte 1 | abweichend, aber für normale `N < 256` kompatibel |
| v51 sendet früh `08 81`, InfoHub liest Interface 1 nie | abweichend; die Nachricht ist keine Hostvoraussetzung |
| v51-Lease `config+0x108`, InfoHub sendet hier kein `0x19` | hostseitig neu bestätigt; Bootdefault 5000 bleibt maßgeblich |
| v51 akzeptiert den Block unabhängig von EOI/Restlänge | kompatibel; InfoHub segmentiert ausschließlich nach Streamlänge |

## 8. Verbleibende Lücken und Referenzcapture

Für die Rekonstruktion des InfoHub-1.0.0.15-Senders sind Reportframing,
Segmentierung, Indizes, Padding, JPEG-Längenquelle und fehlender IN-Read
statisch geschlossen. Ein ASUS-Capture ist dafür nicht mehr nötig.

Vor einem eigenen Write gegen das reale Gerät mit gemeldetem Firmwarestand
v49 bleibt ein passiver ASUS-Referenzcapture dennoch erforderlich. Er soll nun
enger beantworten:

- ob v49 den aus v51 rekonstruierten `0x08`-Consumer und die frühe `08 81`-
  Nachricht tatsächlich identisch implementiert;
- welchen SOF-Typ und welches Subsampling der konkrete Windows-GDI+-Codec zur
  Laufzeit erzeugt;
- ob die reale Anwendungskonfiguration außerhalb des isolierten Senderpfads
  zeitlich benachbarte Modusaktionen auslöst;
- wann der sichtbare Displaycommit erfolgt, weil weder Firmware noch Host
  einen belastbaren Decoder-Done-Status bereitstellen.

Der Capture ist damit keine Lücke des statischen Host-Builders mehr, sondern
eine Sicherheits- und v49-Laufzeitvalidierung.
