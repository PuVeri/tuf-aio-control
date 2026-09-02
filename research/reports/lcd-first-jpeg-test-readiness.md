# Abschließender statischer Readiness-Review für den ersten JPEG-Test

Stand: 2026-09-02

## Zweck und Sicherheitsgrenze

Dieser Bericht bewertet die Readiness für genau einen späteren, ausdrücklich
freizugebenden ASUS-LCD-JPEG-Transfer auf Interface 1 des Geräts
`0b05:1c7b`. Er basiert ausschließlich auf den vorhandenen statischen
Host- und Firmwareanalysen, den realen lesenden Identitätsbefunden und den
bereits dokumentierten `0x87`-Ergebnissen.

Während dieses Reviews gab es keine Gerätekommunikation, keinen HID-Zugriff,
keinen HID-Write und keinen Testcode. Die hier ausgesprochene GO-Entscheidung
ist eine technische Readiness-Entscheidung für ein Folgeticket. Sie ist keine
Freigabe, den beschriebenen Write auszuführen.

Bewertungsskala:

- **bestätigt:** direkt im Host, in v51, in Deskriptoren oder am realen Gerät
  beobachtet beziehungsweise statisch geschlossen;
- **stark gestützt:** mehrere unabhängige Belege schließen die Aussage eng
  ein, aber die konkrete Interface-1-Ausführung auf dem realen Gerät fehlt;
- **offen:** mit den vorhandenen Artefakten nicht belastbar entscheidbar;
- **widersprüchlich:** vorhandene Belege verlangen unvereinbare Aussagen.

## 1. Host-vs-Device-Endprüfung

### 1.1 Transport und Assemblierung

| Prüfpunkt | Host und analysierte v51-Firmware | Reales Gerät / Gesamtbewertung |
| --- | --- | --- |
| Reportgröße | InfoHub schreibt 1025 Windows-HID-API-Byte. Das erste Byte ist `00`; v51 empfängt auf EP `0x03` exakt 1024 Byte. | **bestätigt** für InfoHub, Deskriptor und v51. Die identische Linux-Abbildung `00 || report[1024]` ist durch die hidraw-Semantik und den real bestätigten Interface-0-Fall **stark gestützt**, auf Interface 1 aber noch nicht live bestätigt. |
| HID-Framing | Interface 1 besitzt keinen Report-ID-Item. Das API-Nullbyte gehört nicht zum Drahtreport; Drahtbyte 0 ist `0x08`. | **stark gestützt** end-to-end. Es gibt keinen widersprechenden Befund. |
| Controlword | Host und v51 verwenden Byte 0 als Command, Bytes 1/2 plus die unteren sieben Bits von Byte 3 als Feld und Bit 7 von Byte 3 als First-Bit. | **bestätigt** für Host/v51; für den sehr wahrscheinlich v49-basierten realen Consumer **offen**, aber durch die produktspezifische ASUS-Hostsoftware stark kompatibilitätsgestützt. |
| `N` | Host: `N = ceil(L/1020)`. v51: Erstsegmentfeld ist die Segmentzahl; normale sichere Grenze `1 <= N <= 200`. | **bestätigt** für Host/v51. Das konkrete Testartefakt muss `L` und `N` vor dem Öffnen des Geräts fixieren und validieren. |
| Segmentindexfolge | Host sendet nach Segment 0 exakt `1..N-1`. v51 erwartet genau diesen Fortschritt; nur das aktuelle Segment kann als Duplikat behandelt werden. | **bestätigt** für Host/v51. Kein Retry und kein Duplikat sind für den Test zulässig. |
| Erstsegmentbit | Nur Segment 0 trägt Byte 3 `0x80`; alle Folgesegmente tragen dort `0x00`. | **bestätigt** für Host/v51. |
| Nullpadding | InfoHub nullt den Quellpuffer und kopiert immer 1020 Byte. v51 übernimmt den vollständigen letzten Block unverändert. | Hostregel und Transport sind **bestätigt**. Dass der Hardwaredecoder nach EOI ausschließlich Nullbytes toleriert, ist durch die ASUS-Erzeugung und EOI-Terminierung **stark gestützt**, nicht live bestätigt. |
| Queuegrenzen | v51 besitzt 200 Blöcke und akzeptiert den normalen Bereich `1 <= N <= 200`; der Test nutzt ein sehr kleines `N`. | Für v51 **bestätigt**. Eine abweichende v49-Grenze ist **offen**; bei einem minimalen ASUS-JPEG fehlt dafür aber ein positiver Hinweis. |

### 1.2 Decoder- und Displaylebenszyklus

| Prüfpunkt | Analysierter v51-Pfad | Bewertung für den späteren Test |
| --- | --- | --- |
| Decoder-Lease | Nach vollständiger Assemblierung wird `config+0x108` in den flüchtigen Countdown `0x001315c4` geladen. Bootdefault ist 5000 Callbackticks. Solange der Decoder aktiv und der Wert ungleich null ist, bleibt die Queuequelle belegt. | v51 **bestätigt**. Wandzeiteinheit und v49-Implementierung sind **offen**. Der Test verändert den Wert nicht und setzt einen bekannten, zuvor nicht durch andere LCD-Kommandos veränderten Gerätezustand voraus. |
| Decoderstart | Der Consumer benötigt Queueeintrag und freien Zielknoten, sendet früh `08 81`, setzt Grafikzustand zurück und startet Modus `0x6021` mit Queuequelle und Framebufferziel. | v51 **bestätigt**; Start auf dem realen Gerät **offen**, durch ASUS-Zielhost und identisches Produkt stark gestützt. |
| Queuefreigabe | Bei `active==0` wird die Queue freigegeben und der Zielknoten ready markiert. Läuft die Lease zuerst ab, wird die Queue ohne Ready-Markierung freigegeben; ein Decoderstopp ist dort nicht sichtbar. | v51 **bestätigt**. Fehlerbit und Decodererfolg werden nicht zur Hostseite gemeldet. Das konkrete v49-Verhalten ist **offen**. |
| Displaycommit | Ein späterer Callback schaltet die Framebufferbasis auf den ready markierten Knoten und gibt den zuvor sichtbaren Knoten frei. | Der v51-Kontrollfluss ist **bestätigt**. Sichtbarer Zeitpunkt, tatsächlicher Erfolg und v49-Gleichheit sind **offen**. `08 81` ist ausdrücklich kein Done- oder Commitstatus. |

In den geprüften Punkten gibt es keinen als **widersprüchlich** einzustufenden
Befund. Die offenen Punkte liegen sämtlich hinter der fehlenden realen
v49-Binär- beziehungsweise Laufzeitevidenz; sie ändern nicht das geschlossene
ASUS-Hostformat.

## 2. Abgegrenzte v49-Restunsicherheit

ASUS InfoHub 1.0.0.15 filtert im rekonstruierten Gerätepfad exakt auf
`0b05:1c7b`, ordnet dessen Interface mit 1025 API-Ausgabebyte als HID2 zu und
erzeugt genau den beschriebenen `0x08`-Transfer. Der Sender ist daher nicht
nur protokollfamilienähnlich, sondern ASUS- und produkt-ID-spezifisch.

Das reale Gerät meldet empirisch `0x0049` über `0x87` und `bcdDevice 0.49`.
Die Bezeichnung seines Binärstands als v49 ist sehr stark abgeleitet, aber
mangels offizieller v49-Binärdatei nicht bytegenau bestätigt. Die analysierte
Firmware ist v51. Für deren `0x08`-Unterbaum ist kein persistenter Schreibpfad
erreichbar.

### 2.1 Änderung, durch die der Transfer nur fehlschlagen würde

Mindestens einer der folgenden konkreten Mechanismen müsste in v49 gegenüber
v51 abweichen:

- `0x08` wird verworfen oder erwartet ein anderes First-/Index-/Zählermodell;
- die normale Queuegrenze ist kleiner als das konkrete `N`, oder die
  Queueallokation schlägt fehl;
- v49 akzeptiert die SOF0-/YCbCr-/Samplingkombination oder das Nullsuffix
  nicht;
- der Decoderstart, die Ready-Markierung oder der Framebuffercommit fehlt
  beziehungsweise erwartet eine zusätzliche, von InfoHub 1.0.0.15 im
  erfolgreichen Pfad nachweislich nicht gesendete Aktion.

Diese Änderungen erklären Ablehnung, unverändertes Display oder einen
Decoderfehler. Keine davon erzeugt für sich einen persistenten Effekt.

### 2.2 Änderung, durch die der Transfer temporär hängen würde

Es müsste mindestens einer dieser flüchtigen Lebenszyklen in v49 gegenüber
v51 fehlen oder fehlerhaft sein:

- der v49-Assembler hält nach einer anders interpretierten Segmentfolge einen
  unvollständigen Transfer ohne Reset- oder Ersatzmöglichkeit fest;
- das Decoder-Active-Signal bleibt für dieses JPEG gesetzt und die Lease fehlt,
  wird nicht dekrementiert oder gibt Queue-/Bulk-Zustand nicht frei;
- der Lease-Ablauf gibt zwar Speicher frei, lässt aber Decoder, Queue, Ring oder
  Displaytask in einem flüchtigen Busy-Zustand;
- der Interface-1-OUT-Endpunkt wird nach einem Fehler oder Abschluss nicht
  erneut armiert.

Das wären RAM-, MMIO-, Queue- oder USB-Zustände. Ohne zusätzliche persistente
Kante sind Replug beziehungsweise Geräte-/Displayneustart die obere
Recoveryklasse, nicht persistente Beschädigung.

### 2.3 Änderung, durch die der Transfer persistent gefährlich würde

Eine reine Inkompatibilität, ein Decoderfehler, fehlendes `08 81`, ein
Timeout oder ein ausbleibender Commit genügt nicht. Mindestens einer dieser
technischen Mechanismen müsste in v49 neu vorhanden sein:

1. **Dispatcher-Alias:** Interface-1-Command `0x08` verzweigt in v49 statt in
   die JPEG-Queue auf SPI-/Flash-, Updater-, Boot- oder persistente
   Konfigurationslogik.
2. **Persistente Kante im JPEG-Unterbaum:** Assembler, Consumer,
   Decoderabschluss oder Fehlerpfad ruft zusätzlich einen persistenten Writer,
   Updater oder Bootpfad auf.
3. **Adresssteuerung:** JPEG- oder Controlwordbytes bestimmen in v49 entgegen
   v51 eine DMA-/Decoder-Zieladresse, die persistenten Adressraum erreichen
   kann.
4. **Normalbereichs-Speicherfehler mit persistenter Folgekante:** Schon das
   kleine, gültige `N` und die vollständigen 1020-Byte-Blöcke überschreiben
   wegen eines kleineren/falschen v49-Puffers kontrollfluss- oder
   adresswirksamen Zustand, der anschließend tatsächlich einen persistenten
   Writer erreicht.

Für keinen dieser Mechanismen liegt ein positiver Beleg vor. Dass ASUS
InfoHub genau dieses VID/PID-Ziel mit genau diesem Format bedient, spricht
zusätzlich gegen einen grundlegenden Dispatcher- oder Normalformatbruch in der
produktiven Gerätegeneration. Es beweist jedoch nicht die bytegleiche
v49-Implementierung.

## 3. Konservatives JPEG-Testartefakt

### 3.1 Verbindliche Bildeigenschaften

Das spätere Artefakt muss offline und vor jedem Geräte-Open erzeugt,
bytegenau eingefroren und unabhängig validiert werden:

- exakt 320 × 320 Pixel;
- JPEG Baseline Sequential, Marker SOF0;
- 8 Bit Sample Precision;
- JFIF mit drei Komponenten Y, Cb und Cr;
- 4:2:0: Y-Sampling `2x2`, Cb und Cr jeweils `1x1`;
- Huffman-Entropiecodierung mit den üblichen Standardtabellen, keine
  optimierten oder benutzerdefinierten Tabellen;
- genau ein sequentieller Scan, kein Progressive-, Extended-, arithmetischer,
  hierarchischer oder differentieller Modus;
- keine CMYK-/YCCK-, RGB- oder Adobe-APP14-Interpretation;
- keine EXIF-, ICC-, Thumbnail- oder anwendungsspezifischen Metadaten;
- Qualität 60 als die von InfoHub im initialen Modus 1 verwendete
  Qualitätsstufe;
- kein Restartintervall;
- eine sehr einfache achromatische Grafik, vorzugsweise dunkler Hintergrund
  mit einem hellen, an 16-Pixel-MCU-Grenzen ausgerichteten Rechteck. Dadurch
  bleiben Cb/Cr konstant, der Inhalt ist sichtbar erkennbar und die Datei
  klein;
- Datei beginnt mit `ff d8` und ihr syntaktisch zugehöriges EOI ist `ff d9`;
  die Quelldatei selbst enthält keine Bytes nach diesem EOI;
- `L` liegt deutlich unter 204000 Byte und
  `N = ceil(L/1020)` erfüllt `1 <= N <= 200`;
- für diesen Minimaltest wird zusätzlich `N <= 4` verlangt. Wird dies mit der
  festgelegten einfachen Grafik nicht erreicht, findet kein Write statt; das
  Artefakt wird offline neu geprüft.

4:2:0 ist gegenüber 4:4:4 für diesen Test vorzuziehen: Es ist im
Hardwaremanual ausdrücklich unterstützt, entspricht einem üblichen
JFIF-Encoderpfad und benötigt bei gleicher einfachen Grafik weniger
Entropieblöcke. 4:4:4 wäre technisch innerhalb der belegten Untermenge, bietet
hier aber keinen Sicherheitsvorteil.

### 3.2 Explizit zu kontrollierende Encoderparameter

- Abmessungen und Pixelinhalt;
- Baseline/SOF0, 8 Bit und genau ein sequentieller Scan;
- YCbCr-Komponentenmodell, Komponenten-IDs und 4:2:0-Samplingfaktoren;
- Huffman statt arithmetischer Codierung, Standard-Huffmantabellen und
  deaktivierte Huffmanoptimierung;
- Qualitätsstufe 60;
- deaktivierter Progressive-Modus und fehlendes Restartintervall;
- JFIF-Ausgabe ohne EXIF, ICC, APP14, Thumbnail und zusätzliche Kommentare;
- vollständige Markerstruktur, SOI/EOI und fehlender Dateinachlauf;
- maximale Länge und daraus berechnetes `N`.

Eine Option wie „quality 60“ allein ist nicht encoderübergreifend
byteidentisch. Deshalb wird nicht nur der Aufruf, sondern das fertige Artefakt
validiert und eingefroren.

### 3.3 Zu dokumentierende Reproduzierbarkeitsdaten

- Encodername, exakte Version und Bezugsquelle;
- vollständige Erzeugungsparameter;
- SHA-256, exakte JPEG-Länge `L`, `N` und Nullpaddinglänge;
- Markerliste und Offsets, JFIF-Version/Dichte, Komponenten- und
  Tabellenselektoren;
- tatsächliche DQT- und DHT-Tabellen;
- Ergebnis einer unabhängigen strukturellen JPEG-Prüfung und eines
  rein lokalen Softwaredecodes;
- finaler Segmentplan einschließlich Hash beziehungsweise Hexdarstellung der
  vier Controlbytes jedes Segments.

Ein selbst erzeugtes und vollständig validiertes JPEG ist sicherer als ein
beliebiges vorhandenes Bild: Metadaten, Progressive-Modus, Farbraum,
Subsampling, Tabellen, Nachlauf und Größe sind kontrollierbar. Ein beliebiges
vorhandenes JPEG darf für diesen ersten Test auch dann nicht verwendet werden,
wenn es sich lokal anzeigen lässt.

## 4. Exakte Spezifikation des einmaligen Folgetests

### 4.1 Vorbedingungen und Offline-Gates

1. Das Folgeticket besitzt eine ausdrückliche menschliche Freigabe für genau
   einen Interface-1-`0x08`-Bildtransfer auf genau das identifizierte Gerät.
2. Es gibt keinen parallel laufenden ASUS-/LCD-Sender und keinen anderen
   Prozess, der das Zielinterface schreibt.
3. Seit dem bekannten Geräte-/Initialzustand wurden keine fremden
   LCD-Kommandos gesendet, die Queue, Decoder oder `config+0x108` verändert
   haben könnten. Ist dieser Zustand nicht belastbar herstellbar, wird
   abgebrochen; ein potenziell unsicheres physisches Power-Cycling wird nicht
   improvisiert.
4. Das JPEG ist gemäß Abschnitt 3 fertig erzeugt, validiert und gehasht. Alle
   `N` API-Puffer werden vor dem Geräte-Open aufgebaut und statisch geprüft.
5. Für Segment 0 gilt exakt:
   `00 || 08 (N & 0xff) 00 80 || payload[0..1019]`.
6. Für Segment `i=1..N-1` gilt exakt:
   `00 || 08 (i & 0xff) 00 00 || payload[i*1020..i*1020+1019]`.
7. Der zusammengesetzte Payload ist exakt
   `JPEG[0..L-1] || 00 × (N*1020-L)`. Jeder API-Puffer ist 1025 Byte, jeder
   Drahtreport 1024 Byte.

### 4.2 Dynamische Identifikation und Validierung

1. `/dev/hidrawX` wird niemals fest codiert. Das Ziel wird dynamisch über
   `VID 0x0b05`, `PID 0x1c7b` und Interface 1 bestimmt.
2. Vor dem Öffnen zum Schreiben werden über rein lesende Systemmetadaten
   geprüft: genau das erwartete Gerät, Interface 1, Usage Page `0xff06`, Usage
   `0x01`, kein Report-ID-Item, 1024 Byte OUT, 16 Byte IN sowie die erwarteten
   Endpunkte `0x03` OUT und `0x84` IN.
3. `bcdDevice 0.49` wird erwartet und protokolliert. Eine andere Revision,
   Mehrdeutigkeit, ein fehlendes Attribut oder ein Descriptorunterschied führt
   zum Abbruch vor dem Write.
4. Unmittelbar vor dem ersten Write wird erneut geprüft, dass der dynamisch
   aufgelöste Knoten noch zu demselben physischen Gerät und Interface gehört.

Ein zusätzlicher rein lesender Preflight darf nur System- und
Deskriptormetadaten erfassen. Ein `0x87`-Request wäre trotz seiner lesenden
Semantik ein HID-Write und gehört ausdrücklich nicht zu diesem Test. Ein Read
auf EP `0x84` ist nicht erforderlich und liefert keinen belegten
Decoder-Done-Status.

### 4.3 Einzige Kommunikationssequenz

1. Genau ein Descriptor für Interface 1 wird geöffnet; Interface 0 wird nicht
   geöffnet und nicht angesprochen.
2. Auf dem vollständigen Erfolgsweg erfolgen exakt `N` synchrone
   `hidraw.write()`-Aufrufe in der Reihenfolge `0..N-1`.
3. Jeder Aufruf erhält exakt 1025 Byte und muss exakt 1025 als Erfolgslänge
   zurückgeben.
4. Bei Exception, USB-Fehler, Short Write oder unerwartetem Rückgabewert wird
   sofort abgebrochen und der Descriptor geschlossen. Dann gab es
   zwangsläufig weniger als `N` erfolgreiche Writes; es wird weder
   weitergesendet noch versucht, durch zusätzliche Aufrufe die Sollzahl zu
   erreichen.
5. Es gibt keinen Retry, kein Duplikat, keine Interface-0-Kommunikation, keinen
   weiteren Command und keinen Recovery-Write.
6. Es gibt keinen Read von EP `0x84`. InfoHub 1.0.0.15 benötigt ihn nicht;
   `08 81` wäre nur Queueannahme/Start und kein Sicherheits- oder Done-Beleg.
7. Nach dem letzten erfolgreichen Write wird der Descriptor geschlossen. Es
   folgt kein zweiter Frame.
8. Sichtbare Wirkung, Artefakte, USB-Zustand und eine gegebenenfalls nötige
   rein physische Recovery werden nur beobachtet und dokumentiert. Es wird
   kein weiterer HID-Befehl zur Diagnose oder Recovery gesendet.

### 4.4 Bewertung einer Fünf-Sekunden-Quiet-Phase

Die fünfsekündige rein lesende Phase des `0x87`-Tests diente dazu, einen
später gelesenen Inputreport belastbarer dem einzelnen Request zuzuordnen.
Beim JPEG-Test wird kein IN-Report ausgewertet. Eine leere per-Open-hidraw-
Inputqueue beweist weder freie interne JPEG-Queue noch inaktiven Decoder noch
den Wert der Lease.

Eine solche Phase bringt daher für den Bildpfad keinen belegten
Sicherheitsgewinn und ist kein Testgate. Wichtiger sind der bekannte
Gerätezustand, das Ausschließen paralleler Writer, vollständig vorbereitete
Puffer, kein Retry und kein zweiter Frame. Eine passive Beobachtungszeit nach
dem Schließen darf für die Ergebnisdokumentation verwendet werden, ist aber
keine zusätzliche Gerätekommunikation und kein Beleg für Decoderabschluss.

## 5. Failure-Mode-Bewertung

| Failure Mode | Erwarteter Mechanismus und Wirkung | Klasse / Recovery |
| --- | --- | --- |
| Falsches hidraw-Framing | Nichtnull-Report-ID, fehlendes API-Nullbyte oder verschobenes Command wird vom Linux-HID-Pfad voraussichtlich verworfen oder erzeugt keinen gültigen `0x08`-Report. | **flüchtig**; Writefehler oder kein Transfer. Durch strikte 1025-Byte-Vorvalidierung ausgeschlossen. |
| Falsche Länge | Short/oversize API-Write kann abgelehnt werden; ein unvollständiger Drahtreport erfüllt den 1024-Byte-Callbackvertrag nicht. | **flüchtig**, schlimmstenfalls unvollständige Assemblierung; Descriptor schließen, keine Wiederholung. |
| Falscher Segmentindex | v51 schreitet nur beim erwarteten nächsten Index fort; ein späterer Index wird nicht normal angefügt, ein aktueller Index kann überschrieben werden. | **flüchtige unvollständige Assemblierung**; mangels Assembler-Timeout eventuell erst durch Replug/Neustart bereinigbar. |
| Unvollständiger Transfer | Decoder und Displaycommit starten nicht; der Assembler besitzt keinen belegten Timeout. | **flüchtig bis Replug/Neustart nötig**; kein weiterer Frame als improvisierte Recovery. |
| JPEG-Decoderfehler | v51 meldet den Fehler nicht an den Host. Bei Decoderende kann die Queue freigegeben und ein Zielknoten dennoch ready markiert werden; bleibt Active gesetzt, greift die Lease. | **flüchtig**: unverändertes Bild, leerer/fehlerhafter Frame oder Artefakt; eventuell Neustart nötig. |
| Lease-Timeout | Queue wird ohne Ready-Markierung freigegeben, während kein sichtbarer Decoderstopp erfolgt. | **flüchtig bis Neustart nötig**. Kein zweiter Frame verhindert eine erneute Nutzung desselben Queuebereichs durch diesen Test. |
| Queue bleibt belegt | Möglich bei abweichendem v49-Lifecycle oder nicht ablaufender Lease; weitere Bilder könnten blockiert sein. | **flüchtig**, gegebenenfalls durch Replug/Display-/Geräteneustart behebbar. |
| USB-Stall | Ein Write scheitert oder Endpoint bleibt gestallt. Ohne Retry endet die Sequenz sofort. | meist **flüchtig**, gegebenenfalls USB-Replug nötig. Kein Recovery-Command. |
| Display bleibt unverändert | Queue-/Decoderfehler, Lease-Ablauf ohne Ready oder fehlender Commit. | **flüchtiger funktionaler Fehlschlag**; keine Persistenzimplikation. |
| Display zeigt Artefakte | Decoderfehler oder fehlerhafter Zielbuffer wird sichtbar. | **flüchtig**, bis zu einem später autorisierten gültigen Frame oder Neustart; dieser Test sendet keinen zweiten Frame. |
| USB-Replug erforderlich | Endpoint-, Assembler-, Queue- oder Decoderzustand erholt sich nicht selbst. | **durch Replug/Neustart behebbar**; nur als menschlich kontrollierte Recovery, nicht automatisiert. |
| Gerät-/Displayneustart erforderlich | Flüchtiger Firmware-/MMIO-Zustand übersteht ein bloßes Schließen des Deskriptors. | **durch Neustart behebbar**; thermische und elektrische Betriebsgrenzen der Kühlung müssen dabei menschlich beachtet werden. |
| Persistenter Schaden | Erfordert eine der in Abschnitt 2.3 beschriebenen, für v49 unbelegten neuen Kanten. Im v51-`0x08`-Pfad fehlt ein solcher Mechanismus. | **theoretisch persistent**, aber ohne positiven Beleg und nicht aus den normalen Failure Modes ableitbar. |

### 5.1 Erneuter Persistenz-Crosscheck

| Zielpfad | v51 ab Interface-1-`0x08` | Reales, sehr wahrscheinlich v49-basiertes Gerät |
| --- | --- | --- |
| SPI-Write | **nein**, nur hinter getrenntem `0x88`-Pfad | **unbekannt** mangels v49-Binärdatei; kein positiver Hinweis |
| Flash-Write | **nein**, getrennte Befehle/Backends | **unbekannt**; kein positiver Hinweis |
| Bootloader/Firmwareupdate | **nein**, getrennte `0x86`-/`0x02`-/Updaterpfade | **unbekannt**; kein positiver Hinweis |
| Persistente Konfigurationsänderung | **nein**; `0x08` liest `config+0x108` nur in einen RAM-Countdown | **unbekannt**; kein positiver Hinweis |

Gesamtantwort auf „persistente Pfade erreichbar?“: **für v51 nein; für das
reale, sehr wahrscheinlich v49-basierte Gerät formal unbekannt**. Aus den
vorhandenen Belegen ist kein erreichbarer persistenter Mechanismus abzuleiten.

## 6. Quantitative technische Risikoklassen

Die Klassen sind ordinale technische Bewertungen, keine statistischen
Wahrscheinlichkeiten.

| Ergebnis | Risikoklasse | Begründung |
| --- | --- | --- |
| Temporärer Fehler, unverändertes Bild oder Artefakt | **niedrig** | Erster eigener Interface-1-Lauf und fehlende v49-/Done-Evidenz bleiben relevant; Hostformat, Zielprodukt, JPEG-Untermenge und Padding sind dagegen eng geschlossen. |
| USB- oder Displayhänger | **niedrig** | v51 besitzt Lease- und Queuefreigabe, aber der Timeout stoppt den Decoder nicht sichtbar und v49 ist nicht binär geprüft. Kein Retry und kein zweiter Frame begrenzen die Wirkung. |
| USB-Replug oder Gerät-/Displayneustart nötig | **niedrig** | Möglich bei Stall, unvollständiger Assemblierung oder abweichendem v49-Lifecycle; es gibt keinen positiven Beleg, dass der ASUS-Normaltransfer diesen Zustand auslöst. |
| Persistente Beschädigung | **sehr niedrig** | v51 erreicht weder SPI, Flash, Updater, Boot noch persistente Konfiguration. v49 müsste eine konkrete neue gefährliche Kante besitzen; dafür gibt es keinen positiven Befund, während der ASUS-Host exakt dieses Produkt und Format adressiert. Wegen der fehlenden v49-Binärdatei ist das Risiko nicht als null beweisbar. |

## 7. GO/NO-GO

**GO: Ein einmaliger minimaler JPEG-Test ist ausreichend spezifiziert.**

Die Entscheidung stützt sich auf das bytegenau geschlossene ASUS-Hostformat,
die exakte v51-Kompatibilität, die konservativ eingegrenzte
Hardware-JPEG-Untermenge, das ASUS-belegte Nullpadding und die fehlende
Persistenzkante im v51-`0x08`-Pfad. Die formale v49-Unbekannte bleibt offen,
ist aber auf konkrete strukturelle Änderungen eingegrenzt und besitzt keinen
positiven Gefahrenbeleg.

Das GO gilt ausschließlich unter allen Gates aus Abschnitt 3 und 4: ein
offline validiertes, eingefrorenes Minimal-JPEG; dynamische und erneute
Identitätsprüfung; Erfolgspfad mit genau `N` Writes; sofortiger Abbruch ohne
Retry bei jeder Abweichung; keine Interface-0-Kommunikation; kein EP-`0x84`-
Read; keine weiteren Commands; Descriptor schließen; kein zweiter Frame.

Ein Folgeticket darf zunächst die Offline-Artefakterzeugung, Validierung und
Pufferprüfung implementieren. Gerätekommunikation bleibt bis zu einer neuen,
ausdrücklichen Freigabe für genau diesen Einmaltest untersagt.
