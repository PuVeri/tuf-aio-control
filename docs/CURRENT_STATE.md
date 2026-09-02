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
  Feldgrenze. `1 <= N <= 200` ist die normale speichersichere Hostgrenze. Ein
  Index 200 kann formal Abschluss auslösen, wird aber nicht kopiert; `N=201`
  scheitert an der Queueallokation. Analyse 03 dokumentiert zusätzlich einen
  ausschließlich fehlerhaften 32-Bit-Überlaufrandfall bei extrem großen `N`.
- Ein zusätzliches Abschlusssegment, eine separate Restlänge und ein
  Entfernen oder Ergänzen von Padding sind statisch ausgeschlossen. Die vier
  USB-Controlbytes und das interne Queue-Längenwort liegen außerhalb der
  1020-Byte-Nutzlast, werden aber nicht an den Grafikblock weitergereicht.
- Die 800-Byte-Differenz ist daher keine rekonstruierbare Rohframe-Lücke:
  maximal 204000 Byte USB-Quelle und der 204800-Byte-Zielframebuffer sind
  getrennte Objekte. Der nachfolgende Quellformatnachweis identifiziert die
  `0x6021`-Quelle als JPEG; ein roher 320×320×16-Bit-Vollframe ist als
  Hostmodell nicht haltbar.
- Endpoint `0x84` wird einmal nach erfolgreichem Queue-Peek und noch vor
  Grafikoperation `0x0c` mit 16 Byte gesendet; der Queueeintrag bleibt bis zum
  späteren Release belegt. Nur das konstante Präfix `08 81` wird frisch
  geschrieben. Es ist eine Start-/Annahmenachricht, kein Segment-ACK und keine
  Abschluss- oder Fehlerantwort; Bytes 2..15 tragen keine belegte Semantik.

## Statische LCD-/JPEG-Transportanalyse 03

Die vollständige Rekonstruktion steht in
`research/reports/lcd-command-analysis-03.md`. Reproduzierbarer Read-only-
Export: `research/ghidra-scripts/ExportLcdTransportLifecycle.java`.

- Das Controlword ist bytegenau: Byte 0 ist der Befehl; Bytes 1/2 und die
  unteren sieben Bits von Byte 3 sind das 23-Bit-Feld; Bit 7 von Byte 3 ist
  ausschließlich das Erstsegmentbit. Im ersten Report enthält das Feld `N`,
  danach den Index `1..N-1`.
- `1 <= N <= 200` bezeichnet die normale und speichersichere Hostgrenze,
  nicht Feldbreite oder vollständige Firmwarevalidierung. `N=0` wird formal
  abgeschlossen, aber nicht alloziert. Durch 32-Bit-Überlauf können
  `N=4210753..4210953` wieder kleine Queuelängen erzeugen; diese missbräuchliche
  Folge aus mehr als vier Millionen Reports ist keine zulässige Hostbetriebsart.
- Ein fehlender Block stoppt den Fortschritt ohne Timeout. Nur das jeweils
  aktuelle Segment darf dupliziert werden und überschreibt seinen Block. Ein
  Duplikat nach Abschluss kann denselben Transfer erneut einreihen; ein
  legitimer Host sendet deshalb genau einmal und ohne Retry.
- Jeder Report kopiert exakt 1020 Datenbyte. Im USB-Pfad existieren weder eine
  letzte Restlänge noch das Entfernen oder Erzeugen von Padding. Die
  ursprüngliche JPEG-Länge geht verloren; die Queue kennt nur `N*1020`.
- `[0x00131940]` ist die getrennte Länge eines gespeicherten JPEG-Objekts. Sie
  wird von `0x0010eff4` aus der Objekt-/Record-Länge gesetzt, begrenzt und
  steuert die Kopie in dessen Acceleratorbuffer. Der USB-`0x08`-Pfad berührt
  dieses Feld nicht.
- Im USB-Pfad gibt es keine vorgelagerte Software-JPEG-Prüfung und keinen
  separaten Accelerator-Kopierbuffer. Der Queuepayload wird direkt als Quelle
  des `0x6021`-Hardwaredecoders gesetzt.
- Der Softwaredecoder ignoriert Bytes nach einem korrekt erreichten `ff d9`.
  Der Hardwarepfad erhält keine Quelllänge und ist deshalb stark als
  EOI-terminiert gestützt; welche konkreten Schlussbytes er toleriert, bleibt
  statisch offen. Nullpadding ist nicht belegt.
- `08 81` entsteht nur in `0x00129b2c`, nachdem Queueeintrag und freier
  Zielknoten vorhanden sind, aber vor Grafikreset und Decoderstart. Im v51-
  Image gibt es auf Interface 1 keine alternativen Byte-1-Werte und keine
  Busy-, Ready-, Done- oder Fehlernachricht.
- Der Decoder meldet Erfolg und Fehler nur intern. Der USB-Consumer wartet
  lediglich auf `active==0`, prüft das Errorbit nicht, gibt die Queue frei und
  markiert den Zielknoten bereit. Der spätere Displaycallback schaltet die
  Framebufferbasis um und gibt den zuvor sichtbaren Ringknoten frei.
- Ein eigener JPEG-Live-Test ist noch nicht freigabereif. Blocker sind vor
  allem der unbekannte Schlussblocksuffix, fehlende Done-/Fehlerevidenz, die
  offene vollständige Hardware-JPEG-Untermenge, Interface-1-Hostframing und
  die v51/v49-Firmwaredifferenz.

## Statische LCD-/JPEG-Transportanalyse 04

Die statisch noch lösbaren Blocker sind in
`research/reports/lcd-command-analysis-04.md` geschlossen. Der erweiterte
Read-only-Export bleibt
`research/ghidra-scripts/ExportLcdTransportLifecycle.java`.

- `0x001315c4` ist ein vollständiges 32-Bit-Countdownwort, kein Bitfeld.
  `0` ist abgelaufen/inaktiv, `0xffffffff` ein nicht dekrementierter Sentinel;
  alle anderen Werte werden periodisch um eins reduziert. Die Quelle
  `config+0x108` hat Bootdefault `5000` und kann über Interface-0-Unterbefehl
  `0x19` ohne Bereichsprüfung geändert werden.
- Ein vollständiger Interface-1-`0x08`-Transfer lädt diesen Countdown erst
  nach der Segmentassemblierung. Solange der Hardwaredecoder aktiv ist,
  schützt ein Wert ungleich null den Queueeintrag. Bei null wird die Queue
  ohne Ready-Markierung freigegeben; der Hardwaredecoder wird in diesem Zweig
  nicht sichtbar gestoppt. Der Zustand ist daher eine hostrelevante
  Decoderquellen-Lease beziehungsweise ein Timeout, kein Display-Commit-Flag.
- Interface 1 besitzt einen unnummerierten 1024-Byte-OUT-Report. Auf EP `0x03`
  stehen exakt 1024 Byte, beginnend mit dem Command/Controlword. Aus der
  dokumentierten Linux-Semantik folgt für `hidraw.write()` exakt
  `00 || 1024-Byte-Report`, also 1025 Byte; der Kernel entfernt das API-
  Nullbyte. Dies ist für Interface 1 nicht live getestet, aber statisch und
  API-semantisch geschlossen. Interface-1-Reads liefern den unnummerierten
  16-Byte-IN-Report ohne Nullpräfix.
- Der Firmware-Headerparser erkennt SOF0/SOF1/SOF2 und ein bis vier
  Komponenten; das ist keine Decoderfreigabe. Die offizielle N9H20-
  Dokumentation beschränkt den Hardwarecodec auf Baseline Sequential. Die
  konservative direkte USB-Untermenge ist deshalb SOF0/8 Bit, exakt 320×320,
  Y/Grayscale oder JFIF-YCbCr mit 4:4:4, 4:2:2 beziehungsweise 4:2:0. SOF1,
  SOF2, 4:4:0, RGB, CMYK/YCCK und arithmetische oder hierarchische Varianten
  bleiben für den Hardwarepfad ausgeschlossen beziehungsweise unbelegt.
- Die Firmware enthält kein eingebettetes JPEG-Muster und keinen
  Hostproducer. Sie kopiert sämtliche 1020 Byte des letzten Segments, kennt
  die ursprüngliche JPEG-Länge nicht und erhält beziehungsweise prüft keinen
  konkreten Suffix. Nullpadding ist weiterhin nicht belegt und nur aus
  Hostsoftware oder Referenzcapture bestimmbar.
- Ein späterer passiver Capture muss beide Interfaces vollständig und mit
  URB-Zeitstempeln erfassen: alle EP-`0x03`-Segmente und Controlwords, SOI/EOI,
  den vollständigen letzten Block, jeden Suffixbyte, EP-`0x84`-IN-Nachrichten
  einschließlich `08 81`, alle begleitenden Interface-0-Befehle sowie nach
  Möglichkeit Original-JPEG und sichtbaren Commitzeitpunkt. Ein Capture zeigt
  Herstellerpraxis, nicht allgemein die Toleranz anderer Paddingwerte.
- Für einen eigenen JPEG-Test bleiben der ASUS-Suffix, die v49/v51-Gleichheit,
  die reale Begleit-/Timeoutsequenz und das Fehlen eines Decoder-Done-Status
  Blocker. `08 81` bestätigt nur Queueannahme/Start; ein reiner nachfolgender
  Versions-/Statusread bestätigt keinen Decoderabschluss.

## Statische InfoHub-Hostextraktion

Die vollständige statische Extraktion steht in
`research/reports/infohub-inno-extraction.md`; das versionierbare Datei-,
Größen- und SHA-256-Manifest liegt unter
`research/manifests/infohub-1.0.0.15-files.sha256`.

- Der vorhandene 90.476.632-Byte-Installer ist Inno Setup 6.4.0.1. Sein
  Inno-Datenbereich reicht von `0x000d7a00` bis `0x05645ca8` und enthält einen
  unverschlüsselten LZMA1-Solid-Chunk. Zwei LZMA1-Headerblöcke beschreiben 149
  Dateieinträge und 147 Dateilokationen.
- Der offizielle `innoextract`-Entwicklungsstand
  `6e9e34ed0876014fdb46e684103ef8c3605e382e` kennt exakt die
  `6.4.0.1`-Signatur. Er wurde unverändert und ohne Systeminstallation
  projektlokal gebaut; enthaltene Windows-Dateien oder Installer-Skripte
  wurden nicht ausgeführt.
- 147 eindeutige Dateien mit zusammen 248.549.932 Byte wurden nach
  `research/extracted/infohub-1.0.0.15/` extrahiert. Der vorgelagerte
  Inno-Prüflauf und alle 147 nachträglichen Manifestprüfungen waren
  erfolgreich.
- `ASUS InfoHub.exe` ist der primäre Hostkandidat: exakte
  `VID_0B05&PID_1C7B&MI_00`-Strings, SetupAPI-/HID-Imports,
  `CreateFile`/`ReadFile`/`WriteFile` und getrennte Diagnose für `LED HID1`
  und `LED HID2` liegen gemeinsam vor.
- `XYUI.dll` ist der sekundäre Bildaufbereitungskandidat: `image/jpeg`,
  Frame-JPG-Pfade, `SaveJpgImageFile`-/GIF-/OpenCV-Exporte und ein
  320×320-bezogener Buildpfad sind belegt. HID oder SetupAPI importiert die
  DLL nicht.
- Rohe Funde von Reportgrößen, JPEG-Markern und `0x80..0x87` bleiben ohne
  Kontrollflussbezug absichtlich unbewertet. Eine Senderfunktion ist noch
  nicht rekonstruiert.

## Öffentlicher Protokollfamilien-Cross-Check

Der eng begrenzte Quellenvergleich steht in
`research/reports/lcd-protocol-family-crosscheck.md`.

- Öffentlich dokumentierte verwandte Geräte stimmen in einer ungewöhnlich
  spezifischen Kombination mit ASUS überein: zwei Control-/Bild-HID-Interfaces,
  Endpunkte `0x01/0x82` und `0x03/0x84`, Reportgrößen 440/1024/16 Byte,
  4+1020-Byte-Bildaufteilung, Befehl `0x08`, Erstwort `08 N 00 80` und die
  Controlfamilie `0x80..0x87`. Ein gemeinsamer Protokollstamm ist damit stark
  gestützt; OEM- oder Firmwareidentität folgt daraus nicht.
- `ttlcd` und `th420-display` erzeugen das letzte kurze JPEG-Segment als vollen,
  nullinitialisierten 1020-Byte-Nutzblock. Eine veröffentlichte Beschreibung
  eines Hersteller-Captures berichtet ebenfalls Nullen nach EOI. Das ist exakt
  mit der ASUS-Vollblockkopie und der fehlenden Restlänge kompatibel und macht
  Nullpadding zur konservativsten, stark begründeten Kandidatenregel. Ein
  ASUS-v49-Transfer selbst ist damit noch nicht beobachtet.
- Beide veröffentlichten Sender verwenden Folgeindizes `1..N-1` und stimmen
  damit mit der ASUS-v51-Firmware überein. Der abgedruckte TH420-Blogtrace zeigt
  dagegen `2..N`; die öffentliche Evidenz ist an dieser Stelle intern
  widersprüchlich.
- Der framebezogene 16-Byte-Read auf EP `0x84` passt strukturell zu ASUS
  `08 81`, beweist aber weder identische Antwortbytes noch Decoderabschluss.
  Ein Hostread nach dem letzten OUT kann eine bereits vor Decoderstart
  bereitgestellte Nachricht abholen. Der aktuelle TH420-Code führt diesen Read
  im Gegensatz zu `ttlcd` und der Blogbeschreibung nicht aus.
- Ein passiver ASUS-Referenzcapture bleibt vor einem eigenen JPEG-Write
  erforderlich: ASUS-Suffix, v49-Folgeindizes, EP-`0x84`-Inhalt/-Timing,
  begleitende Interface-0-/Timeoutbefehle und die reale JPEG-Untermenge sind
  weiterhin ASUS-spezifisch offen.

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

Die nächste Arbeit soll innerhalb der weiterhin passiven Grenze zunächst
`ASUS InfoHub.exe` statisch analysieren:

1. von den belegten SetupAPI-/HID-Imports und Diagnosezeichenketten zu den
   getrennten HID1-/HID2-Handles gehen;
2. deren `WriteFile`-/`ReadFile`-Aufrufer nach 440-, 1024- und 16-Byte-Puffern
   trennen;
3. im 1024-Byte-Zweig den 4+1020-Byte-Builder und erst dort Controlword,
   Segmentindizes, EOI-Suffix und letzte Blockinitialisierung bestimmen;
4. genau einen Schritt rückwärts zu den importierten JPEG-/Framefunktionen aus
   `XYUI.dll` gehen und den 440-Byte-Zweig anschließend auf begleitende
   Controlbefehle eingrenzen;
5. einen passiven Hersteller-Capture erst danach als gezielten Vergleich für
   statisch verbleibende Lücken planen und SPI-, Updater- sowie persistente
   Objektpfade ausgeschlossen halten.

Keine Gerätekommunikation, Emulation oder Firmware-Schreibrechte. Jeder
weitere reale HID-Write benötigt einen neuen ausdrücklich freigegebenen Auftrag.
