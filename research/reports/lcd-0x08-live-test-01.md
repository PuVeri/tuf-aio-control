# Erster realer `0x08`-JPEG-Live-Test

Dokumentiert: 2026-09-02  
Exakter Testzeitpunkt: nicht mitgeteilt

## Umfang und Evidenzgrenze

Dieser Bericht hält das vom Bediener bestätigte Ergebnis genau eines realen
JPEG-Transfers fest. Während dieser Dokumentationsarbeit fand keine weitere
Gerätekommunikation statt, es wurden keine Schreibrechte aktiviert und kein
zweiter Test ausgeführt.

Die Beobachtung belegt den beschriebenen Erfolgsfall auf diesem realen Gerät
mit genau dieser JPEG-Datei und dieser Segmentfolge. Sie ist weder ein
USB-Mitschnitt noch ein Beleg für nicht von außen beobachtbare
Firmwareinternas.

## Gerät

| Merkmal | Wert |
| --- | --- |
| VID:PID | `0b05:1c7b` |
| Versionswert aus `0x87` | `0x0049` |
| USB-Geräterevision | `bcdDevice 0.49` |
| verwendetes Interface | 1 |
| hidraw-Knoten während dieses Boots | `/dev/hidraw8` |

Der hidraw-Knoten ist nur eine Momentaufnahme; die Auswahl erfolgte über
Geräteidentität und Interface und darf nicht als stabiler Pfad behandelt
werden. Versionswert und `bcdDevice` stützen stark die Einordnung als v49-
Gerät. Die bytegenaue Identität des installierten Binärstands mit einer
offiziellen ASUS-v49-Datei bleibt mangels dieser Datei unbewiesen.

## Eingefrorenes Referenz-JPEG

| Merkmal | Wert |
| --- | --- |
| Datei | `tests/fixtures/lcd-0x08-reference.jpg` |
| SHA-256 | `5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866` |
| Länge | 2236 Byte |
| Geometrie | 320×320 |
| JPEG-Profil | SOF0 / Baseline, 8 Bit |
| Farbdarstellung | JFIF-YCbCr 4:2:0 |
| Segmentzahl | `N=3` |
| Nullpadding | 824 Byte |

## Tatsächlich gesendete Folge

Jeder Linux-hidraw-Aufruf enthielt 1025 API-Byte:
`00 || 1024-Byte-Drahtreport`. Der Drahtreport bestand aus vier Controlbytes
und 1020 Payloadbytes.

| Segment | Controlword | Payload |
| --- | --- | --- |
| 0 | `08 03 00 80` | JPEG-Bytes 0 bis 1019 |
| 1 | `08 01 00 00` | JPEG-Bytes 1020 bis 2039 |
| 2 | `08 02 00 00` | letzte 196 JPEG-Bytes, danach exakt 824 × `00` |

Es erfolgten exakt drei Writes und kein Retry. Es gab keine Kommunikation mit
Interface 0, keinen Read von Endpoint `0x84`, keinen weiteren Command und
keinen zweiten Frame.

## Beobachtetes Ergebnis

Der Transfer wurde erfolgreich ausgeführt. Auf dem AIO-LCD erschien sichtbar
das erwartete weiße Quadrat. Damit sind für diesen einen Transfer sowohl die
JPEG-Dekodierung als auch ein sichtbarer Displaycommit belegt. Temporär
erteilte Schreibrechte wurden unmittelbar danach wieder entfernt.

## Empirisch bestätigt auf dem realen v49-Gerät

- Interface 1 funktioniert als Bildkanal.
- Linux-hidraw-Framing `00 || 1024-Byte-Report` funktioniert.
- Ein `0x08`-JPEG-Transfer funktioniert.
- `N=3` mit den Folgeindizes 1 und 2 funktioniert.
- 824 Nullbytes nach dem JPEG-EOI im letzten Payload werden akzeptiert.
- Das spezifizierte Baseline-JPEG wird dekodiert und sichtbar committed.
- Für diesen erfolgreichen Transfer war kein Interface-0-Begleitbefehl nötig.
- Für diesen erfolgreichen Transfer war kein Read von Endpoint `0x84` nötig.

„v49-Gerät“ bezeichnet hier die empirische Kombination aus Versionswert
`0x0049` und `bcdDevice 0.49`, nicht eine bytegenau verifizierte
Firmwaredatei.

## Nur aus der analysierten v51-Firmware statisch bekannt

Queuegrenzen, Decoder-Lease, interner Decoderstart, Queuefreigabe und die
genauen Commit-Callbacks sind nur im analysierten v51-Pfad statisch
nachvollzogen. Ebenso gilt der fehlende erreichbare SPI-/Flash-/Bootloader-
und persistente Konfigurationsschreibpfad nur als statischer Befund für v51.
Der sichtbare Erfolg auf dem realen Gerät bestätigt das externe Ergebnis,
nicht diese internen Implementierungsdetails für v49.

## Weiterhin offen und ausdrücklich nicht ableitbar

Aus diesem einzelnen erfolgreichen Frame darf keine Aussage abgeleitet werden
über:

- Animationen oder mehrere Frames;
- langfristigen Dauerbetrieb;
- Fehler-, Timeout-, Abbruch- oder Recoveryverhalten;
- andere JPEG-Profile, Größen, Samplingvarianten oder Segmentzahlen;
- den Inhalt oder die Notwendigkeit von Endpoint `0x84` in anderen Abläufen;
- die exakten v49-internen Queue-, Lease-, Decoder- und Commitpfade;
- die bytegenaue Identität der installierten Firmware mit einer offiziellen
  ASUS-v49-Binärdatei.

Die erfolgreiche Beobachtung erteilt keine Freigabe für einen weiteren
Transfer.
