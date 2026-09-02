# Statische Rekonstruktion des LCD-JPEG-Transports 03

Stand: 2026-09-02

## Zweck und Sicherheitsrahmen

Diese Analyse rekonstruiert den Host-zu-LCD-Pfad des Interface-1-Befehls
`0x08` byte- und bitgenau. Untersucht wurden ausschließlich die bereits
extrahierte v51-Firmware, das bestehende Ghidra-Projekt und vorhandene
Projektartefakte. Das Ghidra-Projekt wurde mit `-readOnly -noanalysis`
geöffnet. Es gab keine Gerätekommunikation, keine HID-Schreiboperation, keine
Emulation, keine Freigabe zusätzlicher Schreibrechte und keinen Zugriff auf
SPI-, Flash- oder Persistenzfunktionen.

Der reproduzierbare Export liegt in
`research/ghidra-scripts/ExportLcdTransportLifecycle.java`. Beispielaufruf:

```text
analysis_tmp=$(mktemp -d /tmp/tuf-aio-lcd03.XXXXXX)
env XDG_CONFIG_HOME="$analysis_tmp/config" \
  /home/l/HeartdriveLAB/shared/tools/ghidra/ghidra_12.1_PUBLIC/support/analyzeHeadless \
  research/ghidra-projects device-firmware-v51-ghidra12-1 \
  -process device-firmware-v51.bin -readOnly -noanalysis \
  -scriptPath research/ghidra-scripts \
  -postScript ExportLcdTransportLifecycle.java \
  "$analysis_tmp/lcd-transport-lifecycle.txt"
```

## Ergebnis in Kürze

1. Das Controlword ist exakt ein Little-Endian-DWORD mit Befehl in Bits 0..7,
   einem 23-Bit-Feld in Bits 8..30 und dem Erstsegmentbit in Bit 31. Beim
   Erstsegment bedeutet das Feld Gesamtsegmentzahl `N`, danach Segmentindex.
2. Der normale, sichere Hostbereich ist `1 <= N <= 200`. Das ist keine
   Feldgrenze und auch keine vollständige Aussage über alle fehlerhaften
   Firmwarezustände. Das Feld kann `0..0x7fffff` darstellen; ein 32-Bit-
   Überlauf in `N * 1020` eröffnet einen extremen, nicht legitimen Randfall.
3. Jeder USB-Report enthält immer 1020 Nutzbytes. Die Firmware entfernt kein
   Schlussblockpadding und bewahrt die ursprüngliche JPEG-Länge im USB-Pfad
   nicht auf. Der Queueeintrag hat ausschließlich die Länge `N * 1020`.
4. `[0x00131940]` ist die exakte Länge eines getrennten gespeicherten
   JPEG-Objekts. Sie wird in `0x0010eff4` aus dessen Record-Länge gesetzt und
   gehört nicht zum USB-`0x08`-Pfad.
5. Der USB-Pfad besitzt vor Decoderstart weder eine Software-JPEG-Prüfung noch
   einen separaten Accelerator-Kopierbuffer. Der Queuepayload wird direkt als
   Hardwarequelle gesetzt.
6. `08 81` wird nach erfolgreichem Queue-Peek, aber vor Grafikreset und
   Decoderstart gesendet. Es ist eine Annahme-/Startnachricht, keine Ready-,
   Done- oder Fehlerbestätigung. Der Queueeintrag bleibt bis zum späteren
   Release belegt.
7. Ein eigener Live-Test ist noch nicht exakt und hinreichend sicher
   spezifizierbar. Hauptblocker sind der unbekannte erlaubte Schlussblocksuffix,
   das Fehlen einer Done-/Fehlermeldung und die Differenz zwischen analysierter
   v51-Firmware und dem real bestätigten Gerät mit Versionswert `0x0049`.

## 1. Exaktes Vier-Byte-Controlword

### 1.1 Drahtformat

`0x001297e8` lädt das erste DWORD des 1024-Byte-Reports direkt. Auf der
Little-Endian-ARM-Firmware gilt:

```text
Byteoffset  Bits im DWORD  Bedeutung
0           0..7          command
1           8..15         count_or_index Bits 0..7
2           16..23        count_or_index Bits 8..15
3           24..30        count_or_index Bits 16..22
3, Bit 7    31            first
```

Äquivalent:

```text
control = command
        | (count_or_index << 8)
        | (first ? 0x80000000 : 0)
```

Das Feld `count_or_index` ist exakt 23 Bit breit und hat den darstellbaren
Bereich `0..0x7fffff`. `command` hat den Bereich `0..0xff`. Im LCD-Pfad muss
`command == 0x08` sein. Bit 31 bedeutet ausschließlich „dieser Report beginnt
beziehungsweise ersetzt eine Assemblierung“. Es ist weder Endsegment-,
Gültigkeits- noch Persistenzbit.

### 1.2 Assemblierungszustand

Der Zustand ab `0x003bb480` ist direkt belegt:

| Offset | Bedeutung |
| ---: | --- |
| `+0x00` | Flags; Bit 0 wird bei `complete` gesetzt, in diesem Pfad aber nicht zur Entscheidung gelesen |
| `+0x04` | erwartete Gesamtsegmentzahl `N` |
| `+0x08` | zuletzt akzeptierter Index `last_index` |
| `+0x0c` | gespeicherter Befehl |
| `+0x10` | Assemblierungsdaten, Block 0 |

Die Callbackfunktion `0x0010df9c` ist der einzige statisch belegte Aufrufer
von `0x001297e8`. Sie reicht den 1024-Byte-Interface-1-OUT-Puffer weiter. Der
Empfänger ignoriert einen möglichen Längenparameter und kopiert stets fest
`0x3fc = 1020` Byte.

### 1.3 Erstsegment-Regeln

Für `first == 1` führt `0x001297e8` ohne Prüfung eines laufenden Transfers aus:

```text
stored_command = command
last_index     = 0
N              = count_or_index
copy(report[4:1024], assembler_block[0], 1020)
complete       = (N <= 1)
```

Bestätigte Konsequenzen:

- Das Erstsegment ist logisch immer Index `0`; sein 23-Bit-Feld ist `N`, nicht
  der Index.
- Ein neues Erstsegment verwirft beziehungsweise ersetzt den vorherigen
  Teilzustand ohne Fehlermeldung.
- Der Datenbereich hinter Block 0 wird dabei nicht gelöscht.
- `N=1` ergibt einen normalen Einsegmenttransfer.
- `N=0` liefert formal sofort `complete`, aber `0x0010df9c` berechnet Länge
  null und die Queueallokation `0x0012a3f0` lehnt Länge null ab. Es entsteht
  kein Queueeintrag.
- Es gibt weder Transfer-ID noch CRC, Nutzlänge, Endmarkierung oder Timeout.

### 1.4 Folge-Segment-Regeln

Für `first == 0` wird zuerst der Befehl verglichen. Nur bei
`command == stored_command` kommt die Indexprüfung:

```text
accepted = (index == last_index) or (index == last_index + 1)
```

Bei einem akzeptierten Folgepaket gilt:

```text
if index < 200:
    copy(report[4:1024], assembler_block[index], 1020)
last_index = index
complete = (N <= last_index + 1)
```

Die normale Hostfolge ist deshalb `1, 2, ..., N-1`. Index `0` ohne gesetztes
Erstsegmentbit ist unmittelbar nach dem Erstsegment als Duplikat zulässig und
überschreibt Block 0.

Die Zahl `200` ist die exklusive Kopiergrenze für Folgeindizes. Index `199`
wird kopiert, Index `200` nicht. Das Erstsegment kopiert Block 0 unabhängig
von `N`.

### 1.5 Reihenfolge, fehlende und duplizierte Segmente

- Ein Sprung vorwärts, ein älterer Index als der aktuelle `last_index` oder
  jede andere Reihenfolge wird still ignoriert. `last_index` bleibt stehen.
- Ein fehlender Block kann später noch als genau `last_index + 1` eintreffen.
  Ohne ihn kann die Assemblierung nicht fortschreiten. Es gibt keinen
  statisch belegten Timeout oder automatischen Abbruch.
- Nur die Wiederholung des jeweils aktuellen `last_index` gilt als Duplikat.
  Sie überschreibt denselben 1020-Byte-Block.
- Ein Duplikat des letzten Blocks nach bereits festgestelltem Abschluss kann
  erneut `complete` liefern und damit denselben Transfer nochmals in die Queue
  stellen. Auch ein nach Abschluss ignorierter Index mit weiterhin passendem
  Befehl kann wegen des unveränderten Abschlusszustands nochmals `complete`
  liefern. Ein legitimer Host darf deshalb nach dem letzten Segment weder
  Retry noch zusätzliche Segmente senden.

### 1.6 Befehlsfehler und Abbruchzustand

Bei `command != stored_command`:

```text
log("receiving data error ...")
stored_command = 0
```

`N`, `last_index`, Datenbuffer und Flagwort werden nicht zurückgesetzt. Der
abschließende Vergleich `N <= last_index + 1` wird trotzdem ausgeführt.
Weitere `0x08`-Folgesegmente passen anschließend nicht mehr zum gespeicherten
Befehl null. Nur ein neues Erstsegment stellt einen normalen Zustand wieder
her. Es gibt keine USB-Fehlerantwort.

Vollständige Befehle verarbeitet `0x0010df9c` danach nur für `0x08` und
`0xff`. Andere Befehle können im generischen Assembler formal abgeschlossen
werden, erzeugen hier aber keinen LCD-Queueeintrag.

### 1.7 Exakte Bedeutung von `1 <= N <= 200`

Für einen normalen, leeren Queuezustand gilt:

- `N=1`: 1020 Byte; erfolgreich allokierbar.
- `N=200`: Indizes `0..199`, exakt 204000 Nutzbyte; einschließlich internem
  Vier-Byte-Längenwort 204004 Byte und damit kleiner als die Queuekapazität
  `0x32000 = 204800`.
- `N=201`: Index 200 wird nicht kopiert; die zunächst berechnete Länge 205020
  Byte passt nicht in die Queue.

Damit ist `1 <= N <= 200` die einzige statisch begründete, normale und
speichersichere Hostregel. Sie bedeutet nicht:

- dass das 23-Bit-Feld auf 200 begrenzt wäre;
- dass die Firmware das Erstsegment gegen 200 validiert;
- dass `N <= 200` bei bereits belegter Queue eine Allokation garantiert;
- dass alle `N > 200` wegen der Queuegröße ausnahmslos scheitern.

Der letzte Punkt korrigiert Analyse 02. `0x0010df9c` berechnet die Queuelänge
mit 32-Bit-ARM-Arithmetik als:

```text
payload_length = (N * 1020) mod 2^32
```

Für den extremen Feldbereich `N=4210753..4210953` liegt das übergelaufene
Ergebnis wieder zwischen 764 und 204764 Byte und kann in einer leeren Queue
allokierbar sein. Ein solcher Transfer benötigte mehr als vier Millionen
sequenzielle Reports; ab Index 200 würde nichts mehr in den Assembler kopiert.
Am oberen Ende würde die anschließende Queuekopie sogar über die 204000
initialisierten Assembler-Nutzbytes hinaus lesen. Das ist ein statisch belegter
Fehlerfall, keine zulässige Hostbetriebsart.

### 1.8 Belegte Host-seitige Controlword-Bildung

Die Bildung ist nur für einen bereits auf ein ganzzahliges Vielfaches von
1020 Byte gebrachten Transportquellbuffer vollständig spezifizierbar. Der
Wert der bei einem JPEG eventuell notwendigen Schlussbytes ist noch offen:

```text
function build_reports(transport_source):
    require len(transport_source) % 1020 == 0
    N = len(transport_source) / 1020
    require 1 <= N <= 200

    for i in 0 .. N-1:
        if i == 0:
            field = N
            first = true
        else:
            field = i
            first = false

        byte0 = 0x08
        byte1 = field & 0xff
        byte2 = (field >> 8) & 0xff
        byte3 = ((field >> 16) & 0x7f) | (first ? 0x80 : 0x00)
        data = transport_source[i*1020 : (i+1)*1020]
        report = byte0 || byte1 || byte2 || byte3 || data
        require len(report) == 1024
        send_exactly_once(report)
```

Nicht belegt und deshalb absichtlich nicht Bestandteil dieses Pseudocodes ist
`transport_source = jpeg || zero_padding`.

## 2. Letztes JPEG-Segment und Padding

### 2.1 USB-Assembler und Queue

Ein JPEG der Originallänge `L` benötigt auf dem Draht
`N = ceil(L / 1020)` Reports. Ist `L` nicht durch 1020 teilbar, muss der Host
den letzten Report dennoch auf exakt 1020 Datenbyte vervollständigen. Die
Firmware besitzt keine Darstellung für einen kürzeren letzten Datenblock.

Die Firmware:

- kopiert aus jedem Report genau 1020 Byte;
- kopiert nach Abschluss genau `N * 1020` Byte in die Queue;
- entfernt kein Padding;
- ergänzt kein Padding;
- sucht im USB-Softwarepfad nicht nach `ff d9`;
- reicht das Queue-Längenwort nicht an den Grafikblock weiter;
- reicht ausschließlich den Zeiger auf den vollständigen Queuepayload weiter.

Alle Hostbytes nach `ff d9` bleiben daher Bestandteil der Hardwarequelle.

### 2.2 Keine erhaltene USB-JPEG-Originallänge

Im USB-Pfad bleibt `L` nirgends separat erhalten. Nach der Assemblierung kennt
die Firmware nur `N * 1020`. Die einzige in-band erkennbare Bildgrenze ist der
JPEG-EOI-Marker `ff d9`; die ARM-Software wertet ihn in diesem Pfad aber nicht
aus. Eine ursprüngliche Länge könnte nur durch erneutes Parsen des JPEG-Stroms
rekonstruiert werden, was hier nicht geschieht.

Das interne Queueformat lautet:

```text
uint32_le queue_payload_length = N * 1020
uint8_t   queue_payload[N * 1020]
internes Alignment auf vier Byte
```

Das Längenwort und Alignment liegen außerhalb der Grafikquelle.

### 2.3 Tatsächliche Bedeutung von `[0x00131940]`

`[0x00131940]` ist kein USB-Feld und keine Queue-Länge. Der einzige statisch
belegte Schreiber ist `0x0010eff4`:

```text
0x0010f004: [0x0013193c] = param_1  // source pointer
0x0010f008: [0x00131940] = param_2  // source byte length
```

Der gespeicherte Objektpfad `0x001279e8` lädt unmittelbar davor:

```text
source_pointer = [0x00131510]
source_length  = [0x0013150c]
0x0010eff4(source_pointer, source_length, x, y)
```

Diese Werte stammen aus dem geladenen Objekt-/Bootrecord. `0x0011acd8` prüft
die Länge gegen `0x31fe0 = 204768` und kopiert bei zugelassenem
Hardwareversuch exakt `[0x00131940]` Byte von `[0x0013193c]` in einen getrennt
allokierten Quellbuffer. Die Länge wird nur für Prüfung und Kopie benutzt; sie
wird nicht an den Hardwaredecoder übergeben.

Der USB-Pfad `0x0010df9c -> 0x001297e8 -> 0x003bb430 -> 0x00129b2c`
liest und schreibt weder `0x0013193c` noch `0x00131940`.

### 2.4 Softwaredecoder nach `ff d9`

Der Referenzsoftwaredecoder `0x0010f16c` ruft nach dem Entropiedecode den
Markerparser `0x00124988` auf und verlangt als nächsten Marker `0xd9`. Bei
erkanntem EOI setzt er seinen Abschlusszustand und kehrt zurück. Er vergleicht
die Position des EOI nicht mit dem Ende des Quellobjekts und liest danach in
diesem Decodeaufruf keine weiteren Quellbytes.

Damit ist für diesen Softwaredecoder bestätigt: Bereits zugängliche Bytes nach
dem ersten korrekt erreichten `ff d9` werden ignoriert. Ihr Wert wird durch
diesen Decoder nicht eingeschränkt.

### 2.5 Hardwaredecoder nach `ff d9`

Für den MMIO-Hardwaredecoder ist statisch bestätigt:

- Er erhält die Quellbasis, aber keine Originallänge.
- Der gespeicherte Objektpfad kopiert nur die tatsächlichen JPEG-Bytes in
  einen größeren `0x32000`-Byte-MEMDEV-Pixelbereich.
- Der MEMDEV-Konstruktor initialisiert den nachfolgenden Pixelbereich nicht
  sichtbar; insbesondere gibt es vor dem Hardwarestart kein explizites
  Nullfüllen des Puffersuffixes.
- Der Decoder meldet intern Bildheader/Geometrie über Status `0x40`, Abschluss
  über `0x04` und Fehler über `0x02`.

Daraus ist stark gestützt, dass der Hardwaredecoder seine logische Grenze am
JPEG-Strom, insbesondere am EOI, findet und nachfolgende Pufferspeicherbytes
nicht als Teil desselben Bildes auswertet. Sonst wäre bereits der
Firmware-Referenzpfad mit variabler JPEG-Länge nicht robust.

Aus dem ARM-Code nicht bestimmbar bleiben Hardware-Prefetch, Read-ahead und
der exakt tolerierte Byteinhalt nach `ff d9`. Insbesondere ist statisch nicht
bewiesen, dass ein USB-Schlussblocksuffix beliebig sein darf oder dass er null
sein muss. Die richtige Aussage lautet deshalb:

- Nullpadding wird weder erzeugt noch als Wert geprüft.
- Nullpadding ist keine belegte Protokollanforderung.
- Das Transportpadding wird vollständig weiterkopiert.
- Der Softwaredecoder ignoriert beliebige Bytes nach EOI.
- Für den Hardwaredecoder ist das Ignorieren stark gestützt, die exakte
  zulässige Suffixgrammatik aber offen.

## 3. Interface-1-IN-Nachricht `08 81`

### 3.1 Erzeuger und Inhalt

Der einzige belegte Aufrufer des Interface-1-IN-Senders `0x0011508c` ist
`0x00129b2c` bei `0x00129c34`. Er ruft auf:

```text
send_interface1_in(0x0012eba0, 2)
```

Die ROMbytes ab `0x0012eba0` lauten:

```text
08 81 00 00 cd ab 34 12 cd ab 34 12 51 00 00 00
```

`0x0011508c` kopiert jedoch nur die angeforderten zwei Byte in den dedizierten
BSS-Puffer `0x003ed340` und armiert anschließend USB-Selektor `0x14` mit fest
16 Byte. Deshalb gilt:

| Byte | Belegter Inhalt und Bedeutung |
| ---: | --- |
| 0 | konstant `0x08`; Kennung des ausschließlich hier gestarteten `0x08`-Queuepfads |
| 1 | konstant `0x81`; nicht benannter Annahme-/Startstatus |
| 2..15 | werden bei diesem Sendevorgang nicht frisch geschrieben; der dedizierte BSS-Puffer startet null und besitzt keinen weiteren belegten Schreiber |

Die nachfolgenden ROMwerte `cd ab 34 12 ...` werden nicht auf Interface 1 IN
kopiert. Der andere Nutzer derselben ROMregion `0x00128bc0` liest nur die
Wörter ab `+4` für einen getrennten SPI-nahen Pfad; er erzeugt keine
Interface-1-IN-Nachricht.

### 3.2 Auslösezeitpunkt

`0x00129b2c` wird periodisch aufgerufen. Sein Drosselzähler wird nach einer
Bearbeitung auf `5` gesetzt und bei jedem Aufruf dekrementiert; der Bulkpfad
wird bearbeitet, sobald das Dekrement `-1` ergibt. `08 81` entsteht genau dann,
wenn:

1. kein `0x08`-Grafikvorgang als aktiv markiert ist;
2. der nächste Framebuffer-Ringknoten den Frei-Zustand null besitzt;
3. `0x0012a390` einen nichtleeren Queueeintrag liefert.

Danach ist die Reihenfolge instruktionsgenau:

```text
send 08 81
graphics state reset
mode = 0x6021
target = next framebuffer
completion callback = 0x00115110
source = queue payload
operation 0x0c start
bulk_active = 1
```

Die Nachricht wird einmal pro aus der Queue gestarteter Grafikoperation
gesendet, nicht pro Segment.

### 3.3 Semantik und Alternativwerte

Byte 0 ist nicht dynamisch aus dem Controlword kopiert, korreliert aber
eindeutig mit dem einzigen hier zugelassenen Queuebefehl `0x08`. Byte 1 ist
eine ROMkonstante. Wegen des Zeitpunkts ist die engste belegte Semantik von
`0x81`:

```text
vollständiger Queueeintrag ausgewählt und Decoderstart steht unmittelbar an
```

„ACK“, „accepted“ oder „started“ sind brauchbare Beschreibungen, aber kein
Firmwarestring belegt einen offiziellen Namen.

Im v51-Image existieren:

- kein alternativer Byte-1-Wert für diesen Interface-1-IN-Sender;
- kein zweiter Aufrufer von `0x0011508c`;
- kein `0x08`-Busy-, Ready-, Done- oder Fehlerreport auf Interface 1 IN;
- keine Verbindung der Decoderstatusbits `0x04`/`0x02` zum Endpoint `0x84`.

Andere Vorkommen des Zahlenwerts `0x81`, insbesondere im Interface-0-
Befehlsdispatcher, sind nicht Teil dieser Nachricht.

Der Endpoint-`0x84`-Completion-Callback `0x0010e0a8` bestätigt nur das Ende
des USB-IN-Transfers und löscht ein Feld bei `0x00131320`. Er erzeugt keine
weitere Nachricht und ist nicht mit dem Decoderabschluss verbunden.

### 3.4 Muss Hostsoftware warten?

Der Decoderstart hängt nicht von einem Host-Read oder einer Bestätigung ab.
Hostsoftware muss daher nicht warten, damit die Firmware fortfährt. Will der
Host jedoch feststellen, ob der Queueeintrag tatsächlich ausgewählt und der
Startpfad erreicht wurde, ist `08 81` die einzige statisch belegte positive
Beobachtung.

Auf `08 81` zu warten bestätigt weder JPEG-Gültigkeit noch Decodererfolg,
Framebuffer-Commit oder sichtbare Darstellung. Für einen Done-Zustand gibt es
keine bekannte Interface-1-Nachricht.

## 4. Rekonstruierter Transferlebenszyklus

Die gewünschte Sollfolge enthält zwei Schritte, die der USB-Pfad tatsächlich
nicht besitzt: eine vorgelagerte Software-JPEG-Prüfung und einen getrennten
Accelerator-Kopierbuffer. Der reale statische Ablauf ist:

| Schritt | Status | Statischer Befund |
| --- | --- | --- |
| Host sendet Erstsegment | **Bestätigt** | Bit 31 setzt Befehl, `N`, Index 0 und kopiert genau 1020 Byte. Ein laufender Teiltransfer wird ersetzt. |
| Host sendet Folgesegmente | **Bestätigt** | Nur aktueller Index oder genau nächster Index wird akzeptiert; normal `1..N-1`; jeder kopierte Block hat 1020 Byte. |
| Abschluss der Assemblierung | **Bestätigt** | `N <= last_index + 1`; keine Endmarke und keine Restlänge. |
| Vollständiger Queueeintrag | **Bestätigt, bedingt** | Nur Befehl `0x08`, nichtnull Länge und erfolgreiche Queueallokation; Länge `N*1020`; Fehler bleiben stumm. |
| Warten auf freien Ringknoten und inaktiven Grafikpfad | **Bestätigt** | `0x00129b2c` startet nur bei Queueeintrag, freiem `next`-Knoten und `bulk_active == 0`. |
| Interface-1 IN `08 81` | **Bestätigt** | Einmal nach erfolgreichem Queue-Peek und unmittelbar vor Grafikreset/Start; der Eintrag bleibt belegt. |
| Software-JPEG-Prüfung im USB-Pfad | **Bestätigt nicht vorhanden** | Weder `0x00110a58` noch `0x00124988` oder `0x0010f16c` ist aus dem USB-Pfad erreichbar. |
| Separater Acceleratorbuffer im USB-Pfad | **Bestätigt nicht vorhanden** | Der Queuepayload selbst wird als Source gesetzt. Der Kopierbuffer mit `[0x00131940]` gehört nur zum gespeicherten Objektpfad. |
| Hardwarequelle und Modus setzen | **Bestätigt** | Source = Queuepayload, Target = `current->next->framebuffer_base`, Modus `0x6021`. |
| Hardwaredecoder starten | **Bestätigt** | Operation `0x0c` startet MMIO-Block `0xb100a000`; die JPEG-Funktion ist durch den getrennten Referenzpfad stark typisiert. |
| JPEG-Header/Geometrie in Hardware | **Stark gestützt** | Status `0x40` liest Breite/Höhe aus `b100a028`; interner Hardwareparser ist im ARM-Code nicht sichtbar. |
| Dekodierung in nächsten Framebuffer | **Bestätigt** | Zielbasis ist der nächste Ringknoten; `0x6021` erzeugt zwei Byte pro erkanntem Pixel. |
| Hardwareabschluss oder -fehler | **Bestätigt intern** | Status `0x04` löscht `active` erfolgreich; Status `0x02` löscht `active` und setzt `error=1`. Keine USB-Meldung. |
| Queuefreigabe nach inaktivem Decoder | **Bestätigt** | `0x00129b2c` fragt nur `active==0`, ignoriert das Errorbit, gibt den Queueeintrag frei und markiert den Zielknoten `-1`. Dieser Schritt liegt vor dem sichtbaren Commit. |
| Vorzeitige Queuefreigabe bei Abbruchzustand | **Bestätigt, Semantik offen** | Solange der Decoder aktiv ist, kann ein Nullzustand bei `0x001315c4` `bulk_active` löschen und die Queue ohne Ready-Markierung freigeben. Die fachliche Bedeutung dieses globalen Zustands ist nicht vollständig typisiert. |
| Sichtbarer Display-Commit | **Stark gestützt** | `0x00129cf0` übernimmt bei seinem späteren Callback einen nichtfreien Folgeknoten und schreibt dessen Basis über `0x00109394` nach `b1002050`. Die Registerwirkung ist bestätigt; Sichtbarkeit wurde nicht real gemessen. |
| Ringfreigabe | **Bestätigt** | Beim Displaywechsel setzt `0x00129cf0` den zuvor aktuellen Knoten auf frei (`ready_state=0`). |

Als Zeitfolge:

```text
OUT Erstsegment
-> OUT Folgepakete
-> complete
-> Queueallokation und N*1020-Kopie
-> Warten auf Consumerbedingungen
-> IN 08 81
-> Queuepayload direkt als Hardwarequelle
-> Hardware-JPEG-Start
-> internes success oder error, beide beenden active
-> Queue freigeben; next->ready_state = -1 bei normalem Ende
-> späterer Displaycallback schreibt neue Framebufferbasis
-> bisher sichtbaren Ringknoten freigeben
```

Wichtig: Der Queueeintrag wird nicht erst nach dem sichtbaren Commit
freigegeben, sondern bereits nach dem vom Consumer beobachteten Ende des
Hardwarevorgangs. Außerdem prüft der Consumer das interne Decoder-Errorbit
nicht, bevor er den Zielknoten bereit markiert.

## 5. Statische Sicherheitsbewertung eines späteren JPEG-Tests

### 5.1 Bereits hinreichend belegt

Für einen später gesondert freizugebenden Versuch sind statisch belegt:

- Befehl und Controlwordbildung für normale `N=1..200`;
- exakt 1024 Byte pro Interface-1-OUT-Report, davon vier Control- und 1020
  Quelldatenbyte;
- streng einmalige Reihenfolge ohne Retry als sicherstes Hostverhalten;
- maximal 204000 Transportquellbyte im normalen Modell;
- JPEG als Quellformat des `0x6021`-Hardwareblocks;
- 320×320 als passende Zielgeometrie;
- `0x08` führt im rekonstruierten Pfad zu flüchtigem Queue-, Decoder- und
  Displayzustand und erreicht keinen bekannten SPI-, Flash- oder
  Persistenzschreibpfad;
- ein anschließender reiner Read kann höchstens `08 81` als Startannahme
  beobachten und löst selbst keinen Decoder- oder Persistenzpfad aus.

### 5.2 Noch blockierende offene Punkte

Ein minimaler Test mit einem kleinen gültigen 320×320-JPEG, genau einer
Bildübertragung, keinem Retry und anschließend nur lesender Beobachtung ist
noch nicht hinreichend exakt spezifizierbar. Blockierend sind:

1. **Schlussblocksuffix:** Bei `L mod 1020 != 0` ist die erforderliche Anzahl
   zusätzlicher Bytes bekannt, ihr exakt zulässiger Inhalt für den
   Hardwaredecoder aber nicht. Nullpadding ist nicht belegt.
2. **Keine USB-Vorvalidierung:** Der USB-Pfad startet den Hardwaredecoder ohne
   SOI-/SOF-/EOI-Prüfung durch ARM-Code. Welche JPEG-Untermenge die Hardware
   zuverlässig akzeptiert, insbesondere progressive SOF2, Subsampling,
   Tabellen- und Metadatensegmente, ist nicht vollständig statisch bestimmt.
   Ein konservatives Baseline-SOF0-JPEG reduziert diese Unsicherheit, beseitigt
   sie aber nicht als Evidenzlücke.
3. **Keine Done-/Fehlerevidenz:** `08 81` kommt vor Decoderstart. Weder Erfolg,
   Fehler noch sichtbarer Commit sind über Interface 1 IN beobachtbar. Ein
   reiner Read kann den Testausgang deshalb nicht eindeutig feststellen.
4. **Stumme Fehlerfälle:** Reihenfolgefehler, Queueallokationsfehler und einige
   Abbruchzustände liefern keine Fehlerantwort. Ein Hosttimeout könnte nur
   „keine Startnachricht“ feststellen, nicht die Ursache.
5. **Decoderfehler wird beim Commitpfad nicht ausgewertet:** Der Consumer
   markiert nach `active==0` den Zielknoten bereit, ohne das interne Errorbit zu
   prüfen. Das Verhalten des sichtbaren Bildes bei Hardwarefehler bleibt
   unbestimmt.
6. **Firmwareversionsdifferenz:** Analysiert ist v51; das reale Gerät lieferte
   zuletzt `0x0049`. Ohne v49-Binärdatei oder passiven Herstellerreferenztrace
   ist die bytegleiche Gültigkeit dieses Pfads für das konkrete Gerät nicht
   bestätigt.
7. **Interface-1-Host-API-Framing:** 1024 Drahtbytes sind bestätigt. Das für
   Interface 0 real bestätigte zusätzliche hidraw-API-Nullbyte ist für einen
   Interface-1-Write noch nicht passiv oder real bestätigt worden. Ein
   späteres Testverfahren muss klar zwischen API-Puffer und Drahtreport
   unterscheiden.
8. **Start-/Abbruchzustand `0x001315c4`:** Seine Einwirkung auf die Freigabe
   eines laufenden Bulktransfers ist bestätigt, die vollständige fachliche
   Zustandssemantik und der erwartete Ausgangswert vor einem Einzeltest sind
   offen.
9. **Kein passiver Herstellerreferenztransfer:** Ein legitimer Mitschnitt
   könnte Schlussblocksuffix, Hostframing, tatsächliches JPEG-Profil,
   `08 81`-Timing und v49-Verhalten ohne eigenen Write gleichzeitig belegen.

Ein exakt durch 1020 teilbares JPEG mit EOI am Ende des letzten Reports würde
den ersten Blocker technisch umgehen, ist aber noch kein vollständiger Ersatz
für die fehlende v49- und Erfolgsevidenz. Das künstliche Erreichen dieser Länge
darf seinerseits keine unbestätigten JPEG-Marker- oder Paddingannahmen
einführen.

## 6. Schlussfolgerung

Das Controlword und der normale Segmenttransport sind für einen Hostencoder
ausreichend exakt rekonstruiert. Nicht ausreichend rekonstruiert ist die
letzte semantische Grenze zwischen JPEG-EOI und dem festen 1020-Byte-
Transportblock. Die Firmware behandelt alle Schlussbytes als Quelldaten, der
Softwaredecoder ignoriert nach EOI alles Weitere und der Hardwarepfad ist stark
EOI-gesteuert, aber seine exakte Suffixakzeptanz ist nicht aus ARM-Code
beweisbar.

`08 81` schließt diese Lücke nicht: Die Nachricht bestätigt nur Queueannahme
und unmittelbar bevorstehenden Start. Weil sie vor dem Decoder entsteht und
kein Done-/Fehlerreport folgt, kann ein späterer reiner Read keinen sicheren
Darstellungserfolg beweisen. Zusammen mit der v51/v49-Differenz verhindert das
derzeit eine hinreichend sichere und exakte Freigabespezifikation für einen
eigenen JPEG-Live-Test.
