# Statische Rekonstruktion des LCD-Datenpfads 02

Stand: 2026-09-02

## Zweck und Sicherheitsrahmen

Diese Fortsetzung typisiert den Interface-1-Pfad bis zu einem möglichst
vollständigen Host-Paketmodell. Untersucht wurden ausschließlich die bereits
extrahierte v51-Firmware und das bestehende Ghidra-Projekt. Das Projekt wurde
mit `-readOnly -noanalysis` geöffnet. Es gab keine Gerätekommunikation, keine
aktiven `0x08`-Tests, keine Emulation und keine Zugriffe auf SPI-, Flash- oder
andere persistente Pfade.

Der neue Export
`research/ghidra-scripts/ExportLcdPacketModel.java` sammelt die relevanten
Instruktionen, Dekompilate, Callgraph-Kanten, Konstanten-Xrefs,
Hardware-Register-Xrefs und Byte-Swap-Kandidaten. Ein reproduzierbarer Aufruf
ist:

```text
analysis_tmp=$(mktemp -d /tmp/tuf-aio-lcd02.XXXXXX)
env XDG_CONFIG_HOME="$analysis_tmp/config" \
  /home/l/HeartdriveLAB/shared/tools/ghidra/ghidra_12.1_PUBLIC/support/analyzeHeadless \
  research/ghidra-projects device-firmware-v51-ghidra12-1 \
  -process device-firmware-v51.bin -readOnly -noanalysis \
  -scriptPath research/ghidra-scripts \
  -postScript ExportLcdPacketModel.java \
  "$analysis_tmp/lcd-packet-model.txt"
```

Ghidra meldet beim Dekompilieren von `0x0010df9c` weiterhin ungültige Daten
am direkt folgenden Literalpool. Die für diesen Callback exportierte
Instruktionsfolge ist vollständig; die betroffenen Literalwerte werden durch
die übrigen Xrefs und die manuell geprüften Rohbytes bestätigt.

## Kurzfassung

1. `0x001314d0` ist kein Grafikdescriptor. Es ist ein BSS-Feld, das auf den
   aktuellen Knoten eines Framebuffer-Rings zeigt. Der Folgeknoten liefert bei
   `+4` die Ziel-Framebuffer-Adresse. Geometrie, Stride, Pixelformat und
   Callback liegen nicht in diesem Knoten.
2. Der Knoten ist mindestens `0x10` Byte groß: `+0` Folgeknoten, `+4`
   Framebufferbasis, `+8` im untersuchten Pfad unbekannt, `+0x0c`
   Frei-/Bereitzustand. Eine Konstruktorstelle, die eine exakt größere oder
   exakt `0x10` Byte große Allokation beweist, wurde nicht gefunden.
3. Die getrennte emWin-MEMDEV-Struktur ist dagegen vollständig typisiert:
   `0x18` Byte Header, 320×320, 16 bpp, Stride 640, danach `0x32000` Pixelbyte.
4. Das Interface-1-Steuerwort besitzt genau Befehl, ein 23-Bit-Feld und das
   Erstsegmentbit. Es enthält keine Länge, Endmarke oder weiteren Flags.
5. `200` ist zunächst eine Kopiergrenze für Segmentindizes, nicht die
   Feldbreite der Gesamtzahl. Wegen der Queuekapazität ist 200 zugleich die
   größte Gesamtzahl, die erfolgreich weitergereicht werden kann.
6. Die 800 Byte sind nach dem statischen Befund keine versteckte
   Schlusssegmentlücke: USB-Quellobjekt und 320×320-Zielframebuffer sind
   getrennte Objekte. Der `0x6021`-Pfad ist ein 16-Bit-Ausgabepfad des
   Grafik-/Decoderblocks. Dass die USB-Nutzlast selbst ein kompletter
   Rohframe sei, ist widerlegt; das genaue akzeptierte Quellformat bleibt
   offen.
7. Interface 1 IN sendet vor dem eigentlichen Grafikstart einmal 16 Byte.
   Frisch geschrieben werden nur die konstanten Bytes `08 81`. Das ist keine
   Abschlussantwort und enthält keine Segmentnummer, Sequenznummer oder
   Fehlerangabe.

## 1. Was tatsächlich hinter `0x001314d0` liegt

### 1.1 Korrektur des bisherigen Modells

`0x001314d0` liegt im BSS und ist `0x001314c4 + 0x0c`. Die umgebende
Boot-/Displaystruktur wird von `0x001268d0` so benutzt:

| Offset ab `0x001314c4` | Belegte Rolle |
| ---: | --- |
| `+0x00` | Anzahl gültiger geladener Objekt-/Bootrecords |
| `+0x04` | aktueller Recordindex |
| `+0x08` | Zeiger auf ein dynamisches Array von 16-Byte-Records |
| `+0x0c` | Zeiger auf den aktuellen Framebuffer-Ringknoten; absolute Adresse `0x001314d0` |

Damit ist die Formulierung „Grafikdescriptor bei `0x001314d0`“ zu stark.
Das Feld enthält nur die Ringposition. `0x00129b2c` liest zuerst den aktuellen
Knoten und dann dessen Folgeknoten; der Folgeknoten wird zum Ziel des nächsten
Grafikvorgangs.

### 1.2 Statisch belegte Ringknotenstruktur

Aus `0x00129b2c`, `0x00129cf0` und `0x001268d0` ergibt sich:

```c
struct lcd_fb_ring_node {
    struct lcd_fb_ring_node *next;  // +0x00, bestätigt
    uint32_t framebuffer_base;      // +0x04, bestätigt
    uint32_t unknown_08;            // +0x08, nicht typisiert
    int32_t  ready_state;           // +0x0c, bestätigt
};
```

Die statisch bestätigte Mindestgröße beträgt `0x10` Byte. Alle beobachteten
Zugriffe enden bei `+0x0c`, und der Objektgebrauch ist mit einer
`0x10`-Byte-Struktur konsistent. Da die Erzeugung beziehungsweise Allokation
dieser Ringknoten nicht im untersuchten Imagepfad gefunden wurde, ist
„exakt `0x10` Byte und ohne nachfolgende Privatfelder“ nicht bewiesen.

Die Felder haben folgende belegte Semantik:

- `+0x00`: `0x00129b2c` und `0x00129cf0` dereferenzieren es als nächsten
  Ringknoten. Die Verkettung ist bestätigt; die exakte Knotenzahl ist offen.
- `+0x04`: wird als Adresse an Grafikrouter-Operation `0` und an
  `0x00109394` übergeben. `0x00109394` schreibt denselben Wert in das
  Displaycontrollerregister `0xb1002050`. Das Feld ist daher die
  Framebufferbasis, kein Zeiger auf einen weiteren Softwaredescriptor.
- `+0x08`: kein Zugriff im rekonstruierten Bulk-, Boot- oder
  Displaywechselpfad. Eine Benennung wäre Spekulation.
- `+0x0c`: `0` bedeutet für den Produzenten „frei“. Ein positiver
  Laderückgabewert markiert geladene Daten, und `-1` markiert einen durch den
  Grafikpfad fertig beschriebenen Puffer. Der Displaywechselcallback
  akzeptiert jeden Nichtnullwert als bereit und setzt den bisher sichtbaren
  Knoten anschließend auf `0` zurück.

### 1.3 Ringwechsel und Callbacks

Beim Bootereignis `3` registriert `0x001268d0` die Funktion `0x00129cf0` in
`0x0013151c`. `0x00129cf0` führt atomar aus:

```text
current = *(0x001314d0)
next = current->next
current->ready_state = 0
if next->ready_state != 0:
    *(0x001314d0) = next
    set_display_framebuffer(next->framebuffer_base | 0x80000000)
```

Der Bulkpfad installiert getrennt davon `0x00115110` als
Grafik-Completion-Callback. Diese Funktion besteht nur aus `bx lr`; der
eigentliche Abschluss wird in `0x00129b2c` durch Abfrage von `0x00105e60`
festgestellt. Weder Callback liegt im Ringknoten.

### 1.4 Bufferpointer und Konstanten

- `0x00331b40` wird während der Anzeigeinitialisierung explizit als
  Display-Framebufferbasis gesetzt.
- `node->framebuffer_base` ist dynamisch und wird beim Ringwechsel ebenfalls
  direkt an den Displaycontroller geschrieben.
- Queue `0x003bb430` mit Backing-Buffer `0x003edb40` ist die getrennte
  Grafikquelle des Interface-1-Pfads.
- Das Bit `0x80000000` wird von der Firmware auf Quell- und Zieladressen
  gesetzt. Es ist ein internes Bus-/Adressattribut und kein Hostdatenbit.
- `0x6021` ist der für `0x08` fest eingestellte Grafikmodus.
- `0x32000` ist sowohl die Größe eines 320×320×16-Bit-Pixelbereichs als auch
  die gewählte Kapazität des getrennten Interface-1-Queuebuffers. Die beiden
  Speicherobjekte sind nicht identisch.

Breite, Höhe, Stride, Farbumsetzung oder Funktionspointer sind im Ringknoten
nicht vorhanden.

## 2. Getrennte, vollständig typisierbare Grafikstruktur

Die Anzeigeinitialisierung `0x00127e9c` erzeugt über
`0x00110f74 -> 0x00111754` ein emWin-Memory-Device mit den Argumenten
`x=0`, `y=0`, `width=0x140`, `height=0x140`, Flag `1`, Gerätetabelle
`0x001307e0` und Farbumsetzungstabelle `0x0012ec20`. Das zurückgegebene Handle
wird in `0x001315b4` gespeichert.

Nach dem Lock/Dereferenzieren besitzt das MEMDEV-Datenobjekt diesen
bestätigten Header:

| Offset | Größe | Feld | Wert bei der LCD-Initialisierung |
| ---: | ---: | --- | ---: |
| `+0x00` | 4 | emWin-Gerätezeiger | dynamisch |
| `+0x04` | 2 | `x0` | `0` |
| `+0x06` | 2 | `y0` | `0` |
| `+0x08` | 2 | Breite | `320` |
| `+0x0a` | 2 | Höhe | `320` |
| `+0x0c` | 4 | Stride in Byte | `640` (`0x280`) |
| `+0x10` | 4 | Bits pro Pixel | `16` |
| `+0x14` | 4 | Hilfshandle/-zeiger | hier `0` |
| `+0x18` | variabel | Pixelbereich | `320 * 640 = 0x32000` Byte |

Der Konstruktor berechnet den Stride allgemein als
`(width * bits_per_pixel + 7) >> 3` und die Allokationsgröße als
`height * stride + 0x18`. Für dieses Objekt sind das exakt `0x32018` Byte.

Diese Struktur liefert den statischen Beleg für native Geometrie und
16-Bit-Stride, ist aber nicht das Objekt bei `0x001314d0` und wird nicht mit
der Interface-1-Nutzlast übertragen.

## 3. Grafikmodus `0x6021` und Pixelpfad

### 3.1 Wirkung des Modus

`0x00106058` akzeptiert eine kleine Modusfamilie und schreibt `0x6021` sowohl
in den internen Grafikzustand als auch nach `0xb100a008`. Im
Transfer-State-Builder `0x00105a10` gilt für `0x6021`:

```text
Ausgabebyte = Breite * Höhe * 2
```

Nur `0x14021` verwendet in diesem Zweig vier Byte pro Pixel. Der unabhängige
JPEG-/Objektrenderer `0x0011acd8` wählt ebenfalls `0x6021` für seine
16-Bit-Ausgabe und `0x14021` für 32 Bit. Damit ist `0x6021` als
16-Bit-Ausgabepfad bestätigt.

Grafikrouter-Operation `0` schreibt die Zielbasis nach `b100a07c`, Operation
`4` die Quellbasis nach `b100a0a0`, und Operation `0x0c` startet den Vorgang.
Für USB-`0x08` ist das Ziel `current->next->framebuffer_base`, die Quelle der
Queuepayload.

### 3.2 Herkunft der Dimensionen

`0x001059f4` liest beide 16-Bit-Dimensionen aus Register `b100a028`. Die
statische Xref-Suche findet im Firmwareimage keinen Softwarewrite auf dieses
Register. Im direkten Interface-1-Pfad werden auch die Routeroperationen
`0x0e`/`0x0f`, mit denen andere Aufrufer Dimensionen vorgeben, nicht benutzt.

Die Dimensionen kommen deshalb im Bulkpfad weder aus dem Ringknoten noch aus
separaten Feldern des USB-Steuerworts. Sie entstehen aus dem Zustand des
Grafik-/Decoderblocks beziehungsweise aus der von ihm interpretierten Quelle.
Im JPEG-Beschleunigungspfad verwendet derselbe Block einen kodierten
Quellbuffer und erzeugt ein 16- oder 32-Bit-Zielbild. Das ist ein starker
Beleg dafür, USB-`0x08` als Grafik-Quellobjekt und nicht als zwingend rohen
Framebuffer zu modellieren. Eine explizite JPEG-SOI-Prüfung findet im
USB-Pfad selbst jedoch nicht statt; „USB-`0x08` ist JPEG“ bleibt daher noch
nicht bestätigt.

### 3.3 5/6/5-Belegung

Die am MEMDEV installierte Farbtabelle `0x0012ec20` besteht aus:

- `0x00119ee0`: logische Farbe nach 16-Bit-Index;
- `0x00115db4`: 16-Bit-Index nach logischer Farbe;
- `0x00122ce4`: Indexmaske `0xffff`.

Die Vorwärtsumsetzung ist binär eindeutig:

```text
index[ 4: 0] = LUT5(logical_color[ 7: 0])
index[10: 5] = LUT6(logical_color[15: 8])
index[15:11] = LUT5(logical_color[23:16])
```

Die Rückumsetzung liest exakt dieselben Bereiche `0x001f`, `0x07e0` und
`0xf800` logisch zurück, auch wenn `0x07e0` nicht als einzelner ARM-Immediate
im Code materialisiert wird. Bei der von diesem Image verwendeten älteren
emWin-ABGR-Konvention ist das:

```text
bits  0..4   R5
bits  5..10  G6
bits 11..15  B5
```

Als numerisches Wort ist das `BGR565`. Im ARM-Little-Endian-Speicher steht
das niederwertige Byte zuerst. Die offizielle emWin-Dokumentation nennt für
`GUICC_565` ausdrücklich die Maske `BBBBBGGGGGGRRRRR` und beschreibt außerdem
ABGR sowie den Wechsel neuerer Versionen zu ARGB:
<https://www.segger.com/downloads/emwin/UM03001>. Die Firmwarefunktion selbst
liefert zusätzlich Alpha `0xff` im höchsten Byte und belegt damit die hier
verwendete ABGR-Variante.

Der vollständige Instruktionsscan findet im Image kein `REV`, `REV16`,
`REVSH` und kein `ROR #8`. Die beiden Farbumsetzer enthalten auch keine
manuelle Zwei-Byte-Tauschschleife. Für das native MEMDEV ist daher
`BGR565` als Little-Endian-Wort bestätigt, ohne zusätzlichen Byte-Swap.

Noch nicht vollständig bestätigt ist, ob der Hardwaremodus `0x6021` seine
16-Bit-Ausgabe garantiert in genau derselben Kanalordnung liefert oder ob
der Displaycontroller eine Kanalumschaltung vornimmt. Da sein Ziel unmittelbar
als emWin-/Display-Framebuffer verwendet wird, ist dieselbe Belegung sehr
wahrscheinlich, aber für einen Hostencoder soll diese letzte Gleichsetzung
noch als offene Hardwareformatfrage markiert bleiben.

## 4. Exakte Interface-1-Segmentstruktur

### 4.1 Drahtformat

Jeder OUT-Report auf Endpoint `0x03` ist exakt 1024 Byte lang:

```text
Offset  Größe  Bedeutung
0x000   1      Befehl
0x001   1      Bits 0..7 des 23-Bit-Felds
0x002   1      Bits 8..15 des 23-Bit-Felds
0x003   1      Bits 16..22 des Felds; Bit 7 = Erstsegment
0x004   1020   Nutzdatenblock
```

Als Little-Endian-Wort:

```text
bits  0..7   command
bits  8..30  count_or_index
bit      31  first
```

Es gibt in den vier Controlbytes keine weiteren Bits für Nutzlänge,
Endsegment, Fehlerkontrolle, Padding oder Prüfsumme.

### 4.2 Zustandsstruktur von `0x001297e8`

Der Assemblierungszustand bei `0x003bb480` ist:

| Offset | Feld |
| ---: | --- |
| `+0x00` | Flags; Bit 0 wird bei festgestelltem Abschluss gesetzt |
| `+0x04` | erwartete Gesamtzahl `N` aus dem Erstsegment |
| `+0x08` | zuletzt akzeptierter Index |
| `+0x0c` | aktueller Befehl |
| `+0x10` | Beginn des Assemblierungsbuffers |

Das Erstsegment wird immer als logischer Index `0` behandelt, unabhängig vom
Wert im 23-Bit-Feld. Dieser Wert wird beim Erstsegment als Gesamtzahl `N`
gespeichert. Der komplette 1020-Byte-Block wird nach `state + 0x10` kopiert.

Bei einem Folgesegment ist das 23-Bit-Feld der Index. Akzeptiert werden nur:

```text
index == last_index          // Duplikat, überschreibt denselben Block
oder
index == last_index + 1      // nächster Block
```

Ein Sprung, ein älterer Index außer dem unmittelbaren Duplikat oder eine
andere Reihenfolge wird still ignoriert. Bei einem anderen Befehl wird die
Meldung `receiving data error` ausgegeben und der gespeicherte Befehl auf null
gesetzt.

Nur für `index < 200` erfolgt die Kopie an:

```text
state + 0x10 + index * 1020
```

Ein sequenzieller Index ab 200 wird nicht kopiert, aber trotzdem als
`last_index` gespeichert. Der Abschlussvergleich wird anschließend immer
ausgeführt:

```text
complete = (N <= last_index + 1)
```

Damit ist für einen normalen Transfer `N` tatsächlich die Gesamtzahl und die
Folge lautet `0..N-1`. Eine gesonderte Endmarkierung existiert nicht.

### 4.3 200: Feldgrenze, Kopiergrenze und effektive Gesamtgrenze

Die Zahl 200 ist nicht die Feldgrenze: Das Controlfeld ist 23 Bit breit, und
das Erstsegment validiert `N` nicht gegen 200. `200` ist im Empfänger
unmittelbar die exklusive Kopiergrenze für Folgeindizes.

Für die erfolgreiche Weitergabe ist 200 dennoch die effektive maximale
Gesamtzahl:

- `N = 200`: Indizes `0..199`, alle Blöcke werden kopiert; Länge 204000 Byte.
- `N = 201`: Index 200 kann den Abschluss auslösen, wird aber nicht kopiert;
  die anschließend angeforderte Queuepayload von 205020 Byte passt nicht in
  `0x32000` Byte.
- Größere `N` können den Empfänger nach genügend sequenziellen, nicht mehr
  kopierten Indizes formal abschließen, scheitern aber ebenfalls an der
  Queueallokation.
- `N = 0` erzeugt keine nutzbare Queuepayload.

Für ein Hostmodell gilt deshalb `1 <= N <= 200`, obwohl die Drahtfeldbreite
größere Zahlen darstellen kann.

### 4.4 Queueübergabe und Fehlerfälle

Nach einem vollständigen Befehl `0x08` berechnet `0x0010df9c` ausschließlich:

```text
payload_length = N * 1020
```

Es reserviert diese Länge in Queue `0x003bb430` und kopiert bei erfolgreicher
Allokation genau so viele Bytes aus dem Assembler. Der Queueeintrag selbst ist:

```text
uint32_le payload_length   // Queue-intern
uint8_t payload[payload_length]
padding auf vier Byte      // Queue-intern
```

`0x00129b2c` erhält von `0x0012a390` den Payloadzeiger und die Länge. Es prüft
die Länge nur auf ungleich null und verwirft sie danach. An Grafikrouter-
Operation `4` geht `entry + 4`, also weder das Queue-Längenwort noch das
USB-Controlwort.

Weitere Fehlersemantik:

- Ein nicht passender Befehl setzt den Assemblierungsbefehl auf null; es wird
  keine Interface-1-Fehlerantwort erzeugt.
- Eine ungültige Segmentreihenfolge wird still verworfen.
- Ein Queueallokationsfehler verwirft den vollständigen Transfer; es gibt
  keinen Retry und keine Fehlerantwort.
- Der Queueeintrag bleibt während des Grafikvorgangs belegt und wird erst
  nach Abschluss oder Abbruch freigegeben.

## 5. Die 800-Byte-Differenz

Die Gleichungen sind korrekt, aber allein keine Protokollerklärung:

```text
200 * 1020       = 204000
0x32000          = 204800
Differenz        =    800
320 * 320 * 2    = 204800
```

Die geforderten Alternativen lassen sich statisch wie folgt entscheiden:

| Hypothese | Statischer Befund |
| --- | --- |
| 200 ist nur ein Index-/Zählergrenzwert | Teilweise ja: Es ist die exklusive Kopiergrenze, nicht die 23-Bit-Feldgrenze. Durch die Queuekapazität wird es zugleich zur effektiven maximalen weiterleitbaren Gesamtzahl. |
| Zusätzliches Abschlusssegment | Nein. Abschluss entsteht nur aus `N <= last+1`; Index 200 wird nicht kopiert und `N=201` passt nicht in die Queue. |
| Separate Nutzlänge | Nein. Für `0x08` wird nur `N*1020` verwendet. Die Callbackkonstante `0x400` ist Reportgröße, keine tatsächliche Restlänge. |
| Padding wird entfernt oder ergänzt | Nein. Jeder Block wird exakt mit 1020 Byte kopiert. Queuealignment ist außerhalb der Payload und ändert sie nicht. |
| `0x32000` ist Framebuffer- statt USB-Transfergröße | Ja, als native 320×320×16-Bit-Pixelgröße; gleichzeitig ist es ausweislich `0x001293f8` die Kapazität des getrennten Queue-Backing-Buffers. Es ist nicht die maximal erzeugte USB-Payloadlänge. |
| Metadaten liegen außerhalb der 1020 Byte | Ja: vier Byte USB-Controlwort und vier Byte Queue-Längenwort liegen außerhalb. Keines davon wird an den Grafikblock als Quelldaten übergeben, und zusammen erklären sie die 800 Byte nicht. |

Damit ist ausgeschlossen, dass ein zusätzlicher 800-Byte-Restblock, eine
letzte Nutzlänge oder verborgenes Queuepadding einen rohen 204800-Byte-Frame
vervollständigt. Auch ein maximaler Queueeintrag belegt einschließlich
Längenwort nur 204004 Byte und lässt 796 Byte Queuekapazität frei.

Der belastbarste aktuelle Stand ist stattdessen:

- `0x32000` beschreibt die Zielbild-/Framebufferklasse und die gewählte
  Transport-Queuekapazität.
- Die maximal 204000 Byte sind ein getrenntes Grafik-Quellobjekt.
- Der `0x6021`-Block erzeugt daraus eine 16-Bit-Ausgabe, deren Bytezahl aus
  Breite und Höhe stammt; die logische Queuepayloadlänge wird nicht als
  Ausgabelänge benutzt.
- Derselbe Grafikblock verarbeitet im Objektpfad kodierte JPEG-Quellen.

Die Differenz muss daher nicht durch Hostpadding auf 204800 Byte geschlossen
werden. Vielmehr ist ein kompletter roher 320×320-BGR565-USB-Frame mit diesem
Segmentpfad nicht darstellbar und als Modell zu verwerfen. Offen bleibt, ob
die Quelle für USB-`0x08` JPEG, ein hardwareeigenes kodiertes Format oder ein
anderes längenautonomes Grafikobjekt ist.

## 6. Interface 1 IN / Endpoint `0x84`

### 6.1 Erzeugungszeitpunkt und Inhalt

`0x00129b2c` sendet genau dann eine Interface-1-IN-Nachricht, wenn:

1. ein vollständiger Queueeintrag vorhanden ist;
2. der nächste Framebuffer-Ringknoten frei ist;
3. noch kein Grafikvorgang aktiv ist.

Unmittelbar danach, aber noch vor Grafikreset, Moduswahl und Operation
`0x0c`, ruft es auf:

```text
send_ep84(0x0012eba0, 2)
```

Die ROMbytes bei `0x0012eba0` beginnen mit:

```text
08 81 00 00 cd ab 34 12 ...
```

`0x0011508c` kopiert davon nur zwei Byte in den dedizierten BSS-Puffer
`0x003ed340`, wählt den USB-Selektor `0x14` und armiert fest 16 Byte. Somit
sind nur diese beiden Bytes semantisch frisch gesetzt:

```text
Offset  Wert  Befund
0       0x08  Befehl 0x08
1       0x81  konstanter Status-/Ereigniswert
2..15   -     vom Sender nicht neu geschrieben; dedizierter BSS-Puffer ist initial null
```

Die Nachricht wird einmal pro aus der Queue gestarteter Grafikoperation
erzeugt, nicht einmal pro Segment.

### 6.2 Semantik und Completion-Callback

Wegen des Zeitpunkts ist `08 81` keine Grafikabschlussmeldung. Sie besagt
mindestens, dass der vollständig assemblierte Queueeintrag einen freien
Zielpuffer erreicht hat und nun gestartet werden soll. „accepted/start
notification“ ist daher die engste belegte Beschreibung; ob `0x81` intern
formal „ACK“, „busy“ oder „started“ heißt, ist nicht benannt.

Die Nachricht enthält keine Segmentnummer, Gesamtzahl, Queueposition,
Nutzlänge oder Fehlerkennung. Falls der Grafikvorgang später fehlschlägt, ist
kein weiterer Interface-1-IN-Fehlerpfad belegt.

Der Endpoint-`0x84`-Completion-Callback `0x0010e0a8` schreibt lediglich null
nach `0x00131320` (`0x00131314 + 0x0c`) und erzeugt selbst keine Daten. Im
Image wurde kein direkter Write gefunden, der dieses Feld im Bulkpfad auf
eins setzt; die genaue Besitzsemantik dieses Busy-Felds im USB-Unterbau bleibt
offen. Es gibt keine Daten- oder Callgraph-Verbindung von diesem Callback zur
Segmentqueue oder zur Grafikabschlussabfrage.

Die Reihenfolge in `0x00129b2c` ist eindeutig:

```text
Queueeintrag und freier Zielknoten
  -> EP 0x84: 16 Byte, Präfix 08 81
  -> Grafikzustand zurücksetzen
  -> mode 0x6021
  -> Ziel = next->framebuffer_base
  -> Completion-Callback 0x00115110
  -> Quelle = Queuepayload
  -> Operation 0x0c starten
```

## 7. Host-seitiges Paketmodell

Soweit statisch bestätigt, kann ein Host einen `0x08`-Quellbuffer so
segmentieren:

```text
N = Anzahl vollständig zu sendender 1020-Byte-Blöcke, 1..200

Segment 0:
  control = 0x80000000 | (N << 8) | 0x08
  data    = source[0:1020]

Segment i, 1 <= i < N:
  control = (i << 8) | 0x08
  data    = source[i*1020:(i+1)*1020]

Report = little_endian_u32(control) || data
```

Jeder Report muss 1024 Byte besitzen. Weil keine Restlänge übertragen wird,
ist ein unvollständiger letzter Block nicht darstellbar: Alle Füllbytes sind
aus Firmwaresicht Teil des Quellobjekts. Ein Hostencoder darf daher die letzte
Payload nicht blind aufrunden, solange die Grammatik und erlaubte Terminierung
des Grafikquellformats nicht bekannt sind.

Die 16-Byte-IN-Nachricht mit Präfix `08 81` kann erst nach vollständiger
Assembly und späterer Queueentnahme eintreffen. Sie ist als Startannahme, nicht
als per-Segment-ACK und nicht als Darstellungserfolg zu behandeln. Bytes
`2..15` sollen nicht ausgewertet werden.

## 8. Verbleibende Lücken für einen sicheren Hostencoder

Vor einer Implementierung, die reale Bilddaten sendet, fehlen weiterhin:

1. die exakte Grammatik der Grafikquelle für `0x6021` im USB-`0x08`-Pfad;
2. ein statischer oder passiver Beleg, ob diese Quelle JPEG ist und welche
   Header-, EOI- und Paddingregeln gelten;
3. die Bedeutung des konstanten Statusbytes `0x81` als offizieller
   Protokollzustand;
4. die garantierte Kanalordnung der Hardwareausgabe von `0x6021`, obwohl das
   native emWin-Ziel als Little-Endian-BGR565 belegt ist;
5. die exakte Ringknotengröße über die belegten ersten `0x10` Byte hinaus,
   die Bedeutung von `+0x08` und die Anzahl der Framebuffer-Ringknoten;
6. Fehler- und Timeoutregeln des Hosts, da die Firmware weder Segmentfehler
   noch einen späteren Grafikfehler über Endpoint `0x84` meldet;
7. eine zulässige letzte Blockfüllung. Ohne Quellformatkenntnis ist
   Zero-Padding nicht als sicher oder korrekt belegt.

Diese Lücken erfordern keinen aktiven Gerätetest als nächsten Schritt. Ein
passiver Mitschnitt eines legitimen Herstellertransfers oder weitere
statische Typisierung des Hardware-Decoders könnte Quellformat,
Terminierungsregel und die Bedeutung von `0x81` schließen.
