# Einmaliger JPEG-Test für LCD-Befehl `0x08`

## Zweck und Status

`src/test_jpeg_0x08.py` implementiert den eng begrenzten Hostpfad für genau
einen späteren JPEG-Transfer an das ASUS-TUF-AIO-LCD. Standardmäßig arbeitet
das Werkzeug ausschließlich als Preview/Dry-Run. Die Implementierung und ihre
Offline-Tests autorisieren keine Gerätekommunikation.

Während der Erstellung wurden keine HID-Geräte geöffnet, keine HID-Writes
ausgeführt, keine Schreibrechte aktiviert und keine Pakete installiert. Ein
echter Lauf benötigt einen neuen, ausdrücklich auf Gerät, Referenz-JPEG und
Verfahren begrenzten Auftrag.

## Feste Sicherheitsgrenzen

- einziges unterstütztes Command: `0x08`;
- einziges Ziel: VID `0x0b05`, PID `0x1c7b`, USB-Interface 1;
- keine feste `/dev/hidrawX`-Nummer;
- unnumbered HID-OUT-Report mit exakt 1024 Drahtbyte;
- Linux-hidraw-Puffer exakt `00 || 1024 Byte`, insgesamt 1025 Byte;
- genau eine explizit angegebene JPEG-Datei;
- die JPEG-Eingabe muss eine reguläre Datei sein;
- `1 <= N <= 4`;
- genau ein Frame;
- kein Interface 0, kein Read, kein Retry, kein Recovery-Command und kein
  weiterer Befehl;
- keine Firmware-, SPI-, Flash-, Bootloader- oder Konfigurationsfunktion;
- bei jedem Fehler oder Short Write sofortiger Abbruch über den
  Descriptor-Close-Pfad.

Das Programm enthält genau eine Quelltextstelle mit `os.write()`. Sie liegt in
einer Schleife über das vorab vollständig erzeugte, unveränderliche Segment-
Tuple. Dieses Tuple besitzt höchstens vier Einträge. Bei einer Exception oder
einem Rückgabewert ungleich 1025 endet die Funktion unmittelbar; es existiert
kein Retrypfad.

## Offline-JPEG-Validierung

Die vollständige Datei wird vor der Geräteauswahl gelesen, gehasht und direkt
über ihre JPEG-Marker geprüft. Es erfolgt keine automatische Konvertierung und
keine JPEG-Dekodierung.

Zulässig ist nur die konservative Untermenge:

- Länge größer null und höchstens 4080 Byte;
- SOI `ff d8` am Dateianfang;
- JFIF-APP0 vorhanden;
- vollständiger JFIF-1.x-Header ohne Thumbnail, gültiger Dichteeinheit und
  von null verschiedenen Dichten;
- genau ein SOF0 `ff c0`, kein SOF2 und kein anderer SOF-Typ;
- 8 Bit Sample Precision;
- exakt 320×320 Pixel;
- drei Komponenten mit JFIF-YCbCr-4:2:0-Struktur:
  Y `2x2`, Cb `1x1`, Cr `1x1`;
- genau zwei gültige 8-Bit-Quantisierungstabellen mit IDs 0 und 1;
- exakt die vier üblichen Standard-Huffmantabellen und konservative
  SOS-Tabellenselektoren; die Tabellenbytes werden einzeln gegen festgelegte
  SHA-256-Werte geprüft;
- genau ein Baseline-Sequential-Scan;
- keine arithmetische Codierung und kein Restartintervall;
- keine zusätzlichen APP-, Metadaten- oder sonstigen Headersegmente außerhalb
  der festen Allowlist APP0/DQT/SOF0/DHT/SOS;
- syntaktisches EOI `ff d9` unmittelbar am Dateiende;
- keine Bytes nach EOI;
- `N = ceil(L/1020)` im Bereich `1..4`.

Der Parser unterscheidet in den Scandaten echte Marker von `ff 00`-Byte-
Stuffing. Ein zufälliges `ff d9` außerhalb der syntaktischen Scanbegrenzung
wird daher nicht als ausreichendes EOI akzeptiert.

## Paketbildung

Die Paketbildung besteht aus reinen Funktionen und greift nicht auf sysfs,
udev oder hidraw zu.

Für JPEG-Länge `L` gilt:

```text
N = ceil(L / 1020)
```

Segment 0:

```text
Draht:  08 (N & 0xff) 00 80 | 1020 Payloadbyte
hidraw: 00 | Drahtreport
```

Segment `i=1..N-1`:

```text
Draht:  08 (i & 0xff) 00 00 | 1020 Payloadbyte
hidraw: 00 | Drahtreport
```

Der letzte Payload besteht aus dem JPEG-Rest und ausschließlich `00` bis zur
Länge 1020. Interne Invarianten rekonstruieren das JPEG aus den Payloads und
verwerfen jedes Nonzero-Padding, jede falsche Controlfolge und jede von
1024/1025 abweichende Reportlänge.

## Dynamische Geräteprüfung

Die Preview sucht über `discover_device.py` nach VID/PID und ausschließlich
Interface 1. Ein dynamisch gefundener Kandidat ist nur verwendbar, wenn:

- VID/PID exakt stimmen;
- Interface 1 bestätigt ist;
- der Reportdeskriptor 16 Byte IN und 1024 Byte OUT ergibt;
- keine Report-ID deklariert ist;
- der Pfad ein dynamisch ermittelter absoluter `/dev/hidraw*`-Pfad ist.

Der Dry-Run öffnet diesen Pfad nicht. In einem später autorisierten Live-Lauf
wird der Knoten nur mit `O_WRONLY | O_NONBLOCK` geöffnet. Unmittelbar vor
jedem einzelnen Write werden Zeichengerät, sysfs-Gerätenummer, VID/PID,
Interface, Reportgrößen und fehlende Report-ID erneut geprüft. Erst danach ist
die einzige `os.write()`-Stelle erreichbar.

## Preview und Dry-Run

Standardaufruf mit der eingefrorenen Referenzdatei:

```text
python3 -B src/test_jpeg_0x08.py \
  tests/fixtures/lcd-0x08-reference.jpg
```

Explizit gleichwertiger Dry-Run:

```text
python3 -B src/test_jpeg_0x08.py --dry-run \
  tests/fixtures/lcd-0x08-reference.jpg
```

Beide Varianten geben aus:

- aufgelösten JPEG-Pfad und SHA-256;
- JPEG-Länge, Geometrie, SOF-Typ und Komponenten;
- `N` und Paddinglänge;
- alle vier Controlbytes jedes Segments;
- Zielgerät und Interface, falls ein gültiger Kandidat gefunden wurde;
- Anzahl der geplanten Writes.

Sie öffnen den hidraw-Knoten nicht. `--dry-run` und der Risikoschalter sind
absichtlich nicht kombinierbar. Langoptions-Abkürzungen sind deaktiviert; nur
der vollständig ausgeschriebene `--i-understand-the-risk`-Schalter kann den
späteren Livezweig erreichen.

## Eingefrorenes Referenz-JPEG

Das lokale ImageMagick 7.1.2-27 mit libjpeg-turbo 3.1.3 konnte ohne
Paketinstallation ein geeignetes Referenzbild erzeugen:

```text
magick -size 320x320 xc:'#202020' \
  -fill '#e0e0e0' -draw 'rectangle 128,128 191,191' \
  -type TrueColor -colorspace sRGB -sampling-factor 2x2 \
  -quality 60 -interlace none -define jpeg:colorspace=YCbCr \
  -define jpeg:optimize-coding=false -strip \
  tests/fixtures/lcd-0x08-reference.jpg
```

Die Grafik ist achromatisch: ein 64×64 Pixel großes helles Rechteck auf
dunklem Hintergrund. Seine Kanten liegen auf 16-Pixel-MCU-Grenzen.

Offline bestätigte Daten:

| Merkmal | Wert |
| --- | --- |
| SHA-256 | `5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866` |
| JPEG-Länge | 2236 Byte |
| Geometrie | 320×320 |
| SOF / Präzision | SOF0 / 8 Bit |
| Komponenten | 3 |
| Sampling | `2x2,1x1,1x1` = 4:2:0 |
| `N` | 3 |
| Nullpadding | 824 Byte |
| Controlbytes | `08 03 00 80`, `08 01 00 00`, `08 02 00 00` |

Der Test `test_reference_jpeg_is_frozen_and_valid` bindet SHA-256, Struktur,
`N` und Padding an diese Datei. Während Implementierung und Code-Review wurde
sie nicht gesendet; im später gesondert autorisierten Live-Test wurde sie
genau einmal übertragen.

## Ausgeführter einmaliger Live-Test

Der gesondert autorisierte Einmaltest verwendete folgenden Aufruf:

```text
python3 -B src/test_jpeg_0x08.py --i-understand-the-risk \
  tests/fixtures/lcd-0x08-reference.jpg
```

Der Erfolgsweg ist dann fest:

1. JPEG vollständig offline validieren und alle Puffer erzeugen.
2. Gerät dynamisch als `0b05:1c7b`, Interface 1 auswählen.
3. Descriptor einmal öffnen.
4. Vor jedem Segment Identität und Reportvertrag erneut validieren.
5. Genau `N=3` synchrone Writes mit jeweils 1025 Byte ausführen.
6. Descriptor schließen.
7. Keinen Read, Retry, weiteren Command oder zweiten Frame ausführen.

Dieser Ablauf wurde genau einmal ausgeführt. Auf dem realen Gerät mit
Versionswert `0x0049` und `bcdDevice 0.49` erschien sichtbar das erwartete
weiße Quadrat. Der vollständige Ergebnisbericht steht in
`research/reports/lcd-0x08-live-test-01.md`. Es gab keinen zweiten Frame;
temporäre Schreibrechte wurden unmittelbar danach entfernt.

## Sofortige Abbruchbedingungen

Vor dem ersten Write wird abgebrochen bei:

- ungültigem oder nicht eindeutigem Gerät;
- anderem Interface;
- abweichenden Reportgrößen oder vorhandener Report-ID;
- ungültigem JPEG, Hash-/Dateiwechsel oder `N>4`;
- inkonsistenten Controlbytes, Payloads oder Pufferlängen;
- fehlender Schreibberechtigung. Das Programm verändert keine Rechte.

Nach dem Öffnen wird sofort geschlossen und ohne weiteren Write abgebrochen
bei:

- jeder fehlgeschlagenen erneuten Geräteprüfung;
- jeder Write-Exception;
- jedem Rückgabewert ungleich 1025;
- Disconnect oder Benutzerabbruch.

Es wird nicht versucht, einen begonnenen Transfer zu vervollständigen, einen
Write zu wiederholen oder das Gerät durch einen anderen Befehl zu reparieren.

## Offline-Tests

Ausführung:

```text
python3 -B -m unittest discover -s tests -v
```

Die Suite prüft mindestens:

- Paketanzahlen `N=1`, `N=2` und `N=4`;
- ausschließliches Nullpadding;
- Erst- und Folge-Controlwords;
- exakt 1024 Draht- und 1025 hidraw-Byte pro Segment;
- Ablehnung falscher Geometrie;
- Ablehnung von SOF2;
- Ablehnung von SOF1, weiteren SOF-Typen, zusätzlichen APP-Markern,
  unvollständigem JFIF und fehlenden Quantisierungstabellen;
- Ablehnung fehlenden EOI, Dateinachlauf und fehlerhafter Segmentlängen;
- Ablehnung falscher VID/PID-, Interface-, Reportgrößen- und Report-ID-
  Metadaten;
- Ablehnung von `N>4`;
- Struktur und SHA-256 des Referenz-JPEG;
- statisch genau eine `os.write()`-Stelle;
- Standard-Preview und `--dry-run` erreichen kein `os.open()`.
- `--help`, verkürzte Risikoschalter und unzulässige Argumentkombinationen
  erreichen kein `os.open()`;
- Writefehler nach einem bereits erfolgreichen Segment verhindert alle
  verbleibenden Segmente.

Keine Testfunktion öffnet `/dev/hidraw*`.

## Ergebnis des statischen Code-Reviews

Der unabhängige Review ist unter
`research/reports/test-jpeg-0x08-code-review.md` dokumentiert und endete nach
begrenzten Validator- und CLI-Korrekturen mit **PASS**. Die Offline-Suite
umfasst nun 37 erfolgreiche Tests.

Der Review bestätigte genau eine `os.write()`-Callsite, höchstens vier Writes
pro Prozesslauf, keinen Retry-/Recovery-/Reconnectpfad und keinen Zugriff auf
Interface 0. „Einmalig“ ist innerhalb eines Prozesslaufs technisch erzwungen;
eine erneute manuelle Programmausführung bleibt organisatorisch zu verhindern.

## Grenzen nach dem Live-Lauf

- Kein weiterer Lauf oder zweiter Frame ist durch den erfolgreichen Einmaltest
  freigegeben.
- Animationen, mehrere Frames, langfristiger Dauerbetrieb, Fehlerverhalten und
  andere JPEG-Profile sind nicht getestet und aus dem Ergebnis nicht
  ableitbar.
- Queuegrenzen, Decoder-Lease, interne Queuefreigabe und persistente
  Pfaderreichbarkeit sind für v49 nicht dynamisch beobachtet; die zugehörigen
  Detailbefunde stammen aus der statischen v51-Analyse.

Eine fünfsekündige Interface-1-IN-Quiet-Phase ist nicht vorgesehen. Ohne
Auswertung eines IN-Reports liefert sie keinen belegten Sicherheitsgewinn und
kann weder freie Decoderqueue noch abgelaufene Lease bestätigen.
