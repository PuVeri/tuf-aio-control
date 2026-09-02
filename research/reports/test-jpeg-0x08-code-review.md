# Statischer Safety- und Correctness-Review des JPEG-0x08-Testprogramms

Stand: 2026-09-02

## Zweck und Sicherheitsgrenze

Gegenstand war ein unabhängiger statischer Review von
`src/test_jpeg_0x08.py`, seinen Offline-Tests, der eingefrorenen JPEG-Fixture
und den maßgeblichen Projektbefunden. Während des Reviews wurde kein
hidraw-Gerät geöffnet, keine Gerätekommunikation durchgeführt, kein HID-Write
ausgeführt und keine Schreibberechtigung verändert. Der Livepfad und der reale
Geräte-Preview wurden nicht gestartet.

## Ergebnis

**PASS nach fünf begrenzten Korrekturen.**

Der Programm-Kontrollfluss kann pro Prozesslauf nur einen vorab vollständig
validierten `0x08`-JPEG-Transfer mit `1 <= N <= 4` erreichen. Es gibt genau
eine `os.write()`-Callsite, keine Retrykante und keinen Pfad zu einem anderen
Command oder Interface 0. Writefehler, Short Write und jede erneute
Geräteprüfungsabweichung verlassen die Segmentloop und schließen den
Descriptor im `finally`-Block.

Das PASS ist eine statische Codebewertung und keine Live-Freigabe.

## 1. Gefundene Probleme und Korrekturen

### 1.1 Unvollständiges JFIF-APP0 wurde akzeptiert

Vor dem Review genügte ein APP0-Payload, der lediglich mit `JFIF\0` begann.
Ein abgeschnittener Fünf-Byte-Payload konnte deshalb die JFIF-Prüfung bestehen.

Korrektur:

- exakt 14 Byte APP0-Payload ohne Thumbnail;
- Identifier `JFIF\0`;
- Hauptversion 1;
- gültige Dichteeinheit;
- von null verschiedene X-/Y-Dichte;
- Thumbnailabmessungen exakt null;
- genau ein JFIF-APP0-Segment.

Regressionstest: `test_rejects_truncated_jfif_header`.

### 1.2 Quantisierungstabellen wurden nicht validiert

SOF0 referenzierte Tabellen 0 und 1, der Parser verlangte deren DQT-Segmente
aber nicht. Ein strukturell unvollständiges JPEG ohne DQT konnte damit die
bisherigen Gates passieren.

Korrektur:

- genau die 8-Bit-DQT-IDs 0 und 1;
- jeweils exakt 64 von null verschiedene Werte;
- keine doppelten oder zusätzlichen Tabellen;
- beide referenzierten Tabellen müssen vorliegen.

Regressionstest: `test_rejects_missing_quantization_tables`.

### 1.3 Zusätzliche Marker und Metadaten wurden übersprungen

Nicht ausdrücklich behandelte längentragende Marker wurden zuvor nur anhand
ihrer Länge übersprungen. Dadurch waren etwa APP1/Exif oder andere, für den
ersten Test nicht vorgesehene Varianten möglich.

Korrektur:

- strikte Header-Allowlist für JFIF-APP0, DQT, SOF0, DHT und SOS;
- SOF1, SOF2 und alle weiteren SOF-Typen werden ausdrücklich abgelehnt;
- DRI und DAC werden ausdrücklich abgelehnt;
- alle übrigen Marker, einschließlich weiterer APP-Marker, werden abgelehnt;
- zusätzliche `0xff`-Fillbytes im Header oder Entropiepfad werden für diese
  enge Testuntermenge abgelehnt.

Regressionstests: `test_rejects_sof1`, `test_rejects_sof2`,
`test_rejects_other_sof_variant` und `test_rejects_additional_app_marker`.

### 1.4 Risikoschalter war durch argparse abkürzbar

Python-`argparse` akzeptiert standardmäßig eindeutige Präfixe langer Optionen.
Damit hätte eine verkürzte Schreibweise des Risikoschalters genügen können.

Korrektur:

- `ArgumentParser(allow_abbrev=False)`;
- `--dry-run` und `--i-understand-the-risk` bleiben gegenseitig
  ausgeschlossen;
- nur der vollständig ausgeschriebene Risikoschalter kann den Livezweig
  erreichen.

Regressionstests: `test_risk_switch_cannot_be_abbreviated` und
`test_dry_run_cannot_be_combined_with_risk_switch`.

### 1.5 JPEG-Eingabe war nicht ausdrücklich auf reguläre Dateien begrenzt

Die Größenprüfung machte typische Geräte- oder FIFO-Pfade bereits praktisch
unbrauchbar, typisierte die Eingabe aber nicht ausdrücklich.

Korrektur:

- `_load_jpeg()` verlangt vor dem Lesen `stat.S_ISREG`;
- eine nicht reguläre Eingabe wird vor Geräteauswahl und hidraw-Open
  abgelehnt.

Regressionstest: `test_non_regular_jpeg_input_is_rejected_before_device_selection`.

## 2. Unabhängiger Review des JPEG-Validators

### 2.1 Längen- und Segmentgrenze

`segment_count()` verlangt zuerst `jpeg_length > 0`, berechnet

```text
N = (L + 1019) // 1020
```

und akzeptiert nur `1 <= N <= 4`. `_load_jpeg()` verwirft eine Dateigröße über
4080 Byte bereits vor dem Lesen. `validate_jpeg()` berechnet dieselbe Grenze
erneut aus den tatsächlich gelesenen Bytes. Eine Dateiänderung zwischen
`stat()` und `read_bytes()` wird über den Größenvergleich erkannt.

`N=0` und das erste `N=5`, also `L=4081`, besitzen eigene Negativtests.

### 2.2 Markerparser

- Die Datei muss bytegenau mit `ff d8` beginnen.
- Jedes Headersegment benötigt genau ein `ff`-Präfix und eine Big-Endian-
  Segmentlänge von mindestens zwei.
- `end = offset + declared_length` wird vor dem Payloadzugriff gegen die
  Dateilänge geprüft.
- Markerbyte `00` außerhalb der Scandaten wird als ungültiges Stuffing
  abgelehnt.
- Innerhalb der Scandaten wird ausschließlich `ff 00` als Stuffing
  übersprungen. Restartmarker und zusätzliche Fillbytes werden abgelehnt.
- Der erste echte Marker nach dem einzigen Scan muss EOI `ff d9` sein.
- Der Offset unmittelbar nach EOI muss exakt der Dateilänge entsprechen.

Damit werden fehlendes EOI, ein abgeschnittenes Längenfeld, ein über das
Dateiende reichendes Segment und Daten nach EOI abgelehnt. Die Fixture wird
nicht aufgrund eines zufälligen `ff d9` in Entropiedaten akzeptiert.

### 2.3 SOF0 und Komponenten

Der Parser verlangt genau ein SOF0. Dessen Payloadlänge muss exakt
`6 + 3*C` entsprechen. Anschließend gelten:

- Sample Precision 8;
- Breite und Höhe exakt 320;
- Komponentenfolge exakt:
  - ID 1, Sampling `2x2`, DQT 0;
  - ID 2, Sampling `1x1`, DQT 1;
  - ID 3, Sampling `1x1`, DQT 1.

Damit ist die akzeptierte Struktur JFIF-YCbCr 4:2:0. SOF1, SOF2 und alle
anderen in JPEG definierten SOF-Marker sind ausgeschlossen.

### 2.4 Baseline-Scan und Huffmantabellen

Das einzige SOS muss drei Komponenten mit den Selektoren
`(1,00), (2,11), (3,11)` und den Baseline-Feldern `00 3f 00` besitzen. Ein
zweiter Scan ist unmöglich, weil nach dem ersten Entropiestrom unmittelbar EOI
verlangt wird.

Die vier DHT-Tabellen DC/AC × Luma/Chroma werden einzeln strukturell geparst.
Tabellenklasse, ID, 16 Codelängenzähler und daraus folgende Symbolzahl müssen
konsistent sein. Die vollständigen Tabellenbytes müssen den festgelegten
SHA-256-Werten der vier Standardtabellen entsprechen. Doppelte, fehlende oder
zusätzliche Tabellen werden abgelehnt.

### 2.5 Grenze der Markerprüfung

Der Validator dekodiert die Huffman-Entropiedaten nicht semantisch. Ein
syntaktisch korrekt begrenzter, aber fachlich ungültiger Bitstrom könnte
deshalb als Markerstruktur akzeptiert werden. Das entspricht dem vereinbarten
direkten Markercheck, wird für den Livekandidaten aber zusätzlich begrenzt:

- die Fixture ist per SHA-256 eingefroren;
- `file`, FFmpeg und ImageMagick erkennen beziehungsweise dekodieren sie
  unabhängig als Baseline-JPEG;
- der Unit-Test bindet den bekannten Hash an die validierte Struktur.

Für ein beliebiges anderes, nur markerstrukturell gültiges JPEG wäre dies ein
verbleibendes Decoderfehlerrisiko. Der erste Live-Test soll deshalb weiterhin
die eingefrorene Fixture verwenden.

## 3. Unabhängige Referenz-JPEG-Verifikation

Datei: `tests/fixtures/lcd-0x08-reference.jpg`

| Prüfung | Ergebnis |
| --- | --- |
| SHA-256 | `5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866` |
| Länge | 2236 Byte |
| Container | JFIF 1.01, Dichte 1×1, kein Thumbnail |
| SOF | SOF0 / Baseline |
| Präzision | 8 Bit |
| Geometrie | 320×320 |
| Komponenten | 3 |
| Sampling | `2x2,1x1,1x1`, FFmpeg `yuvj420p` |
| Scan | Baseline, nicht interlaced/progressive |
| EOI | letzte zwei Dateibytes `ff d9` |
| Dateinachlauf | keiner |
| `N` | 3 |
| Padding | 3060 − 2236 = 824 Byte |

Unabhängige Werkzeuge:

- `file`: JFIF, baseline, precision 8, 320×320, components 3;
- `ffprobe`: Baseline, 320×320, `yuvj420p`;
- ImageMagick `identify`: 8 Bit, Sampling `2x2,1x1,1x1`, kein Interlace,
  Qualität 60;
- `sha256sum`, `stat` und `xxd`: Hash, Länge und abschließendes `ff d9`.

Die Datei wurde nicht verändert und nicht gesendet.

## 4. Bytegenauer Paketbuilder-Review

Für `L=2236` gilt:

```text
N = ceil(2236 / 1020) = 3
Gesamtpayload = 3 * 1020 = 3060 Byte
Rest im letzten Segment = 2236 - 2040 = 196 Byte
Padding = 3060 - 2236 = 824 Byte
```

Die drei Segmente lauten:

| Segment | Control | Payload | Drahtreport | hidraw-Puffer |
| ---: | --- | ---: | ---: | ---: |
| 0 | `08 03 00 80` | 1020 | 1024 | 1025 |
| 1 | `08 01 00 00` | 1020 | 1024 | 1025 |
| 2 | `08 02 00 00` | 196 JPEG + 824 `00` | 1024 | 1025 |

Jeder hidraw-Puffer ist exakt `00 || Control || Payload`. Eine unabhängige
Rekonstruktion aus allen drei Payloads ergab für die ersten 2236 Byte erneut
den Fixture-SHA-256. Alle folgenden 824 Byte waren null. Damit ging kein
JPEG-Byte verloren, wurde dupliziert oder verschoben.

`_validate_transfer_invariants()` führt dieselben Prüfungen bei der
Paketbildung und im Livepfad unmittelbar vor jedem möglichen Write aus.

## 5. Geräteauswahl und Revalidierung

`_select_target()` ruft ausschließlich `discover("0b05", "1c7b")` auf und
filtert danach auf `interface_number == 1`. Genau ein Treffer ist erforderlich.
Der Treffer muss zusätzlich erfüllen:

- VID `0b05`, PID `1c7b`;
- Interface 1;
- Inputreport 16 Byte;
- Outputreport 1024 Drahtbyte;
- keine Report-IDs;
- dynamisch gelieferter absoluter `/dev/hidraw*`-Pfad.

Es gibt keinen konkreten, fest codierten hidraw-Index. Interface 0 wird weder
ausgewählt noch als Fallback verwendet.

Nach `os.open()` und unmittelbar vor jedem Segment validiert
`_validate_open_target()`:

- geöffnetes Ziel ist ein Zeichengerät;
- `st_rdev` entspricht dem sysfs-`dev`-Wert des erwarteten Eintrags;
- erneute Discovery ohne udev liefert genau denselben Geräte- und sysfs-Pfad;
- VID/PID, Interface, Reportgrößen und fehlende Report-ID gelten weiterhin.

Ein Interface-0-Objekt scheitert sowohl an `_device_validation_error()` als
auch an der erneuten Discoveryfilterung und kann die Write-Callsite nicht
erreichen.

## 6. Vollständiger Writepfad

AST- und Textsuche ergeben:

- `os.open()`-Callsites im Werkzeug: 1, in `_run_once()`;
- `os.write()`-Callsites im Werkzeug: 1, in `_run_once()`;
- `os.read()`-Callsites im Werkzeug: 0;
- direkte Aufrufer von `_run_once()`: ausschließlich `main()`;
- `_run_once()` wird nur nach vollständiger Offline-Validierung, eindeutiger
  Geräteauswahl und vollständig ausgeschriebenem Risikoschalter aufgerufen.

Die einzige Write-Loop iteriert über das unveränderliche Segment-Tuple.
`build_transfer_segments()` kann aufgrund `MAX_SEGMENTS=4` höchstens vier
Einträge erzeugen. Erfolg bedeutet daher exakt `N` Writes mit jeweils 1025
Byte und `N <= 4`.

Vor jedem Write laufen Geräte- und Paketinvarianten. Danach existieren drei
mögliche Ergebnisse:

1. `os.write()` liefert 1025: nächstes Segment, sofern vorhanden;
2. Exception: unmittelbarer Return ohne weiteres Segment;
3. Rückgabewert ungleich 1025: unmittelbarer Return ohne Nachsenden.

Jeder Return und auch `KeyboardInterrupt` durchläuft den `finally`-Close.
Gemockte Tests bestätigen:

- Erfolgsfall mit `N=3`: genau drei Writeaufrufe;
- Short Write im ersten Segment: genau ein Aufruf;
- Exception im ersten Segment: genau ein Aufruf;
- erstes Segment erfolgreich, Exception im zweiten: genau zwei Aufrufe und
  kein dritter.

Es gibt keinen Retry, keinen Recovery-Write, keinen Reconnect, keinen zweiten
Frame, keinen Interface-0-Write und keine Auswahl eines anderen Commands.

## 7. Preview-, Dry-Run- und Argumentreview

Der einzige Livezweig wird durch folgende Bedingung geschützt:

```text
wenn --dry-run gesetzt oder --i-understand-the-risk nicht gesetzt:
    Preview beenden
```

Zusätzlich gilt:

- Optionsabkürzungen sind deaktiviert;
- Dry-Run und Risikoschalter gemeinsam sind ein argparse-Fehler;
- `--help` beendet argparse vor JPEG- oder Geräteverarbeitung;
- unbekannte oder verkürzte Optionen werden abgelehnt;
- JPEG- und Paketvalidierung finden vor der Geräteauswahl statt.

Mocks ersetzen `os.open()` in den Tests durch eine auslösende Sperre. Normaler
Aufruf, expliziter Dry-Run, `--help`, verkürzter Risikoschalter, kombinierter
Dry-Run/Risikoschalter und nicht reguläre JPEG-Eingabe erreichen keinen Open.

Die Tests selbst öffnen kein `/dev/hidraw*`. Zwei Previewtests schreiben nur
ein synthetisches JPEG in ein automatisch entfernte temporäres Verzeichnis.
Alle simulierten Livepfade mocken `os.open`, `os.write`, `os.close` und die
Geräterevalidierung.

## 8. Sicherheitsquersuche

Im neuen Werkzeug wurden keine direkten Aufrufe gefunden für:

- `subprocess`, `os.system`, `popen` oder Shellausführung;
- Netzwerkbibliotheken oder Netzwerkzugriff;
- Datei-Schreiboperationen;
- SPI-, Flash-, Firmware-, Bootloader- oder Persistenzfunktionen;
- Retry-, Reconnect- oder Recoverylogik;
- andere HID-Commands.

Der bestehende importierte Discoveryhelfer verwendet intern ausschließlich
einen lokalen, lesenden `udevadm info --query=property`-Subprozess und liest
sysfs/Reportdeskriptoren. Er öffnet kein hidraw-Gerät und sendet nichts.

Die `while`-Loops liegen nur im Markerparser. Ihre Eingabe ist vorab auf
höchstens 4080 Byte begrenzt und jeder Schleifenpfad erhöht seinen Offset oder
bricht ab. Die Write-Loop ist auf höchstens vier Segmente begrenzt. Es gibt
keine unbegrenzte Retry- oder Geräte-I/O-Schleife.

## 9. Verbleibende Risiken und Geltungsgrenze

- Die v49-Implementierung des realen Geräts ist weiterhin nicht binär
  bestätigt; v51 besitzt im `0x08`-Pfad keine persistente Kante.
- Interface-1-hidraw-Framing und der Decoderpfad sind auf dem realen Gerät noch
  nicht live validiert.
- `os.write()` kann trotz `O_NONBLOCK` einen USB-/Treiberfehler liefern; der
  Code bricht dann ab, ein unvollständiger Transfer kann flüchtigen Zustand
  hinterlassen.
- Der Parser validiert Marker und Tabellen, nicht die Entropie semantisch. Die
  konkrete Fixture ist unabhängig dekodiert und gehasht; für den ersten Test
  soll keine andere Datei verwendet werden.
- „Einmalig“ ist pro Prozesslauf technisch erzwungen. Ein Mensch könnte das
  Programm in einem zweiten Prozess erneut mit dem vollständigen
  Risikoschalter starten. Die globale Einmaligkeit bleibt daher eine
  organisatorische Freigabegrenze.
- Schreibrechte und ein Liveauftrag bleiben getrennt zu autorisieren. Dieser
  Review hat keine Rechte verändert und keinen Live-Test freigegeben.

## 10. Offline-Prüfergebnis

```text
python3 -B -m unittest discover -s tests -v
```

Ergebnis nach den Korrekturen: **37 Tests erfolgreich**. Darin enthalten sind
alle geforderten Negativfälle, statische Callsiteprüfung, Referenzhash,
Paketrekonstruktion, Dry-Run-Gates und gemockte Writefehler. Zusätzlich waren
Python-AST-Parsing und `git diff --check` erfolgreich.
