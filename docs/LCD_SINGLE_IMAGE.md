# Einzelbild-Sender für das ASUS-AIO-LCD

## Zweck

`src/set_lcd_image.py` validiert und überträgt höchstens ein bereits passendes
JPEG an das LCD der ASUS TUF GAMING LC III 360 ARGB LCD. Standardmäßig zeigt
das Programm ausschließlich eine Preview. Es konvertiert keine Bilder,
startet keinen Hintergrunddienst und besitzt keinen Animations- oder
Wiederholungspfad.

Der Transport beruht auf dem erfolgreichen realen Einmaltest aus
`research/reports/lcd-0x08-live-test-01.md`. Auf dem Gerät mit VID:PID
`0b05:1c7b`, Versionswert `0x0049` und `bcdDevice 0.49` erschien nach drei
Interface-1-Writes sichtbar das erwartete Referenzbild.

## Modulstruktur

- `src/lcd_transport.py` enthält dynamische Geräteerkennung, den engen
  JPEG-Validator, die reine Segmentbildung und `send_frame_once()`.
- `src/set_lcd_image.py` ist die Preview-by-default-CLI für ein einzelnes
  bereits kompatibles JPEG.
- `src/test_jpeg_0x08.py` bleibt das konservative Safety-Werkzeug. Es verwendet
  dieselben geprüften Bausteine, behält aber seine zusätzliche Grenze `N<=4`
  und den Schalter `--i-understand-the-risk`.

## Bestätigtes Transportformat

Das Ziel wird dynamisch als VID `0x0b05`, PID `0x1c7b`, ausschließlich
USB-Interface 1 ermittelt. Ein fester `/dev/hidrawX`-Pfad wird nicht
verwendet. Vor jedem Write werden Identität, Interface, Zeichengerätzuordnung,
16-Byte-IN-/1024-Byte-OUT-Reportgrößen und der unnummerierte HID-Report erneut
geprüft.

Für eine JPEG-Länge `L` gilt:

```text
N = ceil(L / 1020), 1 <= N <= 200
```

Jeder 1024-Byte-Drahtreport besteht aus vier Controlbytes und 1020
Payloadbytes:

```text
Segment 0: 08 N 00 80 | erste 1020 JPEG-Bytes
Segment i: 08 i 00 00 | nächste 1020 JPEG-Bytes, i=1..N-1
```

Der letzte Payload enthält den JPEG-Rest und ausschließlich Nullbytes bis 1020
Byte. Der Linux-hidraw-Puffer ist immer exakt 1025 Byte lang:

```text
00 || 1024-Byte-Drahtreport
```

## Zulässige JPEGs

Die erste Produktstufe akzeptiert ausschließlich reguläre Dateien mit:

- exakt 320×320 Pixeln;
- SOF0/Baseline und 8 Bit Präzision;
- JFIF-YCbCr mit exakt drei Komponenten und 4:2:0-Sampling;
- den vier geprüften Standard-Huffmantabellen;
- 8-Bit-Quantisierungstabellen 0 und 1;
- genau einem Baseline-Scan und abschließendem EOI ohne Dateinachlauf;
- höchstens 200 Transportsegmenten beziehungsweise 204000 JPEG-Bytes.

Progressive und andere SOF-Varianten, zusätzliche APP-Metadaten,
Restartintervalle, arithmetische Codierung und abweichende Komponenten- oder
Samplingmodelle werden abgelehnt. Die vorhandene Referenzdatei
`tests/fixtures/lcd-0x08-reference.jpg` bleibt gültig.

## Preview

```text
python3 -B src/set_lcd_image.py bild.jpg
```

Die Preview gibt Datei, SHA-256, JPEG-Länge, Geometrie, JPEG-Profil,
Segmentzahl, Nullpadding, dynamisch gefundenes Ziel und geplante Write-Anzahl
aus. Sie öffnet kein hidraw-Gerät und sendet nichts.

## Expliziter Einzeltransfer

Nur ein gesondert autorisierter Aufruf mit `--apply` erreicht den
Transferpfad:

```text
python3 -B src/set_lcd_image.py --apply bild.jpg
```

Ein CLI-Aufruf kann `send_frame_once()` genau einmal aufrufen. Der Erfolgsweg
führt exakt `N` synchrone Writes für einen Frame aus. Bei der ersten
fehlgeschlagenen Revalidierung, Write-Exception oder einem Rückgabewert
ungleich 1025 wird sofort abgebrochen und der Descriptor geschlossen. Es gibt
kein Nachsenden, keinen Retry und keinen zweiten Frame.

Dieser Dokumentations- und Implementierungsstand ist keine Freigabe für einen
Live-Lauf. Während des Tickets wurde kein hidraw-Gerät geöffnet.

## Sicherheitsgrenzen

Der Einzelbild-Sender unterstützt ausschließlich Command `0x08` auf Interface
1. Er besitzt:

- keinen Interface-0-Zugriff und keinen IN-Read;
- keine Unterstützung für `0x19`, `0x80..0x87` oder andere Commands;
- keine Firmware-, SPI-, Flash- oder Konfigurationsfunktion;
- keinen Retry, Reconnect oder Recovery-Command;
- keine Animation, Mehrfachframe-Schleife oder Dauerschleife;
- keinen Hintergrunddienst und keine Änderung von Geräteberechtigungen.

Es gibt genau eine `os.write()`-Callsite im gesamten neuen JPEG-Senderpfad,
zentral in `send_frame_once()`. Pro Frame sind höchstens 200 Writes erreichbar.

## Bekannte Einschränkungen und nächster Ausbau

Es findet absichtlich keine automatische Bildkonvertierung statt. Vor einer
solchen Erweiterung müssen separat festgelegt und getestet werden:

- deterministische Skalierung beziehungsweise Crop/Letterboxing auf 320×320;
- definierter Farbraum JFIF-YCbCr und 4:2:0-Sampling;
- SOF0/Baseline, 8 Bit und kompatible Standard-Huffmantabellen;
- kontrollierte JPEG-Qualität und eine harte Ergebnisgrenze von 204000 Byte;
- erneute Validierung des erzeugten JPEGs vor jeder Preview oder Übertragung;
- Offline-Fixtures für Orientierung, Alpha-Behandlung, Farbraum und
  Größenfehler.

Animationen, mehrere Frames und Dauerbetrieb bleiben ausdrücklich außerhalb
dieser Stufe und benötigen eine eigene Sicherheits- und Timingbewertung.
