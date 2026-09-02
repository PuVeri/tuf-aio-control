# Statischer Safety- und Regression-Review des Einzelbild-Senders

Datum: 2026-09-02  
Ergebnis: **PASS**

## Umfang und Ausführungsgrenze

Geprüft wurden `src/lcd_transport.py`, `src/set_lcd_image.py`, das konservative
Werkzeug `src/test_jpeg_0x08.py`, die Offline-Suite und der eingefrorene
Live-Test-Referenztransfer. Während des Reviews wurde kein hidraw-Gerät
geöffnet, keine Gerätekommunikation ausgeführt, keine Schreibberechtigung
aktiviert und kein Live-Test gestartet. Sämtliche Writepfadtests verwendeten
Mocks.

Es wurde kein Safety- oder Correctness-Fehler im Produktionscode gefunden.
Zwei konkrete Testabdeckungslücken wurden geschlossen:

- ein zusammenhängender bytegenauer Golden-Test für alle drei Buffer des
  erfolgreichen Referenztransfers;
- ein expliziter CLI-Test, der die Abkürzung `--app` für `--apply` ablehnt.

## 1. Bytevergleich mit dem erfolgreichen Live-Test

Die lokal geprüfte Datei
`tests/fixtures/lcd-0x08-reference.jpg` besitzt 2236 Byte und SHA-256:

```text
5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866
```

`lcd_transport.build_segments()` erzeugt exakt drei Buffer:

| Segment | hidraw-Präfix und Controlword | JPEG-Bereich | Padding | Bufferlänge | SHA-256 des gesamten hidraw-Buffers |
| --- | --- | --- | --- | --- | --- |
| 0 | `00 08 03 00 80` | Byte 0..1019 | 0 | 1025 | `3112d908a428241a47886505bd261bb9a5e37e107504d46d029ae36578ba357e` |
| 1 | `00 08 01 00 00` | Byte 1020..2039 | 0 | 1025 | `201e5b73689601724004a75d6d30c7e307a364d6e103a19661fdc211ad2257d1` |
| 2 | `00 08 02 00 00` | letzte 196 Byte | 824 × `00` | 1025 | `3745175ac8b0ca9d4604c55ba6950ed4e801fd10ea986794d62ce659105db864` |

Die Konkatenation der drei 1020-Byte-Payloads stimmt bis Byte 2235 bytegenau
mit dem Original-JPEG überein. Der verbleibende Suffix ist genau 824 Byte lang
und vollständig null. Damit ist der vom neuen Modul erzeugte Transfer
bytegleich zu dem im erfolgreichen Live-Test dokumentierten Transfer.

## 2. Geräteerkennung und Revalidierung

Die Konstanten und alle Auswahlpfade sind fest auf VID `0b05`, PID `1c7b`
und Interface 1 begrenzt. `discover_lcd_interface()` filtert bereits die
rein lesenden Discovery-Ergebnisse auf Interface 1 und akzeptiert nur genau
einen Treffer. Es verwendet keinen festen nummerierten hidraw-Pfad.

`device_validation_error()` verlangt zusätzlich:

- exakt VID/PID `0b05:1c7b`;
- Interface 1;
- 16 Byte Input- und 1024 Byte Outputreport;
- keine Report-ID;
- einen dynamisch ermittelten absoluten `/dev/hidraw*`-Knoten.

`send_frame_once()` führt diese Prüfung vor `os.access()` und `os.open()` aus.
Ein Interface-0-Objekt oder falsche Reportmetadaten können daher nicht geöffnet
werden. Nach dem Open prüft `validate_open_target()` vor jedem möglichen Write
erneut Metadaten, Zeichengerättyp, sysfs-Gerätenummer, dynamischen Pfad und
Reportvertrag. Die Discovery-Aufrufe verwenden `include_udev=False`; im neuen
Pfad ist damit auch der optionale `udevadm`-Subprozess nicht erreichbar.

## 3. `send_frame_once()`

Im gesamten neuen JPEG-Pfad aus `lcd_transport.py`, `set_lcd_image.py` und
`test_jpeg_0x08.py` existiert genau eine `os.write()`-Callsite. Sie liegt in
`send_frame_once()`.

Vor dem Öffnen werden JPEG und alle Segmente vollständig validiert. Das
Segmenttuple enthält durch die harte Grenze höchstens 200 Elemente. Die einzige
Transferscheife iteriert genau einmal über dieses Tuple; ihr Erfolgsweg besitzt
daher exakt `N` und höchstens 200 Writes. Jeder Buffer wird unmittelbar vor dem
Write erneut als Teil des unveränderten Gesamttransfers geprüft.

Bei Revalidierungsfehler oder Write-Exception verlässt eine Exception sofort
die Schleife. Ein Rückgabewert ungleich 1025 löst ebenfalls unmittelbar
`LcdTransportError` aus. Es existiert kein Sprung zurück, Retry, Reconnect,
Recovery-Write oder Folgeframe. Der Descriptor-Close steht im `finally`-Block
und wird auf Erfolg, Short Write, Write-Exception, Revalidierungsfehler und
Abbruch ausgeführt. Es gibt keinen `os.read()`- oder sonstigen IN-Pfad.

## 4. Einzelbild-CLI

`set_lcd_image.py` akzeptiert genau ein positionales JPEG und den einzelnen
optionalen Schalter `--apply`. `ArgumentParser(allow_abbrev=False)` verhindert
Abkürzungen; der neue Regressionstest bestätigt insbesondere, dass `--app`
mit Exitcode 2 abgelehnt wird, bevor ein Gerät geöffnet werden kann.

Ohne `--apply` endet der Pfad nach Offline-Validierung, rein lesender Discovery
und Preview. Ein gemockter Test lässt jedes `os.open()` oder
`send_frame_once()` in diesem Pfad hart fehlschlagen und bestätigt, dass beide
nicht erreicht werden. Ungültige JPEGs enden bereits vor Discovery.

Mit `--apply` gibt es genau eine syntaktische Callsite zu `send_frame_once()`
und keine CLI-Schleife. Es gibt weder Dateiliste, Watch-Modus, Thread,
Hintergrundfunktion noch einen zweiten Frameaufruf.

## 5. Regression des konservativen Safety-Werkzeugs

`test_jpeg_0x08.py` definiert weiterhin lokal `MAX_SEGMENTS = 4`. Seine Wrapper
übergeben diese Grenze ausdrücklich an `segment_count()`, `validate_jpeg()`,
`build_segments()`, `validate_transfer_invariants()` und `load_jpeg()`.
`N=5` wird weiterhin abgelehnt. Erst nach dieser strengeren Vorprüfung könnte
das Werkzeug die allgemeine Transferfunktion erreichen. Die allgemeine Grenze
`N<=200` weicht den Safety-Test daher nicht auf.

## 6. Safety-Suche

Die statische Suche über die drei neuen beziehungsweise refaktorierten Module
ergab:

- einzige Befehlskonstante: `COMMAND = 0x08`;
- `0x80` erscheint ausschließlich als Erstsegmentbit im Controlword, nicht als
  Command;
- keine Commands `0x19` oder `0x80..0x87`;
- kein Interface-0-Auswahl- oder Öffnungspfad;
- kein SPI-, Flash-, Firmware- oder Konfigurationspfad;
- kein `subprocess`, Shell- oder Netzwerkzugriff im erreichbaren Senderpfad;
- kein Retry, Reconnect, Recovery, Watcher, Thread oder Hintergrunddienst;
- keine weitere hidraw-Write-Callsite;
- ausschließlich eingabelängenbegrenzte Parser-Schleifen und die auf
  `N<=200` begrenzte Transferscheife, keine Dauerschleife.

Projektweit existieren außerhalb dieses JPEG-Pfads weiterhin die bekannte
separate `os.write()`-Callsite des `0x87`-Safety-Werkzeugs und eine
Datei-Write-Callsite des passiven Capture-Werkzeugs. Beide sind aus dem neuen
Einzelbild-Sender nicht aufrufbar.

## 7. Offline-Regression

Die vollständige Suite endet mit **48/48 erfolgreichen Tests**. Abgedeckt sind
unter anderem:

- bytegenauer Golden-Transfer der Live-Test-Fixture;
- `N=1/2/3/4`, größere Werte und gültiges `N=200`;
- Ablehnung von `N=201` und Beibehaltung von `N<=4` im Safety-Test;
- Nullpadding und vollständige JPEG-Rekonstruktion;
- falsche VID/PID-, Interface-, Reportgrößen- und Report-ID-Metadaten;
- Write-Exception und Short Write ohne Retry;
- Fehler im zweiten Segment nach einem erfolgreichen ersten Write ohne
  Folge-Writes;
- Descriptor-Close auf Erfolgs- und Fehlerpfaden;
- Preview ohne Geräteöffnung oder Transfer;
- ungültiges JPEG vor Discovery;
- genau ein Frameaufruf mit `--apply` und Ablehnung von `--app`.

Keine Testfunktion öffnete ein echtes `/dev/hidraw*`-Gerät.

## Verbleibende Risiken

- Empirisch bestätigt ist nur die 2236-Byte-Referenzdatei mit `N=3`; größere
  JPEGs bis `N=200` sind statisch und offline abgesichert, aber nicht live
  getestet.
- Der reale v49-interne Fehler-, Timeout-, Queue- und Decoder-Lease-Pfad bleibt
  unbekannt; die tieferen statischen Befunde stammen aus v51.
- Ein externer Prozess könnte parallel auf das LCD schreiben. Der Sender
  implementiert absichtlich weder Locking noch Recovery.
- Ein manueller zweiter Programmaufruf bleibt organisatorisch möglich. Pro
  Prozessaufruf ist technisch nur ein Frame erreichbar.
- Die übliche unvermeidbare Race-Lücke zwischen letzter Revalidierung und dem
  folgenden Kernel-Write bleibt bestehen.

Diese Restrisiken ändern das PASS für die geforderte statische Gleichheit und
die eng begrenzte Einzelbildarchitektur nicht und erteilen keine Live-Freigabe.
