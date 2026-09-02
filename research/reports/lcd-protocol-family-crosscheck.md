# Statischer Cross-Check der LCD-Protokollfamilie

Stand: 2026-09-02

## Zweck und Grenze

Dieser Bericht vergleicht den rekonstruierten LCD-Transport des ASUS-Geräts
`0b05:1c7b` eng begrenzt mit drei öffentlich dokumentierten Implementierungen
beziehungsweise Reverse-Engineering-Berichten verwandter LCD-Geräte. Die
Quellen wurden am 2026-09-02 tatsächlich online geprüft:

- [`ttlcd`, README](https://github.com/bekindpleaserewind/ttlcd) und
  [`ttlcd.py`](https://github.com/bekindpleaserewind/ttlcd/blob/main/ttlcd.py)
- [`th420-display`, README](https://github.com/messiahlap/th420-display) und
  [`src/device.rs`](https://github.com/messiahlap/th420-display/blob/main/src/device.rs)
- [„Reverse-engineering the Thermaltake TH420 V2 Ultra LCD protocol“](https://www.devsstuff.com/posts/th-linux-lcd)

Die Links zeigen jeweils den beim Abruf aktuellen `main`-Stand; mangels lokalem
Netzwerkzugriff konnte kein Commit-SHA über `git ls-remote` fixiert werden. Die
Onlineinhalte selbst waren über den Recherchezugang verfügbar. Der Blog ist
eine veröffentlichte Sekundärbeschreibung eines Hersteller-Captures, nicht der
Capture selbst. Seine Aussagen werden deshalb nicht wie unmittelbar vorliegende
URB-Rohdaten behandelt.

Es gab keine Gerätekommunikation, keinen HID-Write, keine Installation und
keine neue Ghidra-Analyse. Die ASUS-Seite stammt ausschließlich aus dem bereits
dokumentierten Firmware-, Descriptor- und Realgerätebefund.

## Bewertungsbegriffe

| Klasse | Bedeutung in diesem Bericht |
| --- | --- |
| **identisch bestätigt** | Der konkrete Wert oder Ablauf ist auf beiden Seiten unmittelbar belegt. |
| **strukturell kompatibel** | Aufbau und Verhalten passen ohne Widerspruch zusammen, die ASUS-spezifische Ausprägung ist extern aber nicht unmittelbar beobachtet. |
| **nur ähnlich** | Gleiche grobe Funktion, jedoch keine hinreichend spezifische Feldgleichheit. |
| **widersprüchlich** | Zwei Befunde verlangen für dasselbe Feld beziehungsweise denselben Ablauf unterschiedliche Werte. |
| **unbekannt** | Die öffentliche Quelle oder die ASUS-Analyse belegt den Vergleichspunkt nicht. |

„Identisch“ bedeutet dabei nicht „dieselbe Firmware“ oder „derselbe OEM“.

## 1. Feldweiser Vergleich

| Vergleichspunkt | ASUS `0b05:1c7b` | Öffentliche verwandte Quellen | Bewertung |
| --- | --- | --- | --- |
| USB-Aufteilung | zwei HID-Interfaces: Steuerung auf Interface 0, Bild auf Interface 1 | Blog beschreibt dieselbe Zweiteilung; beide Programme öffnen getrennte Control-/Image-Interfaces | **identisch bestätigt** |
| Control-Endpunkte | `0x01` OUT, `0x82` IN | Blog nennt exakt `0x01` OUT und `0x82` IN | **identisch bestätigt** |
| Bild-Endpunkte | `0x03` OUT, `0x84` IN | Blog nennt exakt `0x03` OUT und `0x84` IN | **identisch bestätigt** |
| Control-Report | 440 Byte auf dem Draht, 4 + 436 | `ttlcd` und `th420-display` bauen 440-Byte-Controlreports; der Blog beschreibt 440-Byte-ACKs | **identisch bestätigt** |
| Bild-OUT-Report | 1024 Byte, 4 + 1020 | beide Programme verwenden 1024 beziehungsweise 1020; der Blog zeigt 1024-Byte-Transfers | **identisch bestätigt** |
| Bild-IN-Report | 16 Byte | `ttlcd` liest 16 Byte; Blog beschreibt EP `0x84` IN als 16-Byte-Pfad | **identisch bestätigt** |
| Bildbefehl | Byte 0 = `0x08` | beide Programme und Blog verwenden `0x08` | **identisch bestätigt** |
| erstes Segment bei `N=3` | `08 03 00 80` | exakt dieses Wort erscheint in beiden Sendern und im veröffentlichten Trace | **identisch bestätigt** |
| Erstsegmentbit | Little-Endian-Bit 31, also Bit 7 von Byte 3 | öffentliche Sender setzen nur im ersten Bildreport Byte 3 auf `0x80` | beobachtete Verwendung **identisch bestätigt**; die allgemeine Exklusivbedeutung des Bits extern **unbekannt** |
| Segmentzahl | ASUS: 23-Bit-Feld in Bits 8..30, normal `1 <= N <= 200` | Sender legen `N` nur in Byte 1 und lassen Bytes 2/3 außer First-Bit null | für `N <= 255` **strukturell kompatibel**; externe 23-Bit-Semantik **unbekannt** |
| Folgeindex laut Sendercode | ASUS: `i=1..N-1`, also bei `N=3` `08 01 00 00`, `08 02 00 00` | `ttlcd.py` und `device.rs` erzeugen ebenfalls `1..N-1` | **identisch bestätigt** |
| Folgeindex laut Blogtrace | ASUS verlangt bei `N=3` `1,2` | Blog zeigt nach dem Erstreport `2,3` | **widersprüchlich** |
| Bildformat | direkter JPEG-Hardwaredecoder; konservativ Baseline/SOF0 | `ttlcd` fordert non-progressive JFIF; Blog und TH420-Code senden JPEG | Baseline-JPEG **strukturell kompatibel**; Decodergrenzen geräteübergreifend **unbekannt** |
| letzter Report | ASUS kopiert stets alle 1020 Nutzbytes, ohne Restlänge | beide Sender schreiben immer einen vollen 1024-Byte-Report | **identisch bestätigt** für die Transportlänge |
| Inhalt hinter EOI | ASUS-Firmware bewahrt und übergibt jedes Suffixbyte; kein eigener Producer | beide Sender nullinitialisieren den Report; Blog beschreibt Nullsuffix im Herstellertransfer | **strukturell kompatibel**, nicht ASUS-spezifisch bestätigt |
| EP-`0x84`-Read | Firmware stellt einmal `08 81 ...` bereit, nachdem Queue und Ziel frei sind, vor Decoderstart | `ttlcd` liest nach einem Frame 16 Byte; Blog verlangt einen Read nach jedem Frame | Readmuster **strukturell kompatibel**; Inhalt und genaue Bedeutung **unbekannt** |
| EP-`0x84`-Inhalt | Präfix `08 81`, Rest ohne belegte Semantik | Blog beschreibt für das TH420-Gerät 16 Nullbytes | als geräteübergreifende Bytefolge **widersprüchlich**; kein Widerspruch gegen den jeweiligen gerätespezifischen Pfad |
| Controlfamilie `0x80..0x87` | Dispatcher besitzt Antworten für `0x80..0x87`; `0x87` liefert v51 `0x0051`, reales v49-Gerät `0x0049` | `ttlcd` und TH420-Code verwenden unter anderem `0x80`, `0x81`, `0x82`, `0x84`, `0x85`, `0x87` mit demselben `xx 01 00 80`-Rahmen | Nummern und Rahmen **strukturell kompatibel**; Befehlssemantik außer Familienindiz **unbekannt** |

### 1.1 Interner Widerspruch der öffentlichen Folgeindizes

Die öffentliche Vergleichslage darf nicht zu einer einzigen angeblich
beobachteten Regel zusammengezogen werden:

- `ttlcd.py` beginnt `pkt_index` bei 1. Nach dem Erstreport erzeugt es daher
  für drei Segmente die Folgefelder 1 und 2.
- `th420-display/src/device.rs` setzt für Chunk `i > 0` unmittelbar Byte 1 auf
  `i`; auch daraus folgen 1 und 2.
- Der TH420-Blog druckt dagegen 2 und 3 und beschreibt den letzten Wert als
  Gesamtzahl.

Damit stimmen die beiden aktuell veröffentlichten Sender mit der statisch
rekonstruierten ASUS-Regel überein. Der abgedruckte Blogtrace widerspricht
dieser Regel. Ohne die zugrunde liegenden URBs lässt sich nicht entscheiden,
ob eine Firmwarevariante, eine Transkriptionsverschiebung oder ein anderer
Zählbegriff vorliegt. Für ASUS bleibt die v51-Firmwareanalyse die direkte
Evidenz; die öffentliche Inkonsistenz darf nicht in ASUS-Code „gemittelt“
werden.

## 2. Nullpadding und letzter JPEG-Block

### 2.1 Tatsächliches Verhalten der öffentlichen Sender

Beide geprüften Sender implementieren dasselbe konkrete Verfahren:

```text
N = ceil(jpeg_length / 1020)
packet = 1024 vollständig mit 0x00 initialisieren
packet[0:4] = Controlword
packet[4:4+chunk_length] = nächster JPEG-Chunk
vollen 1024-Byte-Report senden
```

Bei einer nicht durch 1020 teilbaren JPEG-Länge stehen damit nach dem letzten
JPEG-Byte bis Nutzbyte 1019 ausschließlich Nullen. Liegt EOI `ff d9` am Ende
des JPEGs, ist der Suffix nach EOI folglich vollständig `00`. Ist die Länge
durch 1020 teilbar, gibt es keinen transportspezifisch ergänzten Suffix und
kein zusätzliches Leersegment. `ttlcd.py` setzt das Padding ausdrücklich über
den „right padding“-Pfad; `th420-display` erreicht dasselbe durch den
nullinitialisierten `[u8; 1024]`-Puffer vor dem Kopieren des Chunks. Der Blog
beschreibt Nullpadding außerdem als Ergebnis mindestens eines realen
Herstellertransfers.

### 2.2 Exakte Kompatibilität mit dem ASUS-Consumer

Das Verfahren passt bytegenau zum ASUS-Firmwarepfad:

1. Der Host sendet immer 1020 Nutzbyte.
2. Die Firmware kopiert immer genau 1020 Nutzbyte je Segment.
3. EOI darf innerhalb des letzten Blocks liegen.
4. Die nachfolgenden Nullen werden unverändert in die Queue kopiert und an den
   Hardwaredecoder weitergereicht.
5. Es gibt weder eine separate JPEG-Restlänge noch einen Suffixstripper.
6. Da keine separate Restlänge bis zum Hardwaredecoder gelangt, ist EOI die
   statisch stark gestützte Bitstrom-Endmarke; die Transportlänge bleibt
   unabhängig davon `N*1020`. Eine reale ASUS-v49-Toleranzprüfung folgt daraus
   nicht.

Nullpadding erfordert somit keine im ASUS-Pfad fehlende Sonderbehandlung und
verhindert, dass unbeabsichtigte beziehungsweise nicht deterministische
Pufferreste hinter EOI übertragen werden. Es ist die am besten belegte und
konservativste Hostbildung.

Die Evidenzklasse bleibt dennoch **strukturell kompatibel**, nicht „identisch
bestätigt“: Keine der drei Quellen zeigt einen Transfer des ASUS-Geräts
`0b05:1c7b`, und der ASUS-Hostproducer beziehungsweise ein ASUS-Capture liegt
nicht vor. Die Quellen belegen außerdem nicht unmittelbar, wie der konkrete
N9H20-Pfad des realen v49-ASUS-Geräts auf den Suffix reagiert. Sie erhöhen die
Plausibilität stark, ersetzen aber keine ASUS-spezifische Beobachtung.

## 3. EP `0x84` und `08 81`

Die auffällige Gemeinsamkeit ist ein eigener 16-Byte-IN-Kanal auf demselben
Bildinterface. `ttlcd` führt nach dem abgeschlossenen Frameversand einen
16-Byte-Read aus. Der Blog beschreibt ebenfalls einen Read nach jedem Frame
und berichtet, ohne Drain könne das verwandte Gerät blockieren. Das aktuell
veröffentlichte `th420-display/src/device.rs` führt dagegen nach seinen
Bild-OUT-Reports keinen Image-IN-Read aus; es liest nur in Controlpfaden. Damit
ist selbst die öffentliche Hostpraxis nicht vollständig einheitlich.

Für die zeitliche Interpretation ist USB-IN-Polling entscheidend: Ein Hostread
nach dem letzten OUT beweist nicht, dass das Gerät die Nachricht erst nach
JPEG-Decodierung erzeugt hat. Er kann eine bereits vorher bereitgestellte
Nachricht abholen. Das externe Readmuster ist daher vollständig damit
vereinbar, dass ASUS `08 81` nach Queueannahme und Zielbufferprüfung, aber vor
Decoderstart bereitstellt.

Der Cross-Check stützt somit die enge Bezeichnung **framebezogene
Annahme-/Startnachricht beziehungsweise zu drainender Bildkanal**. Er stützt
nicht „Decoder fertig“: Der ASUS-Erzeuger liegt statisch vor Decoderstart, und
der Hostzeitpunkt des Reads kann diese Reihenfolge nicht umkehren. Ebenso darf
aus den im Blog berichteten 16 Nullbytes nicht geschlossen werden, dass ASUS
Nullbytes senden müsse. `08 81` und ein Nullreport sind auf Byteebene
verschieden; geräteübergreifende Statuswerte sind nicht belegt.

Offen bleiben für das reale ASUS-v49-Gerät:

- ob es ebenfalls exakt `08 81` erzeugt;
- wann der Host den IN-URB einreicht und wann er abgeschlossen wird;
- ob genau ein Read zwingend nötig ist, um den Bildkanal wieder freizugeben;
- ob nach Decoderende oder Fehler noch weitere IN-Nachrichten entstehen.

## 4. Controlfamilie `0x80..0x87`

Die Gemeinsamkeit geht über einen einzelnen Versionsbefehl hinaus. Die
verwandten Sender verwenden 440-Byte-Reports im Rahmen
`command 01 00 80 | Padding` und senden in ihren Initialisierungs-/Statuspfaden
mehrere Werte aus derselben dicht belegten Familie, insbesondere `0x81`,
`0x84`, `0x85` und `0x87`; außerdem treten `0x80` und `0x82` auf. ASUS besitzt
im selben 440-Byte-Transport Antwortcases für den lückenlosen Bereich
`0x80..0x87`. Der reale ASUS-Test bestätigt konkret den Rahmen
`87 01 00 80` und die gleich gerahmte Antwort.

Das ist wegen der Kombination aus Befehlsbereich, Controlwordform,
Reportgröße und Antwortkanal ein starkes Strukturindiz. Die Nutzsemantik darf
aber nicht übertragen werden:

- ASUS `0x87` ist als Versionswertpfad belegt; die öffentlichen Programme
  benennen beziehungsweise verwenden den Befehl nicht mit einem für ASUS
  beweiskräftigen identischen Antwortpayload.
- Externe Bedeutungen wie Kühlmitteltemperatur, Initialisierung oder Keepalive
  beweisen nicht dieselbe Bedeutung im ASUS-Dispatcher.
- ASUS `0x86` bleibt wegen des Updater-/Firmwareblockpfads ausdrücklich
  kritisch; seine Nummernähnlichkeit erteilt keinerlei Testfreigabe.

## 5. Evidenz für einen gemeinsamen Protokollstamm

Für einen gemeinsamen Protokollstamm spricht nicht ein generisches Merkmal wie
„USB-HID“ oder „JPEG“, sondern die ungewöhnlich spezifische Merkmalskombination:

1. zwei getrennte HID-Interfaces mit derselben Control-/Bildrollenverteilung;
2. exakt dieselben vier Endpointadressen `01/82` und `03/84`;
3. exakt 440 Byte bidirektional im Controlpfad;
4. exakt 1024 Byte OUT und 16 Byte IN im Bildpfad;
5. exakt 4 Byte Header plus 1020 Byte JPEG;
6. Bildbefehl `0x08`;
7. Erstwort `08 N 00 80` und indexierte Folgereports;
8. ein framebezogener Read auf dem 16-Byte-Bild-IN-Kanal;
9. dieselbe dicht belegte `0x80..0x87`-Controlfamilie und insbesondere der
   Rahmen `87 01 00 80`.

In Summe ist ein gemeinsamer Protokollstamm **stark gestützt**. Das ist eine
technische Abstammungshypothese, keine Identitätsfeststellung. Die Quellen
belegen weder denselben OEM noch identische Firmware, Hardwaredecoder,
Displaygeometrie oder Befehlssemantik. Verschiedene VID/PID, unterschiedliche
Displaygrößen, der Folgeindexwiderspruch und verschiedene berichtete
EP-`0x84`-Inhalte zeigen gerade, dass Varianten existieren.

## 6. Sicherheitsbewertung für einen späteren ASUS-Einmaltest

### 6.1 Was der Cross-Check jetzt trägt

Für die isolierte Frage „welche Bytes sollen nach EOI stehen?“ ist
Nullpadding nun deutlich mehr als eine unbelegte Vermutung:

- zwei öffentliche Hostproducer erzeugen es deterministisch;
- eine veröffentlichte Hersteller-Capturebeschreibung berichtet es real;
- es ist exakt mit der v51-ASUS-Vollblockkopie und dem Fehlen einer Restlänge
  kompatibel;
- es minimiert den Suffixinhalt und vermeidet Datenreste.

Nullpadding ist damit die **ausreichend begründete konservative Kandidatenregel**
für eine spätere Testspezifikation. Es ist aber noch keine ASUS-v49-bestätigte
Tatsache.

### 6.2 Verbleibende ASUS-spezifische Unsicherheiten

Ein ASUS-eigener passiver Referenzcapture bleibt für den verlangten Maßstab
„sicher und exakt“ erforderlich, weil er weiterhin nur Folgendes klären kann:

- tatsächlicher letzter Block und Nullsuffix des offiziellen ASUS-Producers;
- reale Folgeindizes auf Firmware v49, trotz der öffentlichen
  `1,2`-gegen-`2,3`-Inkonsistenz;
- tatsächlicher Inhalt und das URB-Timing von EP `0x84`, insbesondere `08 81`;
- ob der ASUS-Host den 16-Byte-IN-Pfad pro Frame zwingend drainiert und ob
  weitere IN-Reports folgen;
- begleitende ASUS-Interface-0-Befehle, darunter eine mögliche Änderung von
  `config+0x108` beziehungsweise der Decoderquellen-Lease;
- v49/v51-Gleichheit des Bildpfads und das reale sichtbare Commitverhalten;
- die tatsächlich vom offiziellen ASUS-Producer gewählte JPEG-Untermenge.

Der Cross-Check ändert daher nicht die Freigabeentscheidung: Noch kein eigener
JPEG-Write. Er reduziert die Paddingunsicherheit auf eine stark begründete
Arbeitshypothese, ersetzt aber den geplanten passiven ASUS-Referenzcapture
nicht.

## 7. Reproduzierbarkeit und Quellenkritik

Die zentralen öffentlichen Codebefunde sind direkt in diesen Funktionen
prüfbar:

- `ttlcd.py`: `IMAGE_PACKET_SIZE`, `USBImage.send_image`,
  `USBImage.send_image_bytes`, `USBImage.trigger_thread` und
  `USBControl.init_device`;
- `th420-display/src/device.rs`: `CTRL_SIZE`, `IMG_PKT_SIZE`,
  `IMG_DATA_SIZE`, `initialize`, `send_frame`, `ctrl_write`, `ctrl_read` und
  `img_write`;
- TH420-Blog: Abschnitte „USB interface layout“, „Frame start packet“,
  „JPEG image data packets“, „Drain the image interface“ und die
  Beispielpakete des 3-Segment-Frames.

Der Blogtrace wurde wegen seines Widerspruchs zum Code nicht als universelle
Felddefinition übernommen. Aussagen aus dem vom Auftrag bereitgestellten
Vergleichsmaterial, die durch die geöffneten Quellen nicht genauer belegt
werden konnten, wurden nicht darüber hinaus erweitert.
