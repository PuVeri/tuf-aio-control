# Statische Rekonstruktion des LCD-JPEG-Transports 04

Stand: 2026-09-02

## Zweck und Sicherheitsrahmen

Diese Untersuchung schließt die noch statisch lösbaren Fragen zu
`0x001315c4`, zum Interface-1-HID-Framing und zur JPEG-Untermenge. Verwendet
wurden ausschließlich die bereits vorliegenden Firmware-, Descriptor- und
Hostanalyseartefakte sowie die offizielle N9H20-Dokumentation. Das bestehende
Ghidra-Projekt wurde mit `-readOnly -noanalysis` geöffnet. Es gab keine
Gerätekommunikation, keinen HID-Write, keine Emulation, keine Freigabe weiterer
Schreibrechte und keinen Zugriff auf SPI-, Flash- oder Persistenzpfade.

Der erweiterte reproduzierbare Export liegt in
`research/ghidra-scripts/ExportLcdTransportLifecycle.java`. Er umfasst nun
sämtliche statisch gefundenen direkten Benutzer von `0x001315c4`, dessen
Konfigurationsquelle und den periodischen Hilfspfad. Beispielaufruf:

```text
analysis_tmp=$(mktemp -d /tmp/tuf-aio-lcd04.XXXXXX)
env XDG_CONFIG_HOME="$analysis_tmp/config" \
  /home/l/HeartdriveLAB/shared/tools/ghidra/ghidra_12.1_PUBLIC/support/analyzeHeadless \
  research/ghidra-projects device-firmware-v51-ghidra12-1 \
  -process device-firmware-v51.bin -readOnly -noanalysis \
  -scriptPath research/ghidra-scripts \
  -postScript ExportLcdTransportLifecycle.java \
  "$analysis_tmp/lcd-transport-lifecycle.txt"
```

## Ergebnis in Kürze

1. `0x001315c4` ist ein vollständiges 32-Bit-Countdownwort, kein belegtes
   Bitfeld. `0` bedeutet abgelaufen/inaktiv, `0xffffffff` ist ein nicht
   dekrementierter Sentinel, alle anderen Werte werden periodisch dekrementiert.
   Der Bootdefault der zugehörigen Konfiguration ist `5000`.
2. Beim vollständigen Interface-1-`0x08`-Transfer wird der konfigurierte
   Countdown nach `0x001315c4` kopiert. Während der Hardwaredecoder aktiv ist,
   schützt ein Wert ungleich null den Queueeintrag; bei null gibt der Consumer
   ihn vorzeitig und ohne Ready-Markierung frei. Der Wert ist daher ein
   hostrelevanter Timeout-/Lease-Zustand.
3. Interface 1 hat einen unnummerierten 1024-Byte-OUT-Report. Auf EP `0x03`
   stehen exakt 1024 Byte und das Controlword beginnt bei Drahtbyte 0. Unter
   Linux benötigt `hidraw.write()` daraus abgeleitet exakt 1025 Byte:
   `00 || report[1024]`; der Kernel entfernt das führende API-Nullbyte.
4. Der N9H20-Hardwarecodec unterstützt laut Hersteller Baseline Sequential,
   nicht Progressive JPEG. Für den direkten USB-Pfad ist die konservativ
   belegte Untermenge deshalb SOF0/8 Bit, Y oder YCbCr mit 4:4:4, 4:2:2 oder
   4:2:0. SOF1/SOF2 werden vom Software-Headerparser erkannt, sind aber kein
   Beleg für Hardwareunterstützung.
5. Die Firmware kopiert nach EOI jedes verbleibende Byte des letzten
   1020-Byte-Segments unverändert und kennt die ursprüngliche JPEG-Länge nicht.
   Was ASUS dort tatsächlich erzeugt, ist weder in der Gerätefirmware noch im
   zugänglichen Hostartefakt enthalten. Dies ist nur durch den Hostproducer oder
   einen Referenzcapture lösbar.

## 1. `0x001315c4`: vollständige Rekonstruktion

### 1.1 Datentyp und Werte

Alle Zugriffe erfolgen mit 32-Bit-`ldr`/`str`; es existieren keine Byte-,
Halfword- oder Maskenzugriffe. Die einzige Sonderwertprüfung lautet in
`0x0012bbac` sinngemäß:

```text
value = *(uint32_t *)0x001315c4
if value != 0 and value != 0xffffffff:
    value = value - 1
    *(uint32_t *)0x001315c4 = value
```

Damit ist statisch belegt:

| Wert | Wirkung |
| --- | --- |
| `0x00000000` | abgelaufen beziehungsweise Gate offen; kein Dekrement |
| `0xffffffff` | Sentinel; kein Dekrement und Gate bleibt geschlossen |
| jeder andere 32-Bit-Wert | pro Callbackaufruf modulo 32 Bit um eins reduziert |

Ein fachlich strukturiertes Bitfeld ist ausgeschlossen. Für normale Werte ist
die passende Typisierung ein 32-Bit-Countdown mit Sentinel. Die Firmware
erzwingt weder Positivität noch einen oberen Grenzwert. Andere negative Werte
als `-1` würden ebenfalls modulo 32 Bit dekrementiert und sind kein sinnvoll
belegter Hostzustand.

Die Quelle ist das DWORD bei `0x004e8348 + 0x108 = 0x004e8450`. Der
Initialisierer `0x00127854` schreibt dorthin `0x00001388 = 5000` und denselben
Wert nach `+0x10c`. Interface-0-Unterbefehl `0x19` ersetzt `+0x108` durch ein
beliebiges Host-DWORD; eine Bereichsprüfung findet dabei nicht statt.

### 1.2 Alle direkten Reads und Writes

Der read-only Pointer-Scan findet genau sechs Literalstellen für
`0x001315c4`: `0x0010e09c`, `0x00126d44`, `0x001275e8`, `0x00127cd4`,
`0x00129cec` und `0x0012bc38`. Daraus ergeben sich diese direkten Zugriffe:

| Adresse | Zugriff | Auslöser und Wirkung |
| --- | --- | --- |
| `0x0010e05c` | Write | Nach vollständig assembliertem Interface-1-Befehl `0x08`: kopiert Konfiguration `+0x108` nach `0x001315c4`. Der Write erfolgt auch dann, wenn die Queueallokation zuvor fehlschlug. |
| `0x00127010` | Write | Interface-0-Case `0x0a`: lädt Konfiguration `+0x108`, bevor der zugehörige Grafik-/Objektpfad gestartet wird. |
| `0x00127060` | Write | Interface-0-Case `0x0b`: derselbe Reload vor dem zugehörigen Grafik-/Objektpfad. |
| `0x001271ac` | Write | Interface-0-Case `0x08`: lädt Konfiguration `+0x108` unmittelbar vor Grafikreset und Decoderfolge. |
| `0x00127230` | Write | Interface-0-Case `0x09`, gesetztes höchstes Payloadbyte: setzt `0xffffffff`. |
| `0x001272e0` | Write | Interface-0-Case `0x09`, höchstes Payloadbyte null: setzt `0`; zugleich werden der Begleitzustand `0x001315cc` und ein Modusbyte gelöscht. |
| `0x0012bbb8` | Read | Periodischer Helfer liest den Countdown und unterscheidet `0`, `-1` und alle übrigen Werte. |
| `0x0012bbcc` | Write | Periodischer Helfer dekrementiert jeden Wert außer `0` und `-1`. |
| `0x0012bc30` | Write | Wenn der getrennte Countdown `0x001315cc` null erreicht, wird `0x001315c4` ebenfalls auf null gesetzt. |
| `0x00126bd8` | Read | Ein gespeicherter Objekt-/Boot-Grafikpfad darf nur fortschreiten, wenn `0x001315c4 == 0` und der Hardwaredecoder nicht mehr aktiv ist. |
| `0x00127b9c` | Read | Der normale gespeicherte JPEG-/Displaytask arbeitet nur, wenn sowohl `0x001315c4` als auch `0x001315cc` null sind. |
| `0x00129ca8` | Read | Während eines Interface-1-Decodes: ist Hardware noch aktiv und der Wert null, wird der Queueeintrag freigegeben und der lokale `bulk_active`-Zustand gelöscht. |

Die BSS-Nullinitialisierung ist kein expliziter ARM-Write im Image. Indirekte
Aliase auf dieselbe Adresse wurden nicht gefunden.

### 1.3 Periodik und Wandzeit

`0x001279e8` registriert `0x0012bbac` über `0x0012bd68` als Callback. Der
gemeinsame Timerpfad berechnet verstrichene Ticks und ruft registrierte
Callbacks periodisch auf. Belegt ist deshalb die Einheit
**Callbackaufrufe**, nicht Millisekunden. Dass `5000` etwa fünf Sekunden oder
eine andere konkrete Wandzeit bedeutet, ist aus dem analysierten Pfad nicht
hinreichend ableitbar und wird nicht angenommen.

Beim Übergang des normalen Countdowns von `1` auf `0` kann `0x0012bbac`
zusätzlich einen internen `0x19`-Restart anfordern, sofern Konfiguration
`+0x111 != 0` und das Modusbyte `0x001315c1 == 1` sind. Der Sentinel `-1`
wird dagegen nicht dekrementiert. Im Interface-0-Case `0x09` wird er mit dem
zweiten konfigurierbaren Countdown `0x001315cc` kombiniert; dessen Ablauf
löscht schließlich auch `0x001315c4`.

### 1.4 Lebensdauer eines Interface-1-Transfers

Für den großen USB-`0x08`-Pfad gilt:

1. Während der Segmentassemblierung wird `0x001315c4` nicht verändert.
2. Erst nachdem das letzte Segment den Transfer formal abgeschlossen hat,
   übernimmt `0x0010df9c` `config+0x108` nach `0x001315c4`.
3. Der Queueconsumer startet später den Hardwaredecoder und setzt seinen
   lokalen `bulk_active`-Zustand.
4. Solange die Hardware aktiv ist, verhindert jeder Wert ungleich null die
   vorzeitige Queuefreigabe. Der periodische Helfer dekrementiert den Wert,
   außer er ist `0` oder `-1`.
5. Meldet die Hardware zuerst inaktiv, gibt der Consumer den Queueeintrag frei
   und markiert den Ziel-Ringknoten bereit. Er löscht `0x001315c4` dabei nicht.
6. Erreicht der Countdown zuerst null, gibt der Consumer den Queueeintrag frei,
   löscht `bulk_active` und markiert den Zielknoten **nicht** bereit.
7. Der Countdown kann nach einem normalen Decoderende weiterlaufen und sperrt
   bis zu seinem Ablauf die konkurrierenden gespeicherten Grafikpfade.

Der Timeoutzweig stoppt den Hardwaredecoder nicht sichtbar. Er macht lediglich
den Queueplatz wieder verfügbar. Bei einem unmittelbar folgenden Transfer
könnte derselbe Backing-Bereich daher erneut verwendet werden, obwohl ein
hängender Hardwarezugriff nicht nachweislich beendet wurde. Für einen späteren
Einmaltest sind „kein Retry“ und „kein weiterer Bildtransfer“ deshalb
sicherheitsrelevant; sie ersetzen aber keine Kenntnis des aktuellen
Timeoutwerts.

### 1.5 Beziehung zu Queue, Decoder und Framebuffer-Ring

`0x001315c4` ist kein Feld der Queue und kein Feld eines Framebuffer-Ringknotens.
Seine Beziehungen sind Kontrollbeziehungen:

```text
vollständiges Interface-1-0x08
  -> Queueeintrag erzeugen
  -> config+0x108 nach 0x001315c4 laden

Queueconsumer
  -> Queueeintrag peeken
  -> 08 81 senden
  -> Hardwaredecoder mit Queuepayload starten
  -> solange Hardware aktiv:
       0x001315c4 != 0  => Queue bleibt belegt
       0x001315c4 == 0  => Queue ohne Ready-Markierung freigeben
  -> bei Hardwareende:
       Queue freigeben, Ziel-Ringknoten ready setzen
```

Der sichtbare Framebufferwechsel erfolgt später aufgrund des Ready-Feldes des
Ringknotens. `0x001315c4` wählt weder Zielbuffer noch sichtbaren Ringknoten und
ist kein Display-Commit-Flag. Es ist aber als Lease/Timeout für die Lebensdauer
der Decoderquelle sicherheitsrelevant und durch den Host über die
Interface-0-Konfiguration beeinflussbar.

## 2. Interface-1-HID-Framing

### 2.1 Firmware- und descriptorseitig bestätigt

Der Reportdeskriptor von Interface 1 enthält:

```text
75 08       Report Size  = 8 Bit
96 10 00    Report Count = 0x0010 = 16   (Input)
81 02       Input
96 00 04    Report Count = 0x0400 = 1024 (Output)
91 02       Output
```

Er enthält kein Global Item `Report ID` (`0x85`). Der USB-Deskriptor bestätigt
EP `0x03` OUT als Interruptendpoint mit `wMaxPacketSize = 0x0400` und EP
`0x84` IN mit `wMaxPacketSize = 0x0010`.

Der Interface-1-OUT-Callback `0x0010df9c` armiert exakt `0x400` Byte und ruft
den Segmentempfänger mit demselben Endpointbuffer auf. `0x001297e8` liest das
Little-Endian-Controlword ab Bufferbyte 0 und kopiert Bufferbytes `4..1023`
als 1020 Nutzbyte. Auf dem USB-Draht gilt daher exakt:

```text
EP 0x03 OUT, 1024 Byte:
wire[0..3]    = Controlword
wire[4..1023] = 1020 Segmentbytes
```

Es existiert kein Report-ID-Byte auf dem Draht und kein freies Präfixbyte vor
dem Command.

### 2.2 Aus Linux-`hidraw`-Semantik abgeleitet

Die offizielle Linux-`hidraw`-Dokumentation verlangt bei `write()`, dass Byte 0
des Userspace-Puffers die Reportnummer enthält; bei unnummerierten Reports ist
sie null. Im USB-HID-Pfad entfernt `usbhid_output_report()` dieses Nullbyte vor
dem Interrupttransfer und zählt es nur für den erfolgreichen API-Rückgabewert
wieder hinzu:

- <https://www.kernel.org/doc/html/latest/hid/hidraw.html>
- <https://github.com/torvalds/linux/blob/master/drivers/hid/hidraw.c>
- <https://github.com/torvalds/linux/blob/master/drivers/hid/usbhid/hid-core.c>

Damit lautet die Linux-Hostgrenze für Interface 1:

```text
hidraw.write(), exakt 1025 Byte:
00 | <1024 Byte Outputreport>

USB EP 0x03 OUT, exakt 1024 Byte:
     <1024 Byte Outputreport>
```

Ein erfolgreicher `write()` muss `1025` zurückgeben. Ein 1024-Byte-Aufruf ohne
führende Reportnummer ist nicht die dokumentierte belastbare API-Form. Für
`hidraw.read()` wird bei unnummerierten Reports kein Nullbyte ergänzt; ein
Interface-1-IN-Report wird als exakt 16 Byte beginnend mit seinem Nutzbyte 0
gelesen.

### 2.3 Noch empirisch unbestätigt

Auf Interface 1 wurde absichtlich kein Write ausgeführt. Die konkrete
`1025 -> 1024`-Abbildung ist deshalb für dieses Gerät nicht live beobachtet,
sondern aus Descriptor, Firmware und generischer Linux-Semantik geschlossen.
Dieselbe Abbildung ist auf Interface 0 bereits real bestätigt:

| Grenze | Interface 0 | Interface 1 |
| --- | ---: | ---: |
| Outputreport laut Descriptor | 440 | 1024 |
| Linux-`hidraw.write()` | 441 | 1025, abgeleitet |
| API-Präfix | `00` | `00`, abgeleitet |
| Drahtendpoint | `0x01` OUT | `0x03` OUT |
| Drahtbyte 0 | Command | Command |
| Inputreport | 440 auf `0x82` | 16 auf `0x84` |

Ein passiver Wire-Capture kann nur die 1024 Drahtbytes bestätigen; das vom
Kernel entfernte Userspace-Nullbyte ist dort definitionsgemäß nicht sichtbar.

## 3. JPEG-Untermenge

### 3.1 Drei getrennte Evidenzebenen

Die Firmware enthält drei verschiedene Ebenen, die nicht gleichgesetzt werden
dürfen:

1. `0x00110a58` prüft einen Header und liest SOF-Felder.
2. `0x0011012c` bereitet den gespeicherten Referenzpfad vor; bei Bedarf kann
   dieser Pfad auf den Softwaredecoder `0x0010f16c` zurückfallen.
3. Der direkte USB-`0x08`-Pfad überspringt beide Funktionen und startet
   ausschließlich den N9H20-Hardwarecodec.

Die Aussage „der Headerparser akzeptiert es“ ist daher ausdrücklich kein
Beleg, dass ein USB-Bild vom Hardwaredecoder verarbeitet wird.

### 3.2 Was der Software-Headerpfad akzeptiert

`0x00110a58` verlangt SOI `ff d8` und sucht SOF0 (`ff c0`), SOF1 (`ff c1`)
oder SOF2 (`ff c2`). Bei SOF2 setzt er ein eigenes Progressive-Flag. Er liest:

- Sample Precision, ohne sie in dieser Funktion zu validieren;
- Höhe und Breite als Big-Endian-16-Bit-Werte und verlangt beide ungleich null;
- Komponentenanzahl `C` mit `1 <= C <= 4`;
- exakt `8 + 3*C` Byte SOF-Segmentlänge;
- pro Komponente ID, horizontales/vertikales Sampling-Nibble und
  Quantisierungstabellennummer.

Dieser Parser allein lässt somit SOF0/1/2, ein bis vier Komponenten und viele
Samplingwerte passieren. Genau daraus darf keine Hardwareunterstützung
abgeleitet werden.

### 3.3 Einschränkung des vorbereiteten Referenz-/Softwarepfads

`0x0011012c` akzeptiert für seine Bildpuffergeometrie nur:

- eine Komponente; oder
- drei Komponenten, wobei Komponente 1 und 2 jeweils Sampling `1x1` haben und
  Komponente 0 eine der Kombinationen `1x1`, `2x1`, `1x2`, `2x2` besitzt.

Dies entspricht bei üblicher Y/Cb/Cr-Reihenfolge 4:4:4, horizontalem 4:2:2,
vertikalem 4:4:0 und 4:2:0. Zwei oder vier Komponenten werden in dieser
Vorbereitung verworfen. Der Softwaredecoder besitzt getrennte sequentielle
und progressive Pfade; das ist ein statischer Beleg für implementierte
Progressive-Verarbeitung, aber weiterhin kein Erfolgstest für jede formal
akzeptierte Kombination.

Der Markerparser kennt außerdem Adobe-APP14. Dass er ein Metadatensegment
lesen kann, macht CMYK/YCCK oder Adobe-RGB nicht zu einer unterstützten
Ausgabe: vier Komponenten scheitern bereits an der genannten Vorbereitung.

### 3.4 Grenzen des N9H20-Hardwaredecoders

Die Firmware nennt `N9H20 UDC Library`, und ihr JPEG-MMIO-Block liegt bei
`0xb100a000`. Dies stimmt mit dem N9H20-Registerlayout überein, insbesondere
mit `JDECWH` bei `JPG_BA + 0x28`, das die Firmware in `0x001059f4` liest.

Das offizielle
[N9H20 Technical Reference Manual Rev. 1.17](https://www.nuvoton.com/export/resource-files/en-us--TRM_N9H20_Series_EN_Rev1.17.pdf)
beschreibt den Codec als **Baseline Sequential Mode** gemäß JPEG/T.81. Für
Decode nennt es:

- interleaved YCbCr 4:4:4, 4:2:2 und 4:2:0;
- Y-only/Grayscale als im Decoderregister-/Alignmentmodell vorhandenen Fall;
- RGB555, RGB565, RGB888 oder YUYV422 als Hardwareausgabe;
- Default- oder programmierbare Huffmantabellen;
- beliebige Primärbildbreite/-höhe innerhalb des Ressourcenmodells;
- 16-Bit-Breite und -Höhe im `JDECWH`-Ergebnisregister;
- ausgabeabhängige Ausrichtung auf 8- beziehungsweise 16-Pixel-Grenzen.

Damit gilt für den Hardwarepfad:

| JPEG-Eigenschaft | Statischer Stand |
| --- | --- |
| SOF0, 8-Bit Baseline Sequential | hardwareseitig bestätigt |
| SOF1 Extended Sequential | vom Firmware-Headerparser erkannt, vom Hardwaremanual nicht freigegeben |
| SOF2 Progressive | Softwarepfad vorhanden, vom Hardwaremanual nicht freigegeben |
| 1 Komponente Y/Grayscale | stark gestützt |
| 3 Komponenten YCbCr | hardwareseitig bestätigt |
| 4:4:4, 4:2:2 horizontal, 4:2:0 | hardwareseitig bestätigt |
| 4:4:0 vertikal | Firmwarevorbereitung kennt es; Hardwaremanual nennt es nicht |
| RGB als JPEG-Eingabefarbraum | nicht belegt |
| CMYK/YCCK, vier Komponenten | für den vorbereiteten Pfad verworfen und hardwareseitig nicht belegt |
| arithmetische JPEG-Codierung | nicht belegt; konservativ ausgeschlossen |
| hierarchische/differenzielle JPEG-Modi | nicht belegt; konservativ ausgeschlossen |

### 3.5 Geometrie und ASUS-sicherer Bereich

Der Headerparser kann formal Breite/Höhe `1..65535` darstellen. Das ist keine
ASUS-Pufferfreigabe. Der direkte USB-Pfad setzt einen festen
320×320-Framebuffer-Ring ein und besitzt vor Hardwarestart keine Prüfung, ob
die JPEG-Geometrie dazu passt. Außerdem stehen höchstens 204000
Transportquellbyte zur Verfügung.

Eine kleinere numerische Codecobergrenze ist weder im ASUS-Pfad noch in der
genannten N9H20-Codecbeschreibung belegt. Die an anderer Stelle genannte
N9H20-LCD-Auflösung bis 1024×768 ist eine Displaycontrollergrenze und darf
nicht als sichere JPEG- oder USB-Puffergrenze umgedeutet werden. Auch die
16-Bit-Felder des Ergebnisregisters sind nur Feldbreiten, keine Freigabe für
65535×65535.

Für einen späteren minimalen ASUS-Test ist daher nur **exakt 320×320** statisch
vertretbar. 320 ist für alle vom Hardwaremanual genannten Ausgabealignments
teilbar. Größere oder abweichende Geometrien werden trotz allgemeiner
N9H20-Fähigkeiten nicht als sicher freigegeben.

Die konservativ spezifizierbare JPEG-Untermenge lautet damit:

```text
SOI/EOI vorhanden
SOF0, 8-Bit Baseline Sequential
exakt 320 x 320
entweder Y/Grayscale 1x1
oder JFIF-konformes YCbCr 4:4:4, 4:2:2 oder 4:2:0
keine Progressive-, CMYK/YCCK-, RGB-, arithmetische oder hierarchische Variante
komprimierte Datei kleiner/gleich dem noch durch Padding bestimmten N*1020-Bereich
```

Für maximale Konservativität ist ein übliches JFIF-YCbCr-4:2:0-JPEG mit
Standard-Huffman-Codierung die engste Schnittmenge. Dies spezifiziert das
Bildformat, noch nicht den unbekannten letzten Segmentsuffix.

## 4. Padding nach JPEG-EOI

### 4.1 Firmwareseitig bestätigt

- Jeder Interface-1-Report besitzt 1020 Segmentbytes.
- Jedes erfolgreiche Segment wird vollständig kopiert, auch das letzte.
- Der Queueeintrag speichert nur `N * 1020`, nicht die ursprüngliche
  JPEG-Länge.
- Es gibt weder Restlängenfeld noch EOI-basierte Kürzung, Paddingprüfung,
  Paddingerzeugung oder Normalisierung.
- Der direkte Hardwarepfad erhält die Quellbasis, aber keine separate
  Quelllänge.
- Der Softwaredecoder des gespeicherten Referenzpfads beendet seine
  Markerfolge an `ff d9`; das beweist nicht die Toleranz des direkten
  Hardwarepfads für jeden Nachlauf.

### 4.2 Gezielte Suche nach Herstellermustern

Die v51-Firmware enthält weder eine plausible eingebettete Sequenz
`ff d8 ff` noch `JFIF`, `Exif` oder `Adobe` als JPEG-Beispiel, aus dem sich ein
Herstellersuffix gewinnen ließe. Der USB-Pfad ist nur Consumer; ein
Host-Paddingproducer ist dort prinzipbedingt nicht enthalten.

Das vorhandene InfoHub-Artefakt ist ein etwa 90-MB-Installercontainer. Der
lokale statische Extraktionsversuch erreicht wegen dessen nicht unterstützter
Setupstruktur keinen enthaltenen Hostproducer. Im zugänglichen PE-Wrapper
liegt kein statisch belegter JPEG-Segmentierer. Daraus folgt weder Null- noch
anderes Padding.

### 4.3 Ergebnis

Der Inhalt nach dem ersten vollständigen EOI `ff d9` bis zum Ende des letzten
1020-Byte-Segments ist **statisch unbestimmt**. Insbesondere sind nicht belegt:

- Nullbytes;
- `0xff`-Fillbytes;
- Wiederholung des letzten Bytes;
- unveränderte Alt-/Pufferbytes;
- ein zweites EOI;
- irgendeine vom Decoder verlangte konkrete Sequenz.

Die Gerätefirmware erwartet strukturell nur einen vollen 1020-Byte-Block und
kopiert ihn weiter. Welche Suffixbytes ASUS sendet, ist **nur durch die
Herstellersoftware beziehungsweise einen passiven Referenzcapture lösbar**.
Ein einzelner Capture belegt dabei lediglich die Herstellerpraxis für genau
diese Datei. Ob andere Nachläufe toleriert werden, kann ein passiver Capture
nicht beweisen.

## 5. Exakter Vertrag für einen späteren passiven Referenzcapture

Der Capture soll keine neue Softwareinstallation und keine eigenen Writes
beinhalten. Er zeichnet ausschließlich einen ohnehin ausgelösten
Herstellertransfer auf. Um alle verbleibenden Transportfragen zu beantworten,
muss er folgende Daten liefern.

### 5.1 Erfassungsumfang

- vollständige Enumeration mit VID/PID, `bcdDevice`, Konfiguration,
  Interface-/Endpointnummern und Reportdeskriptoren;
- sämtliche USB-Controltransfers und Interrupt-URBs beider HID-Interfaces;
- Interface 0: EP `0x01` OUT und `0x82` IN;
- Interface 1: EP `0x03` OUT und `0x84` IN;
- für jedes URB Submit- und Completion-Zeitstempel, Richtung, Endpoint,
  angeforderte/tatsächliche Länge, Status und vollständige Bytes;
- Beginn vor der Herstelleraktion und Ende erst nach sichtbarem Commit plus
  ausreichendem Nachlauf, damit spätere IN-Nachrichten oder Retries sichtbar
  wären;
- wenn möglich ein zeitlich synchronisiertes Video beziehungsweise ein
  protokollierter Zeitpunkt des sichtbaren Displaywechsels;
- die vom Hersteller ausgewählte Original-JPEG-Datei mit exakter Länge,
  SHA-256 und unveränderten Bytes, falls sie zugänglich ist.

Interface 0 muss gleichzeitig erfasst werden, weil dort unter anderem
Unterbefehl `0x19` den später nach `0x001315c4` geladenen Timeoutwert ändern
kann. Auch Setup-/Modusbefehle vor und nach dem großen Transfer sind für eine
vollständige Hostsequenz erforderlich.

### 5.2 Pro Interface-1-OUT-Transfer auszuwerten

Für jeden 1024-Byte-Report auf EP `0x03` sind zu speichern:

```text
timestamp
wire[0..3] als rohe Bytes und uint32_le
command = wire[0]
first   = (controlword >> 31) & 1
field23 = (controlword >> 8) & 0x7fffff
wire[4..1023] vollständig
```

Der Capture muss insbesondere enthalten:

1. den kompletten ersten Report mit `first=1`, Command `0x08` und `N`;
2. alle Folgereports und ihre Indizes in tatsächlicher Reihenfolge;
3. den kompletten letzten Report, nicht nur einen gekürzten Hexdump;
4. etwaige kurze Transfers, USB-Retries, Duplikate oder fehlende Indizes;
5. die vom Draht beobachtete Reportanzahl und den Vergleich mit `N`.

### 5.3 JPEG- und Paddingauswertung

Aus allen `wire[4..1023]` werden exakt `N * 1020` Byte zusammengesetzt. Zu
protokollieren sind:

- Offset und Bytes von SOI;
- vollständige Markerliste einschließlich SOF-Typ, Precision, Geometrie,
  Komponenten-IDs, Samplingfaktoren, Quantisierungs-/Huffmantabellen und APP0/
  APP14;
- Offset des ersten syntaktisch zum Bild gehörenden EOI;
- `jpeg_length = eoi_offset + 2`;
- `suffix_length = N*1020 - jpeg_length`;
- sämtliche Suffixbytes unverändert, zusätzlich eine Häufigkeitsübersicht und
  ein Hexdump von Anfang und Ende des Suffixes;
- Vergleich des rekonstruierten JPEG-Präfixes mit der Originaldatei.

Ein aussagekräftiger Referenztransfer muss ein JPEG verwenden, dessen Länge
nicht durch 1020 teilbar ist. Um eine allgemeine Paddingregel statt nur eines
Einzelfalls zu erkennen, sind später mindestens zwei Herstellertransfers mit
verschiedenen Restlängen nötig. Dies sind weiterhin passive Beobachtungen.

### 5.4 Interface-1-IN und Timing

Jeder 16-Byte-Report auf EP `0x84` ist vollständig zu erfassen. Für `08 81`
sind mindestens diese Zeitdifferenzen auszuweisen:

```text
t(IN submit/completion) - t(completion letzter EP-0x03-OUT-Report)
t(sichtbarer Commit)    - t(08 81)
t(jede weitere IN-Nachricht) - t(08 81)
```

Zu prüfen sind:

- ob der erste passende IN-Report exakt `08 81` plus welche Bytes 2..15 trägt;
- ob `08 81` nur einmal oder mehrfach erscheint;
- ob vor oder nach ihm andere Byte-1-Werte auftreten;
- ob Busy-, Fehler-, Ready- oder Done-artige Meldungen existieren;
- ob die Herstellersoftware vor weiteren Aktionen auf `08 81` oder eine
  spätere Nachricht wartet;
- ob der sichtbare Commit deutlich nach `08 81` liegt, wie es die v51-
  Firmwarestruktur erwarten lässt.

Die reine USB-Reihenfolge kann eine Hostwartelogik nur stark stützen. Ob der
Herstellerprozess tatsächlich blockierend auf einem Read wartet, erfordert
zusätzlich eine passive Host-API-/Prozessspur; ein Wire-Capture allein beweist
diese interne Kausalität nicht.

Ein Wire-Capture bestätigt das 1024-Byte-Gerätereportrahmenformat. Soll
zusätzlich die Hersteller-API-Grenze dokumentiert werden, muss separat der
Hostprozessaufruf erfasst werden; das HID-API-Nullbyte ist auf USB nicht
sichtbar.

## 6. Was ausschließlich Hostsoftware oder Referenzcapture noch beantwortet

Statisch geschlossen sind die Interface-1-Reportgrößen, das Linux-hidraw-
Nullpräfix, die Rolle von `0x001315c4` und die konservative Hardware-JPEG-
Untermenge. Offen bleiben:

1. **ASUS-Schlussblocksuffix:** exakte Bytes nach EOI und die allgemeine
   Erzeugungsregel. Nur Hostproducer oder Capture können sie zeigen.
2. **v49-Gleichheit:** ob das reale Gerät mit Versionswert `0x0049` denselben
   Consumer-, Timeout- und `08 81`-Pfad wie das analysierte v51-Image besitzt.
3. **Herstellersequenz:** welche Interface-0-Modus-/Timeoutbefehle ASUS vor dem
   Interface-1-Transfer sendet, insbesondere ob `config+0x108` geändert wird.
4. **Reales `08 81`-Verhalten:** exakte Bytes 2..15 auf v49, gemessener Abstand
   zum letzten OUT und ob weitere Interface-1-IN-Nachrichten folgen.
5. **Hostwartelogik:** ob die Herstellersoftware `08 81` nur liest, darauf
   wartet oder den sichtbaren Commit anders synchronisiert.
6. **Paddingtoleranz:** Ein Capture zeigt nur tatsächlich gesendete Bytes. Ob
   abweichende Suffixe sicher toleriert werden, bleibt selbst danach ohne
   aktiven Test unbelegt; für einen minimalen Test kann jedoch das exakt
   beobachtete Herstellermuster reproduziert werden.
7. **Wandzeiteinheit von `0x001315c4`:** Ein Capture kann den beobachteten
   Ablauf zeitlich eingrenzen, aber den internen Counter nicht direkt lesen.

Damit sind die rein statisch lösbaren Formatfragen ausgeschöpft. Ein späterer
eigener JPEG-Test ist erst dann exakt genug spezifizierbar, wenn mindestens ein
vollständiger v49-Herstellertransfer den Suffix, die Begleitbefehle und das
reale `08 81`-Timing liefert. Selbst dann bleibt `08 81` eine Annahme-/
Startnachricht und kein statisch belegtes Decoder-Done. Ein nachfolgender
reiner Versions-/Statusread kann den Decoderabschluss derzeit nicht bestätigen.
