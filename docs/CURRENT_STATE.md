# Aktueller Projektstand

Stand: 2026-09-02

## Ziel und Grenze

Ziel ist eine native Linux-Steuerung für das LCD der ASUS TUF Gaming LC III
360 ARGB LCD. OpenRGB bleibt für sämtliche RGB-Beleuchtung zuständig;
`tuf-aio-control` dupliziert diese Funktion nicht.

Das undokumentierte HID-Protokoll wird vorrangig statisch und passiv
untersucht. Zwei gesondert freigegebene, eng begrenzte reale `0x87`-Tests sind
abgeschlossen. Weitere HID-Schreibtests sind nicht freigegeben.

## Bestätigte Hardware- und Transportfakten

- Gerät: `0b05:1c7b`; zwei HID-Interfaces, Usage Page `0xff06`, Usage `0x01`,
  keine deklarierten Report-IDs.
- Interface 0: 440 Byte IN/OUT, Endpunkte `0x82` IN und `0x01` OUT.
- Interface 1: 16 Byte IN, 1024 Byte OUT, Endpunkte `0x84` IN und `0x03` OUT.
- Firmware: 32-Bit ARM Little Endian, 201692 Byte, Ghidra-Basis `0x00100000`.
- Endpointcallbacks: `0x0010deb8` = Interface 0 OUT, `0x0010df88` = Interface 0
  IN, `0x0010df9c` = Interface 1 OUT, `0x0010e0a8` = Interface 1 IN.
- Interface 0 führt über `0x001293f8 -> 0x001296d8 -> 0x00126dfc`.
- Interface 1 führt direkt über `0x0010df9c -> 0x001297e8`.
- Interface 0: 4 Byte Steuerwort + 436 Byte Nutzlast = 440 Byte.
- Interface 1: 4 Byte Steuerwort + 1020 Byte Nutzlast = 1024 Byte.
- Steuerwort: Byte 0 Befehl, Bit 31 Erstsegment, Bits 8..30 Anzahl/Index.
- Interne Events `0x35` und `0x38` sind keine USB-Endpunkte: `0x35` stellt
  vollständige Befehle zu, `0x38` ist der 440-Byte-Transporttick.
- Linux `hidraw.write()` benötigt für Interface 0 ein Host-API-Nullbyte plus
  440 Byte. Das Nullbyte gelangt nicht auf den USB-Draht.
- Der Firmware-Antwortbauer erzeugt segmentierte 440-Byte-Pakete; in diesem
  Pfad wurde keine Transportprüfsumme erkannt.
- Der USB-Gerätedeskriptor des realen Geräts meldet `bcdDevice 0.49`.
- Dynamische `/dev/hidrawX`-Nummern sind keine stabile Geräteidentität.

## Bestätigter Versionswertpfad `0x87`

Die v51-Firmware liefert statisch eine Zwei-Byte-Nutzantwort `0x0051`:

```text
Anfrage:  87 01 00 80 | 436 × 00
Antwort:  87 01 00 80 51 00 | 434 × 00
```

Der zweite reale Einmaltest bestätigte dieselbe Struktur mit `0x0049`:

```text
87 01 00 80 49 00 | 434 × 00
```

Damit sind `0x0049` über `0x87` und `bcdDevice 0.49` am realen Gerät
bestätigt; v51 liefert statisch `0x0051`. Eine bytegenaue Zuordnung des realen
Geräts zu einem offiziellen v49-Paket bleibt mangels v49-Binärdatei
abgeleitet. Details: `research/reports/firmware-v49-investigation.md`.

Die statische Sicherheitsklasse von `0x87` lautet wahrscheinlich rein
lesend. Sein Handler liest keinen Payload und baut nur die konstante Antwort;
der gemeinsame Prolog kann flüchtigen Zustand ändern, erreicht aber keinen
bekannten SPI-, Flash-, Datei-, Boot- oder Resetpfad.

## Reale Tests und passive Beobachtung

- Test 01 am 2026-08-05: genau ein Write und ein 440-Byte-Read; die
  Antwortbytes wurden nicht gespeichert.
- Test 02, dokumentiert am 2026-09-01: fünf Sekunden Ruhe, leere Inputqueue,
  genau ein Write, strukturell korrekte Antwort `0x0049`, kein Retry.
- Zwei passive `O_RDONLY`-Beobachtungen auf Interface 0 (zusammen 120 s) und
  ein paralleler 60-s-Vergleich auf Interface 1 lieferten keinen Report.
- OpenRGB hielt die LCD-HID-Knoten dabei nicht offen und erzeugte ohne aktive
  Änderung keinen sichtbaren Report.
- Die temporäre Schreibregel ist entfernt; beide Interfaces besitzen wieder
  `0640`.

## Statische LCD-/Bildanalyse 01

Die Ergebnisse stehen in
`research/reports/lcd-command-analysis-01.md`.

- Die Queue-Beziehung ist geschlossen: Endpointcallback `0x0010df9c`
  assembliert über `0x001297e8` zunächst separat bei `0x003bb480` und kopiert
  vollständige `0x08`-Transfers in Queue `0x003bb430`; `0x00129b2c` liest
  exakt aus dieser Queue.
- Interface 1 verwendet 1024-Byte-Reports mit vier Byte Steuerwort und 1020
  Byte Nutzlast. Das Erstsegment trägt die Segmentanzahl, Folgepakete den
  Index; abgeschlossen wird nach `N` Segmenten ohne separate letzte Länge
  oder beobachtete Transportprüfsumme.
- Queue `0x003bb430` verwendet Backing-Buffer `0x003edb40` mit `0x32000`
  Byte. Der getrennte Interface-0-Pfad verwendet Queue `0x003bb458` und
  Backing-Buffer `0x0041fb40`.
- `0x00129b2c` übergibt den Queue-Payload direkt als Datenzeiger an
  Grafikrouter `0x001065c4`; die Queue-Länge wird nur auf ungleich null
  geprüft. Descriptor, Breite, Höhe und Stride stammen aus getrenntem Zustand.
- Grafikmodus `0x6021` ist durch Vergleich mit `0x0011acd8` als
  16-Bit-Klassenpfad gut belegt. RGB565, Kanalreihenfolge und Byteorder bleiben
  offen.
- Ein ungepackter 320×320×16-Bit-Vollframe benötigt `0x32000` = 204800 Byte;
  der Interface-1-Assembler liefert maximal 200×1020 = 204000 Byte. Wegen
  dieser 800-Byte-Differenz ist ein vollständiger Rohframe nicht bestätigt.
- Der Objektpfad `0x001279e8 -> 0x0010f0d0 -> 0x0010eff4 -> 0x0011acd8`
  ist als JPEG-Pfad belegt: `0x00110a58` prüft `ff d8` sowie SOF0/1/2 und
  extrahiert Breite und Höhe; `0x0010f16c` dekodiert JPEG-Blöcke und Farben.
  Das beweist JPEG für gespeicherte Objekte, nicht für USB-`0x08`.
- `+0x110` wählt zwischen zwei Ganzzahl-Zeitumrechnungen. `+0x111` steuert
  Ablauf, Wiederholung und einen Sonderzustand `2`; fachliche Namen wie
  Animation oder Loop bleiben unbestätigt.

Reproduzierbarer Read-only-Export:
`research/ghidra-scripts/ExportLcdDataPath.java`.

## Statische LCD-/Paketmodellanalyse 02

Die vertiefte Rekonstruktion steht in
`research/reports/lcd-command-analysis-02.md`. Reproduzierbarer Read-only-
Export: `research/ghidra-scripts/ExportLcdPacketModel.java`.

- `0x001314d0` ist kein Grafikdescriptor, sondern das BSS-Feld für den
  aktuellen Framebuffer-Ringknoten. Der Knoten ist mindestens `0x10` Byte
  groß: `+0` Folgeknoten, `+4` Display-Framebufferbasis, `+8` unbekannt und
  `+0x0c` Frei-/Bereitzustand. Breite, Höhe, Stride und Callbacks liegen nicht
  in diesem Knoten.
- Der getrennte emWin-MEMDEV ist statisch typisiert: `0x18` Byte Header,
  320×320, 16 bpp, Stride 640 und anschließend `0x32000` Pixelbyte. Seine
  5/6/5-Umsetzung ist numerisch `R5` in Bits 0..4, `G6` in 5..10 und `B5` in
  11..15, also BGR565 als Little-Endian-Wort. Im Image gibt es keinen
  `REV`-/`REV16`-/`ROR #8`-Byte-Swap-Kandidaten.
- `0x6021` erzeugt zwei Byte pro Ausgabepixel; `0x14021` erzeugt vier. Die
  Dimensionen liest der Grafikblock aus Hardwarezustand, nicht aus dem
  Ringknoten oder dem USB-Steuerwort. Derselbe Block wird im beschleunigten
  JPEG-Pfad benutzt; JPEG für die USB-`0x08`-Quelle bleibt dennoch unbestätigt.
- Das Interface-1-Steuerwort ist vollständig: Byte 0 Befehl, Bytes 1/2 und
  die unteren sieben Bits von Byte 3 bilden das 23-Bit-Feld für Gesamtzahl
  beziehungsweise Index; Byte 3 Bit 7 kennzeichnet nur das Erstsegment. Es
  gibt keine separate Länge, Endmarke, Prüfsumme oder Paddingangabe.
- `200` ist unmittelbar die exklusive Kopiergrenze für Indizes, nicht die
  Feldgrenze. Durch die `0x32000`-Queuekapazität ist 200 zugleich die größte
  erfolgreich weiterleitbare Gesamtzahl. Ein Index 200 kann formal Abschluss
  auslösen, wird aber nicht kopiert; `N >= 201` scheitert danach an der
  Queueallokation.
- Ein zusätzliches Abschlusssegment, eine separate Restlänge und ein
  Entfernen oder Ergänzen von Padding sind statisch ausgeschlossen. Die vier
  USB-Controlbytes und das interne Queue-Längenwort liegen außerhalb der
  1020-Byte-Nutzlast, werden aber nicht an den Grafikblock weitergereicht.
- Die 800-Byte-Differenz ist daher keine rekonstruierbare Rohframe-Lücke:
  maximal 204000 Byte USB-Quelle und der 204800-Byte-Zielframebuffer sind
  getrennte Objekte. Das genaue, vermutlich kodierte Quellformat von
  USB-`0x08` ist noch offen; ein roher 320×320×16-Bit-Vollframe ist als
  Hostmodell nicht haltbar.
- Endpoint `0x84` wird einmal bei Queueentnahme und noch vor Grafikoperation
  `0x0c` mit 16 Byte gesendet. Nur das konstante Präfix `08 81` wird frisch
  geschrieben. Es ist eine Start-/Annahmenachricht, kein Segment-ACK und keine
  Abschluss- oder Fehlerantwort; Bytes 2..15 tragen keine belegte Semantik.

## Gefährliche und ausgeschlossene Pfade

- `0x88`: SPI-Lesen und bedingtes SPI-Schreiben bei `0x21000`.
- `0x0a..0x0d`: Objekt-/Blocktransfer mit indirekten Backends; persistente
  Schreibziele sind nicht ausgeschlossen.
- `0x1b`, `0x1c`, `0xfe`: persistenznaher Konfigurationspfad `0x00126814`.
- `0x1f`: Modusmutation und möglicher Bootcallback.
- `0x09`: Displaymutation; im Updater zusätzlich Completion-Flag.
- `0x86`: Firmwareblocktransfer; `0x02`: Updater-Abschluss/Reenumeration.
- `0x45`: Konfigurationslöschung im Updater.
- `0xff` mit Payload-DWORD 1: unaufgelöster indirekter Callback.

## Nächster klarer Arbeitsschritt

Die nächste Arbeit soll innerhalb der weiterhin passiven Grenze:

1. einen legitimen Herstellertransfer für einfache statische 320×320-Bilder
   passiv und zeitgleich auf Interface 0 und 1 erfassen;
2. aus diesem Referenzverkehr das Quellformat von `0x08`, die Terminierung des
   letzten 1020-Byte-Blocks und die Bedeutung von Status `0x81` ableiten;
3. die Hardwareausgabe von `0x6021` mit der statisch belegten
   Little-Endian-BGR565-MEMDEV-Belegung abgleichen und die unbekannten
   Ringknotenfelder nur bei zusätzlichem statischem Beleg benennen;
4. SPI-, Updater- und persistente Objektpfade ausgeschlossen halten.

Keine Gerätekommunikation, Emulation oder Firmware-Schreibrechte. Jeder
weitere reale HID-Write benötigt einen neuen ausdrücklich freigegebenen Auftrag.
