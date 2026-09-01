# Statische Rekonstruktion des LCD-Datenpfads 01

Stand: 2026-09-02

## Zweck und Sicherheitsrahmen

Diese Analyse setzt die Vorbereitung aus
`research/reports/lcd-command-analysis-prep.md` fort. Untersucht wurde
ausschließlich die extrahierte v51-Firmware statisch in Ghidra 12.1. Das
vorhandene Projekt wurde mit `-readOnly -noanalysis` geöffnet. Es gab keine
Gerätekommunikation, Emulation, Paketübertragung, Installation oder Änderung
von Firmware-Schreibrechten.

Der neue Export `research/ghidra-scripts/ExportLcdDataPath.java` disassembliert
die bisher nicht als Funktion definierte Endpoint-3-Routine nur transient in
der Read-only-Sitzung. Ghidra verwirft diese Analyseänderung beim Schließen.
Der Export selbst enthält Dekompilate, Instruktionen, Datenreferenzen und
Querverweise auf identische globale Zeigerwerte.

Reproduzierbarer Aufruf:

```text
analysis_tmp=$(mktemp -d /tmp/tuf-aio-lcd-path.XXXXXX)
env XDG_CONFIG_HOME="$analysis_tmp/config" \
  /home/l/HeartdriveLAB/shared/tools/ghidra/ghidra_12.1_PUBLIC/support/analyzeHeadless \
  research/ghidra-projects device-firmware-v51-ghidra12-1 \
  -process device-firmware-v51.bin -readOnly -noanalysis \
  -scriptPath research/ghidra-scripts \
  -postScript ExportLcdDataPath.java "$analysis_tmp/lcd-data-path.txt"
```

## Wichtigste neue Erkenntnis

Die bisher offene Queue-Beziehung ist geschlossen. Endpointcallback
`0x0010df9c` und Konsument `0x00129b2c` verwenden exakt dieselbe Queue bei
`0x003bb430`:

```text
Interface 1 / Endpoint 0x03 OUT
  -> DMA-Reportpuffer 0x003ed520, 1024 Byte
  -> Callback 0x0010df9c
  -> Segmentempfänger 0x001297e8
  -> separater Assemblierungszustand 0x003bb480
     Daten ab +0x10, höchstens 200 × 1020 = 204000 Byte
  -> bei vollständigem Befehl 0x08:
     Ringqueue 0x003bb430
     Backing-Buffer 0x003edb40, Kapazität 0x32000 = 204800 Byte
  -> Konsument 0x00129b2c
  -> Grafikrouter 0x001065c4
```

Die zweite Queue bei `0x003bb458` mit Backing-Buffer `0x0041fb40` gehört
dagegen zum 440-Byte-Transport von Interface 0. Sie ist nicht die Queue des
Interface-1-Großdatenpfads.

## 1. Transport- und Queue-Modell

### 1.1 Relevante Speicherobjekte

| Rolle | Adresse | Beleg |
| --- | --- | --- |
| Endpoint-3-DMA-Reportpuffer | `0x003ed520` | Callback lädt den Zeiger und armiert Endpointselektor 3 für `0x400` Byte |
| 1024-Byte-Assemblierungszustand | `0x003bb480` | direkter erster Parameter von `0x001297e8` |
| Assemblierte Daten | `0x003bb490` | Zustandsbasis `+0x10`; Segmentkopien mit je `0x3fc` Byte |
| Interface-1-Ringqueue | `0x003bb430` | Produzent in `0x0010df9c`, Konsument in `0x00129b2c` |
| Backing-Buffer dieser Queue | `0x003edb40` | Initialisierung in `0x001293f8` mit `0x32000` Byte |
| Interface-0-Ringqueue | `0x003bb458` | getrennte Initialisierung und Verarbeitung in `0x001293f8` |
| Backing-Buffer von Interface 0 | `0x0041fb40` | Initialisierung mit weiteren `0x32000` Byte |

Der Assemblierungsbereich endet rechnerisch bei `0x003ed170`. DMA-Puffer und
Queue-Backing-Buffer liegen dahinter und überlappen ihn nicht.

### 1.2 Steuerwort und Segmentierung

Das 1024-Byte-Drahtpaket hat dieses belegte Format:

```text
Offset  Größe  Bedeutung
0x000   4      Little-Endian-Steuerwort
0x004   1020   Segmentnutzlast; immer vollständig kopiert
```

Im Steuerwort gelten:

- Bits `0..7`: Befehl;
- Bits `8..30`: im Erstsegment die erwartete Segmentanzahl, danach der
  Segmentindex;
- Bit `31`: Erstsegmentkennzeichen.

Beim Erstsegment speichert `0x001297e8` den Befehl, setzt den letzten Index auf
null, speichert die erwartete Segmentanzahl und kopiert 1020 Byte an
`state + 0x10`.

Ein Folgesegment wird nur für denselben Befehl akzeptiert. Sein Index darf dem
zuletzt akzeptierten Index entsprechen oder genau um eins größer sein. Damit
wird ein Duplikat erneut an denselben Offset kopiert; ein unmittelbarer
Nachfolger wird angehängt. Sprünge und andere Reihenfolgen werden nicht
übernommen. Nur Indizes kleiner als 200 werden kopiert.

Der Transfer gilt als vollständig, sobald

```text
erwartete_segmentanzahl <= letzter_index + 1
```

ist. Für einen normalen Hosttransfer folgt daraus die Indexfolge `0..N-1`.
Eine separate Endmarkierung existiert nicht.

### 1.3 Länge, Abschluss und Integrität

Für einen vollständigen Interface-1-Befehl `0x08` berechnet der Callback die
weitergereichte Länge ausschließlich als

```text
N × 1020 Byte
```

Dabei ist `N` die Segmentanzahl des Erstsegments. Es gibt in diesem Pfad keine
separate tatsächliche Länge des letzten Segments, keine Transportprüfsumme und
keine beobachtete Nutzdaten-Endmarkierung. Der letzte 1020-Byte-Block ist daher
aus Sicht der Firmware vollständig Teil des Queueobjekts; mögliches Padding
muss in diesem Block enthalten sein.

Die statisch nutzbare Obergrenze des Assemblers beträgt 200 Segmente oder
204000 Byte. Das Feld `N` selbst wird nicht vorab gegen 200 geprüft;
Folgeindizes ab 200 werden lediglich nicht mehr kopiert. Ein daraus
berechneter Queueeintrag ab 201 Segmenten passt nicht mehr in den Ringpuffer,
sodass `0x0012a3f0` null zurückgibt und der Callback keinen Payload kopiert.
Auch `N = 0` erzeugt keinen Queueeintrag. Ein rekonstruierter Hostparser muss
daher nur `1 <= N <= 200` als weiterleitbaren Bereich behandeln.

Der Queueallocator `0x0012a3f0` legt vor dem Payload ein vier Byte langes
Längenfeld an und richtet den gesamten Eintrag auf vier Byte aus. Ein maximaler
Eintrag belegt somit 204004 Byte und passt in den `0x32000` Byte großen
Ringpuffer.

### 1.4 Übergabe an die gemeinsame Queue

Nach Abschluss von `0x08` ruft `0x0010df9c` auf:

```text
payload = queue_allocate(0x003bb430, N * 1020)
if payload != 0:
    memcpy(payload, 0x003bb480 + 0x10, N * 1020)
```

`0x0012a3f0` ist kein bloßer Heapallocator, sondern reserviert und veröffentlicht
einen Eintrag im Ringpuffer. Das gespeicherte Layout ist:

```text
uint32_le payload_length
uint8_t   payload[payload_length]
padding bis zur nächsten Vier-Byte-Grenze
```

Der Konsument ruft `0x0012a390(0x003bb430, &payload, 0)` auf. Die Funktion
liefert das vier Byte lange Längenfeld als Rückgabewert und `entry + 4` als
Payloadzeiger. `0x00129b2c` prüft die Länge nur auf ungleich null; er reicht
die Länge nicht an den Grafikrouter weiter. Nach Abschluss oder Abbruch des
Grafikvorgangs gibt `0x0012a310` den vordersten Queueeintrag frei.

## 2. Vollständiger Interface-1-Datenpfad

Der belegte Pfad für `0x08` lautet:

```text
0x03 OUT / 1024 Byte
  -> 0x0010df9c
     - armiert Endpoint 3 mit DMA-Puffer 0x003ed520
     - ruft 0x001297e8(0x003bb480, report)
  -> 0x001297e8
     - prüft Befehl und Segmentfolge
     - assembliert 1020-Byte-Blöcke ab 0x003bb490
     - signalisiert Abschluss nach N Segmenten
  -> 0x0010df9c
     - reserviert N*1020 Byte in Queue 0x003bb430
     - kopiert den vollständigen Assemblierungsbereich in die Queue
  -> 0x00129b2c
     - wartet auf freien Grafikzustand
     - liest Länge und Payloadzeiger aus Queue 0x003bb430
     - verwirft die Länge nach der Nichtnullprüfung
     - startet die Routerfolge
  -> 0x001065c4(8, 0x6021, 0)
  -> 0x001065c4(0, descriptor | 0x80000000, 0)
  -> 0x001065c4(0x11, 0x00115110, 0)
  -> 0x001065c4(4, payload | 0x80000000, 0)
  -> 0x001065c4(0x0c, 0, 0)
```

Der Descriptorzeiger stammt nicht aus der Interface-1-Nutzlast. Er wird über
das gemeinsam genutzte Objekt hinter `0x001314d0` bezogen. Seine dynamische
Initialisierung und Feldstruktur sind noch nicht vollständig rekonstruiert.
Damit sind Datenzeiger und Datenlebensdauer belegt, die vollständige Semantik
des zugehörigen Descriptors aber noch offen.

Die Queue bleibt während des Grafikvorgangs belegt. `0x00129b2c` setzt seinen
Busy-Zustand, fragt anschließend `0x00105e60` ab und gibt den Queueeintrag erst
beim beobachteten Abschluss oder einem Abbruch frei. Der Grafikpfad arbeitet
also direkt auf dem Queue-Backing-Buffer; der Payload darf nicht vorzeitig
überschrieben werden.

## 3. Typisierung des Grafikrouters

Für den untersuchten Pfad sind diese Operationen von `0x001065c4` belegt:

| Operation | Wirkung |
| ---: | --- |
| `8` | validiert und speichert einen Grafikmodus über `0x00106058` |
| `0` | speichert den Descriptor-/Basiszeiger in der Grafikstruktur bei `+0x7c` |
| `0x11` | speichert einen Callback-/Funktionszeiger im Kernzustand bei `+0x10` |
| `4` | speichert den Datenzeiger in der Grafikstruktur bei `+0xa0` |
| `0x0c` | startet den vorbereiteten Vorgang über `0x001060ec` |
| `0x0f` | speichert zwei Dimensionswerte im Kernzustand |
| `0x0e` | speichert einen weiteren Dimensions-/Stridewert bei `+0x18` |

`0x001060ec` setzt den Aktivzustand, initialisiert einen 0x24-Byte-Block und
schaltet den vorbereiteten Hardware-/DMA-Zustand frei. Im direkten Pfad von
`0x00129b2c` werden keine Breite, Höhe oder Koordinaten über die Operationen
`0x0e`/`0x0f` gesetzt. Diese Werte müssen daher bereits durch den gemeinsam
genutzten Descriptor oder vorherigen Zustand bestimmt sein.

Der Wert `0x80000000`, der auf Descriptor- und Datenzeiger gesetzt wird, ist
ein firmwareinternes Adress-/Attributbit. Seine genaue Cache- oder
Busbedeutung ist nicht belegt und darf hostseitig nicht als Teil der
Nutzdaten interpretiert werden.

## 4. Datenformat und Beziehung zu `0x32000`

### 4.1 Belegte 16-Bit-Klasse, aber offene Kanalordnung

Der Interface-1-Konsument verwendet immer den Grafikmodus `0x6021`.
`0x00106058` akzeptiert eine kleine Familie verwandter Werte, benennt ihre
Semantik aber nicht.

Der unabhängige Objekt-/JPEG-Renderer `0x0011acd8` liefert einen wichtigen
Vergleich:

- bei internem Tiefenwert `0x20` kopiert er vier Byte pro Pixel und verwendet
  Grafikmodus `0x14021`;
- im alternativen Pfad kopiert er zwei Byte pro Pixel und verwendet
  Grafikmodus `0x6021`.

Damit ist gut belegt, dass `0x6021` den 16-Bit-Klassenpfad des Grafikunterbaus
auswählt. Nicht belegt sind RGB565 gegenüber einer anderen 16-Bit-Belegung,
Byteorder, Kanalreihenfolge, Alpha oder eine mögliche Vorverarbeitung durch
den Descriptor.

### 4.2 Vollframe bleibt unbewiesen

`0x32000` hat zwei gleichzeitig passende Interpretationen:

- `320 × 320 × 2 = 204800` Byte, also exakt ein 16-Bit-Vollframe;
- `200 × 1024 = 204800` Byte, entsprechend den Parametern eines
  Renderer-Pufferkonstruktors und der Queuekapazität.

Der Interface-1-Assembler kann jedoch höchstens `200 × 1020 = 204000` Byte
weiterreichen. Es fehlen 800 Byte zu einem ungepackten 320×320×16-Bit-Frame.
Da keine separate Restlänge und kein zweiter direkt verknüpfter Payloadteil
belegt sind, darf der USB-Payload noch nicht als vollständiger RGB565-Frame
festgelegt werden. Möglich bleiben unter anderem Teilflächen, ein
descriptorabhängiger Stride, ein proprietäres Blocklayout oder ein anderes
16-Bit-nahes Datenobjekt.

Der Queueeintrag selbst enthält keine sichtbare Breite oder Höhe. Der
Konsument übergibt nur den Payloadzeiger; Breite, Höhe und gegebenenfalls
Stride liegen daher wahrscheinlich im separaten Descriptorzustand. Das ist
eine Ableitung, keine abgeschlossene Typisierung.

## 5. Rekonstruktion des Datei-/Objektpfads

Der Pfad aus `0x001279e8` ist nun als JPEG-Pfad belegt:

```text
Displaycallback 0x001279e8, Ereignis 0x15
  -> Objektquelle/Handle und Länge
  -> 0x0010f0d0
     -> Decoderobjekt über 0x0010e3c8
     -> JPEG-Headerparser 0x00110a58
     -> Breite/Höhe aus Objektfeldern +0x10/+0x12
  -> x = (320 - Breite) / 2
  -> y = (320 - Höhe) / 2
  -> 0x0010eff4
     -> 0x0011acd8
        -> JPEG-Zeilendekodierung und Farbumsetzung
        -> generische Zeichen-/Grafikfunktionen
        -> optional derselbe Grafikrouter 0x001065c4
```

`0x00110a58` prüft explizit die JPEG-SOI-Bytes `ff d8` und akzeptiert die
SOF-Marker `c0`, `c1` und `c2`. Breite und Höhe werden als Big-Endian-
16-Bit-Werte aus dem SOF-Segment gelesen und im Decoderobjekt bei `+0x10` und
`+0x12` gespeichert. `0x0010f0d0` gibt genau diese beiden Werte zurück.

`0x0010f16c` enthält JPEG-spezifische Block-/DCT-Verarbeitung und
Y/Cb/Cr-nahe Farbumsetzung in Ausgabezeilen. `0x0011acd8` zeichnet die
dekodierten Zeilen an den übergebenen Koordinaten. Der Defaultpfad
`c:\syst\wapper.jpg` passt damit zu einem tatsächlich belegten Decoder und
ist nicht mehr nur ein Dateinamenshinweis.

In diesem Datei-/Objektpfad wurden keine PNG- oder GIF-Erkennungen und keine
entsprechenden direkten Decoderaufrufe gefunden. Der USB-`0x08`-Großdatenpfad
ruft den JPEG-Parser nicht auf; er geht direkt zum Grafikrouter. JPEG ist
damit für gespeicherte Objekte bestätigt, aber nicht als Format der
Interface-1-Nutzlast.

Weder der USB-Großdatenpfad noch `0x0011acd8` ruft direkt die getrennten
LCM-Initialisierungsfunktionen `0x0010ccd0` oder die emWin-Initialisierung
`0x0010ee20` auf. Der Objektpfad verwendet jedoch den bereits initialisierten
generischen GUI-/Zeichenunterbau.

## 6. Zustandsbytes `+0x110` und `+0x111`

Beide Bytes liegen in der 0x114-Byte-Konfiguration bei `0x004e8348`.

### `+0x110`: Auswahl der Zeitumrechnung

- Befehl `0x1a` schreibt genau ein Byte.
- Abfrage `0x83` gibt genau dieses Byte zurück.
- Der Displaycallback `0x001279e8` behandelt nur null gegenüber ungleich
  null.

Bei freiem Anzeigezustand berechnet der Callback einen Vergleichs-/Zeitwert
aus einem dynamischen Wert bei `0x00130e04`:

```text
+0x110 == 0:  wert / 100
+0x110 != 0:  (wert * 18) / 1000 + 32
```

`0x0010d80c` ist die dabei verwendete Ganzzahldivision. Der Quellwert wird im
Callback `0x00127ce0` aktualisiert. Damit ist `+0x110` als binärer Selektor
für zwei Zeit-/Skalenberechnungen belegt. Die physikalische Einheit und eine
fachliche Benennung wie FPS, Dauer oder Geschwindigkeit bleiben offen.

### `+0x111`: Ablauf- und Wiederholungszustand

- Die Defaultinitialisierung setzt den Wert auf `1`.
- Befehl `0x1f` ersetzt ihn durch ein Payloadbyte und kann bei einem
  Nichtnullwert den Bootcallback registrieren.
- `0x001279e8`, `0x001268d0`, `0x00129b2c` und der Gerätedispatcher lesen den
  Wert.

Statisch sind folgende Klassen belegt:

| Wert | Beobachtetes Verhalten |
| ---: | --- |
| `0` | der normale zentrierte Objekt-/JPEG-Pfad in `0x001279e8` ist aktiv; der Bootpfad beendet sich nach dem letzten Eintrag |
| `1` | Default; der normale Objektcallback kehrt früh zurück; der Bootpfad setzt seinen Index nach dem letzten Eintrag wieder auf null |
| `2` | Sonder-/Übergangszustand; Zähler und Flags werden zurückgesetzt, der normale Objektpfad bleibt gesperrt und `0x001279e8` führt nach 51 Intervallen einen Reset-/Delay-Schritt aus; der Bootpfad beendet sich |
| andere Nichtnullwerte | der normale Objektcallback kehrt früh zurück; der Bootpfad wiederholt seine Eintragsfolge |

Damit steuert `+0x111` nachweisbar Auswahl, Wiederholung und Übergang zwischen
Anzeigeabläufen. Begriffe wie „Animation“, „Loop“, „Off“ oder „Bootmodus“
werden weiterhin nicht als Protokollsemantik festgelegt.

## 7. Konkretes hostseitiges Datenmodell

Ein Hostparser kann den Transport bereits belastbar so modellieren:

```text
Interface1Report:
  control_le32:
    command        = bits 0..7
    count_or_index = bits 8..30
    first          = bit 31
  payload[1020]

Interface1Transfer08:
  command = 0x08
  segment_count = first_report.count_or_index
  forwardable_segment_count = 1 .. 200
  reports = indices 0 .. segment_count-1
  queued_length = segment_count * 1020
  queued_payload = concatenation of every complete 1020-byte payload
  checksum = none observed
  final_valid_length = not separately encoded
```

Für die darüberliegende LCD-Struktur ist derzeit nur dieses vorsichtige Modell
vertretbar:

```text
LcdBulkObject:
  descriptor = firmwareseitiger, separat verwalteter Grafikdescriptor
  payload = Interface1Transfer08.queued_payload
  payload_class = direct 16-bit-class graphics input (well supported)
  pixel_order = unknown
  width/height/stride = descriptor-dependent, not present in queue entry
  full_frame = unconfirmed
```

Ein Hostencoder ist damit noch nicht sicher spezifizierbar. Insbesondere darf
er weder 320×320-RGB565 noch JPEG als Interface-1-Format voraussetzen.

## 8. Stärkster Kandidat für den nächsten sicheren Test

Der stärkste sichere nächste Test ist weiterhin vollständig passiv: eine
differenzielle Aufzeichnung eines einzelnen legitimen Herstellertransfers für
ein bekanntes statisches 320×320-Testbild, idealerweise mehrere Vollflächen
mit eindeutig getrennten Farben. Dabei sind Interface 0 und Interface 1
gemeinsam zeitlich zu erfassen.

Offline zu prüfen sind:

1. Segmentanzahl und lückenlose Indexfolge von Interface-1-`0x08`;
2. tatsächliches Padding im letzten 1020-Byte-Segment;
3. vorausgehender Interface-0-`0x08`-Descriptor und seine Beziehung zu Länge,
   Breite, Höhe und Stride;
4. 16-Bit-Periodizität und Byte-/Kanalordnung bei Vollflächen;
5. Vorhandensein oder Fehlen von JPEG-SOI `ff d8` im USB-Payload;
6. Teilfläche gegenüber Vollframe durch Vergleich mehrerer einfacher Bilder.

Ein aktiver `0x08`-Schreibtest ist noch nicht hinreichend spezifiziert: Der
Descriptor ist offen, 800 Byte Differenz zum 16-Bit-Vollframe sind ungeklärt,
und `+0x110/+0x111` besitzen zustandsändernde Wirkung. Erst ein vollständig
beobachteter, bytegenau dokumentierter Referenztransfer könnte Grundlage für
einen späteren, erneut ausdrücklich freizugebenden Einzeltest sein.

## 9. Weiter ausgeschlossene Pfade

SPI-, Flash-, Updater- und persistente Objektpfade wurden nicht praktisch
untersucht oder ausgeführt. Insbesondere bleiben `0x88`, `0x0a..0x0d`,
`0x1b`, `0x1c`, `0xfe`, Updater-`0x02`, `0x45`, `0x86` und der indirekte
`0xff`-Callback von jeder Gerätekommunikation ausgeschlossen.

## Offene Punkte

- genaue Struktur und Initialisierung des Grafikdescriptors hinter
  `0x001314d0`;
- Bedeutung der akzeptierten Moduswerte um `0x6021` und `0x14021`;
- konkrete 16-Bit-Kanal- und Byteordnung;
- Breite, Höhe und Stride des Interface-1-Payloads;
- Ursache der 800-Byte-Differenz zwischen maximalem Payload und
  320×320×16 Bit;
- Semantik der 16-Byte-IN-Schnittstelle `0x84`;
- Einheiten der beiden durch `+0x110` gewählten Zeitumrechnungen;
- fachliche Benennung der durch `+0x111` ausgewählten Ablaufzustände.
