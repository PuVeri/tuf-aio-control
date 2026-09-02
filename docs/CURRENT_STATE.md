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
  Dieser statische Befund allein bewies JPEG nur für gespeicherte Objekte;
  der spätere reale Einmaltest bestätigt JPEG zusätzlich für den getesteten
  USB-`0x08`-Erfolgsfall.
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
  JPEG-Pfad benutzt. Die statische Analyse allein ließ JPEG für die
  USB-`0x08`-Quelle offen; der spätere Einmaltest bestätigt es für genau die
  getestete Referenzdatei und Segmentfolge.
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
- Zum damaligen Analysestand war ein eigener JPEG-Live-Test noch nicht
  freigabereif. Hostframing, Nullpadding und die konservative JPEG-Untermenge
  wurden danach geschlossen; die v51/v49-Differenz wurde im abschließenden
  Readiness-Review als eng abgegrenztes Versionsrestrisiko bewertet.

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
  Nullbyte. Der reale Einmaltest bestätigt dieses Framing jetzt für Interface
  1. InfoHub bestätigt unabhängig davon die Windows-Abbildung: `WriteFile`
  erhält `00 || report[1024]`, also 1025 API-Byte. Interface-1-Reads liefern
  den unnummerierten 16-Byte-IN-Report ohne Nullpräfix; InfoHub und der
  erfolgreiche Einmaltest führen einen solchen Read jedoch nicht aus.
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
  konkreten Suffix. Der inzwischen extrahierte Hostproducer belegt für ASUS
  ausschließlich Nullbytes nach EOI bis zum Ende des letzten Blocks.
- Ein späterer passiver Capture soll weiterhin beide Interfaces vollständig
  und mit URB-Zeitstempeln erfassen. Suffix, Folgeindizes und fehlender
  Host-IN-Read sind für den Einmaltest auch empirisch bestätigt; offen bleiben
  besonders v49/v51-Gleichheit, der konkrete GDI+-JPEG-SOF-/Subsampling-
  Output und der genaue Commitzeitpunkt. Dass ein sichtbarer Commit erfolgt,
  ist für die Referenzdatei bestätigt.
- Zum Zeitpunkt dieser Analyse waren v49/v51-Gleichheit, Codec-Untermenge und
  fehlender Decoder-Done-Status noch Blocker. Die Codec-Untermenge und der
  ASUS-Hostpfad sind inzwischen ausreichend eingegrenzt; `08 81` bleibt nur
  Queueannahme/Start und wurde im ersten Test weder gelesen noch als
  Done-Status verwendet.

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
- Der Sender ist inzwischen in
  `research/reports/asus-infohub-lcd-sender-analysis.md` vollständig statisch
  rekonstruiert. Die reproduzierbaren read-only Exporte sind
  `research/ghidra-scripts/ExportInfoHubLcdSender.java` und
  `research/ghidra-scripts/ExportInfoHubXyuiJpeg.java`.

## Statische InfoHub-LCD-Senderanalyse

- HID1/Interface 0 und HID2/Interface 1 werden nach Windows-
  `OutputReportByteLength` 441 beziehungsweise 1025 unterschieden, nicht nach
  der zwar geparsten, aber bei der Auswahl unbenutzten `&mi_`-Nummer.
- Der JPEG-Builder `ASUS InfoHub.exe:0x00416bc0` berechnet
  `N=ceil(JPEG-Länge/1020)`, sendet `08 N 00 80` und danach
  `08 i 00 00` für `i=1..N-1`. Er nutzt nur das Low-Byte von Anzahl/Index,
  kopiert immer 1020 Payloadbytes und übergibt pro Segment
  `00 || report[1024]` als 1025-Byte-Windows-HID-Puffer.
- `XYUI::LEDModeCtrl::GetLEDData` nullt den gesamten 409.600-Byte-Zielpuffer,
  kopiert die exakten JPEG-Bytes hinein und gibt die vorher über
  `IStream::Stat` bestimmte Länge zurück. Daher besteht jedes Byte nach EOI
  im letzten Vollblock konkret aus `00`.
- Das Nutzerbild wird nicht unverändert übertragen. XYUI rendert einen neuen
  320×320-Frame und encodiert ihn mit dem anhand `image/jpeg` ausgewählten
  GDI+-Encoder. Einziger Encoderparameter ist Qualität 60 für Modus 1/7,
  sonst 90. SOF-Typ und Subsampling werden nicht explizit gewählt.
- Nach dem letzten erfolgreichen Bildsegment endet der Sender ohne Read.
  InfoHub verwendet weder den 16-Byte-IN-Pfad noch `08 81`, hat keinen
  Antworttimeout und lässt den weiteren Ablauf nicht von Interface-1-IN
  abhängen.
- Zum erfolgreichen Transfer gehört kein Interface-0-Befehl. Insbesondere
  sendet dieser Hostpfad weder `0x19` noch ein Befehlsbyte `0x80..0x87` und
  ändert `config+0x108` nicht. Separate Hostaktionen senden `0x10`, `0x12`
  oder `0x1f`; `FF 01 00 00` erscheint nur nach zwei fehlgeschlagenen
  HID2-Writes.

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
  nullinitialisierten 1020-Byte-Nutzblock. InfoHub bestätigt diese Regel nun
  unmittelbar: `GetLEDData` nullt den Gesamtpuffer vor dem Kopieren des JPEG,
  und der Sender kopiert jeden Payload vollständig. Ein ASUS-v49-Transfer
  selbst ist weiterhin nicht beobachtet.
- Beide veröffentlichten Sender verwenden Folgeindizes `1..N-1` und stimmen
  damit mit der ASUS-v51-Firmware überein. Der abgedruckte TH420-Blogtrace zeigt
  dagegen `2..N`; die öffentliche Evidenz ist an dieser Stelle intern
  widersprüchlich.
- Der framebezogene 16-Byte-Read auf EP `0x84` passt strukturell zu ASUS
  `08 81`, beweist aber weder identische Antwortbytes noch Decoderabschluss.
  Ein Hostread nach dem letzten OUT kann eine bereits vor Decoderstart
  bereitgestellte Nachricht abholen. Der aktuelle TH420-Code führt diesen Read
  im Gegensatz zu `ttlcd` und der Blogbeschreibung nicht aus.
- Ein passiver ASUS-Referenzcapture bleibt wertvolle zusätzliche v49- und
  Laufzeitevidenz, ist nach dem abschließenden statischen Readiness-Review aber
  kein technischer Blocker für genau einen minimalen, gesondert freizugebenden
  JPEG-Test. Offen bleiben die bytegenaue v49-Gleichheit und der sichtbare
  Commitzeitpunkt.

## Abschließender statischer JPEG-Test-Readiness-Review

Der Abschlussbericht steht in
`research/reports/lcd-first-jpeg-test-readiness.md`.

- **GO** für die technische Spezifikation genau eines späteren minimalen
  Interface-1-`0x08`-JPEG-Transfers; dies ist keine Freigabe für einen
  HID-Write.
- Der Erfolgsweg besteht aus genau `N=ceil(L/1020)` Linux-hidraw-Writes mit
  je 1025 API-Byte, keinem Retry, keinem Interface-0-Zugriff, keinem
  Interface-1-IN-Read, keinen weiteren Commands und keinem zweiten Frame.
- Das JPEG wird offline eingefroren und validiert: 320×320, SOF0, 8 Bit,
  JFIF-YCbCr 4:2:0, Standard-Huffman, Qualität 60, einfache achromatische
  Grafik, SOI/EOI, ausschließlich Nullpadding und für den Minimaltest `N<=4`.
- v51 erreicht im `0x08`-Pfad weder SPI-/Flash-Write, Firmwareupdate,
  Bootloader noch persistente Konfigurationsänderung. Für das reale, sehr
  wahrscheinlich v49-basierte Gerät bleibt dies mangels v49-Binärdatei formal
  unbekannt; es gibt keinen positiven Hinweis auf eine persistente Kante.
- Temporärer Fehler, USB-/Displayhänger und Replug-/Neustartbedarf sind jeweils
  **niedrig** eingestuft; persistente Beschädigung **sehr niedrig**.
- Eine fünfsekündige Quiet-Phase liefert ohne auszuwertenden IN-Report keinen
  belegten Sicherheitsgewinn. Maßgeblich sind bekannter Gerätezustand,
  Ausschluss paralleler Writer, vollständig vorvalidierte Puffer, kein Retry
  und kein zweiter Frame.

## Offline-Werkzeug für den ersten JPEG-Test

`src/test_jpeg_0x08.py` und die Bedienungs-/Sicherheitsdokumentation
`docs/JPEG_0X08_TEST.md` implementierten den geplanten Einmalpfad. Der später
gesondert freigegebene Live-Test ist in
`research/reports/lcd-0x08-live-test-01.md` dokumentiert.

- Standardlauf und `--dry-run` validieren genau eine explizite JPEG-Datei,
  bauen sämtliche Pakete offline und öffnen keinen hidraw-Knoten.
- Der Markerparser verlangt SOI/EOI, JFIF, SOF0, 8 Bit, exakt 320×320, drei
  Komponenten, konservatives YCbCr 4:2:0, einen Baseline-Scan, die vier
  bytegenau geprüften Standard-Huffmantabellen, gültige 8-Bit-DQT-Tabellen 0/1
  und `1 <= N <= 4`. SOF1/SOF2, andere SOF-Typen, zusätzliche APP-/
  Metadatensegmente, Restartintervalle, arithmetische Codierung und Bytes nach
  EOI werden abgelehnt. Die Eingabe muss eine reguläre Datei sein.
- Die reinen Paketfunktionen erzeugen `08 N 00 80` und danach
  `08 i 00 00`, füllen ausschließlich mit Nullbytes auf 1020 Payloadbyte auf
  und stellen jedem 1024-Byte-Drahtreport genau ein hidraw-Nullbyte voran.
- Der spätere Livepfad ist nur über `--i-understand-the-risk` erreichbar,
  besitzt genau eine `os.write()`-Quelltextstelle und prüft vor jedem Write
  VID/PID, Interface 1, Zeichengerät/sysfs-Zuordnung, 1024-Byte-OUT-Report und
  fehlende Report-ID erneut. Exception oder Rückgabewert ungleich 1025 führt
  sofort zum Close ohne weiteren Write.
- Es existieren keine Auswahl anderer Commands, kein Interface-0-Pfad, kein
  Read, Retry, Recovery-Command oder zweiter Frame.
- 37 Offline-Tests prüfen unter anderem `N=1/2/4`, Padding, Controlwords,
  1025-Byte-Framing, JPEG-Ablehnungen, Referenzhash, Dry-Run ohne `os.open()`
  sowie Abbruch ohne Retry bei Short Write und Write-Exception. Ein Fehler im
  zweiten Segment nach einem erfolgreichen ersten Segment verhindert
  nachweislich alle verbleibenden Writes.

Das eingefrorene Referenzbild liegt unter
`tests/fixtures/lcd-0x08-reference.jpg`. Es wurde lokal mit ImageMagick
7.1.2-27/libjpeg-turbo 3.1.3 ohne Paketinstallation erzeugt und besitzt:

```text
SHA-256: 5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866
L:       2236 Byte
N:       3
Padding: 824 Byte
```

Der Validator bestätigt offline 320×320, SOF0, 8 Bit, drei Komponenten und
4:2:0. Während der Implementierung wurde die Datei nicht gesendet; im später
gesondert autorisierten Live-Test wurde sie genau einmal übertragen.

## Statischer Safety- und Correctness-Code-Review

Der unabhängige Review steht in
`research/reports/test-jpeg-0x08-code-review.md` und endete nach begrenzten
Korrekturen mit **PASS**.

Gefunden und korrigiert wurden:

- unvollständiges `JFIF\0` konnte zuvor als APP0 genügen;
- referenzierte Quantisierungstabellen wurden zuvor nicht verlangt;
- zusätzliche APP-/unbekannte Headersegmente wurden zuvor übersprungen;
- der Risikoschalter war durch das argparse-Standardverhalten abkürzbar;
- die JPEG-Eingabe war nicht ausdrücklich auf reguläre Dateien begrenzt.

Der Parser verlangt nun einen vollständigen JFIF-Header ohne Thumbnail, DQT 0
und 1, eine feste Marker-Allowlist und den vollständig ausgeschriebenen
Risikoparameter. AST- und Callgraphprüfung bestätigen genau eine
`os.write()`-Callsite in `_run_once()`, ausschließlich aufgerufen von `main()`.
Pro Prozesslauf sind maximal vier Writes erreichbar; es gibt keinen Retry,
Reconnect, Recovery-Write, zweiten Frame oder Interface-0-Pfad.

Die Referenzdatei wurde unabhängig mit `file`, FFmpeg und ImageMagick als
Baseline-JFIF, 320×320, 8 Bit, drei Komponenten und 4:2:0 bestätigt. Der
rekonstruierte Payload besitzt denselben SHA-256 wie die Quelldatei und exakt
824 Nullbytes Nachlauf. Keine Gerätekommunikation fand statt.

## Erster realer `0x08`-JPEG-Live-Test

Der gesondert autorisierte Einmaltest ist unter
`research/reports/lcd-0x08-live-test-01.md` dokumentiert. Das reale Gerät mit
VID:PID `0b05:1c7b`, Versionswert `0x0049` und `bcdDevice 0.49` wurde über
Interface 1 angesprochen; `/dev/hidraw8` war lediglich die dynamische
Zuordnung während dieses Boots.

Gesendet wurde ausschließlich die eingefrorene 2236-Byte-Referenzdatei mit
SHA-256
`5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866`.
Die drei 1025-Byte-hidraw-Puffer trugen `00 || 1024-Byte-Report` und die
Controlwords `08 03 00 80`, `08 01 00 00`, `08 02 00 00`. Der letzte Payload
enthielt nach den verbleibenden 196 JPEG-Bytes exakt 824 Nullbytes. Es gab
keinen Retry, keine Interface-0-Kommunikation, keinen Endpoint-`0x84`-Read,
keinen weiteren Command und keinen zweiten Frame.

Auf dem LCD erschien sichtbar das erwartete weiße Quadrat. Damit sind auf dem
realen Gerät für genau diesen Erfolgsfall empirisch bestätigt:

- Interface 1 als Bildkanal;
- Linux-hidraw-Framing `00 || 1024`;
- der `0x08`-JPEG-Transfer mit `N=3` und Folgeindizes 1, 2;
- Nullpadding nach EOI;
- JPEG-Dekodierung und sichtbarer Displaycommit;
- Erfolg ohne Interface-0-Begleitbefehl und ohne Endpoint-`0x84`-Read.

Nur aus v51 statisch bekannt bleiben die internen Queuegrenzen, Decoder-Lease,
Decoderstart- und Queuefreigabepfade sowie die fehlende Erreichbarkeit
persistenter Schreibpfade. Die bytegenaue Identität des realen Binärstands mit
einer offiziellen v49-Datei ist weiterhin nicht belegt.

Der Einzeltest erlaubt ausdrücklich keine Aussage über Animationen, mehrere
Frames, langfristigen Dauerbetrieb, Fehlerverhalten oder andere JPEG-Profile.
Temporäre Schreibrechte wurden unmittelbar nach dem Test wieder entfernt; in
dieser Dokumentationsarbeit fand keine weitere Gerätekommunikation statt.

## Wiederverwendbarer Einzelbild-Sender

Der empirisch bestätigte Pfad ist jetzt ohne Protokollerweiterung in eine
kleine wiederverwendbare Modulstruktur überführt:

- `src/lcd_transport.py`: dynamische Erkennung von `0b05:1c7b`/Interface 1,
  JPEG-Validierung, reine Paketbildung und exakt einmaliger synchroner
  Frame-Transfer;
- `src/set_lcd_image.py`: allgemeine Einzelbild-CLI, standardmäßig nur
  Preview; ein Transfer ist ausschließlich über `--apply` erreichbar;
- `src/test_jpeg_0x08.py`: funktional gleichwertiges konservatives
  Safety-Werkzeug auf denselben Kernfunktionen, weiterhin hart auf `N<=4`
  begrenzt.

Der refaktorierte Pfad `src/set_lcd_image.py --apply` wurde inzwischen genau
einmal erfolgreich auf dem realen Gerät mit Versionswert `0x0049` und
`bcdDevice 0.49` ausgeführt. Damit ist neben dem ursprünglichen Safety-Werkzeug
auch die wiederverwendbare Transport-/CLI-Schichtung für einen einzelnen Frame
empirisch bestätigt. Daraus folgt keine Freigabe für weitere Frames,
Animationen oder Dauerbetrieb.

Die Produktstufe akzeptiert nur bereits passende 320×320-SOF0-/Baseline-
JFIF-YCbCr-4:2:0-JPEGs mit 8 Bit, drei Komponenten, Standard-Huffmantabellen,
gültigem EOI ohne Nachlauf und `1<=N<=200`. Eine automatische Konvertierung
existiert nicht. Der Linux-Puffer bleibt exakt `00 || 1024-Byte-Report`; der
letzte Payload wird ausschließlich mit Nullbytes aufgefüllt.

Der gesamte neue JPEG-Senderpfad besitzt genau eine `os.write()`-Callsite in
`send_frame_once()`. Ein Aufruf überträgt höchstens einen Frame und maximal
200 Segmente. Bei der ersten Revalidierungsabweichung, Write-Exception oder
einem Short Write wird ohne Retry und ohne weitere Writes geschlossen. Es
gibt keinen Interface-0- oder IN-Read-Pfad, keine anderen Commands, keine
Recovery, keinen Reconnect, keine Animation und keinen Hintergrunddienst.

48 Offline-Tests bestätigen unter anderem `N=1/2/3/4`, größere gültige Werte
bis `N=200`, Nullpadding, Geräte-/Reportablehnungen, Abbruch bei Writefehlern,
Preview ohne Geräteöffnung und genau einen Frame-Aufruf pro CLI-Lauf. Während
dieses Tickets fand keine Gerätekommunikation statt. Bedienung und Grenzen
stehen in `docs/LCD_SINGLE_IMAGE.md`.

## Erste Desktop-UI

`src/tuf_aio_gui.py` implementiert die erste native Desktop-Oberfläche mit dem
bereits lokal vorhandenen PySide6 6.11.1. GUI und Transport bleiben getrennt:
Die Oberfläche enthält keine Controlwords, HID-Paketbildung oder eigene
Geräteöffnung, sondern verwendet ausschließlich `lcd_transport.py`.

Die dunkle, layoutbasierte Oberfläche zeigt den dynamisch erkannten
Gerätestatus, eine Bildvorschau, Pfad, Auflösung, JPEG-Profil, Dateigröße,
Segmentzahl, Padding und Validierungsstatus. Bereits kompatible JPEGs können
erst nach einem expliziten Klick auf `Auf Display senden` übertragen werden.
Inkompatible, von Qt darstellbare Bilder bleiben als Preview sichtbar, der
Sendebutton ist dann deaktiviert und der Validierungsfehler wird angezeigt.
Eine automatische Bildkonvertierung existiert weiterhin nicht.

Vor jedem Klicktransfer liest und validiert die GUI die Datei erneut und führt
die dynamische Geräteerkennung erneut aus. Danach ruft sie
`send_frame_once()` genau einmal auf; dessen VID/PID-, Interface-, Report- und
Per-Write-Revalidierungen bleiben unverändert. Es gibt kein automatisches
Senden, Retry, Reconnect, Polling-Write, IN-Read, Interface 0, Folgeframe,
Animation, Autostart oder Hintergrunddienst.

Die gesamte Offline-Suite umfasst jetzt 53 erfolgreiche Tests. Fünf
headless-Qt-Tests prüfen Referenzbild, inkompatible Preview, fehlendes Gerät,
Transportfehler ohne Retry und genau einen `send_frame_once()`-Aufruf pro
Sendeklick. Alle Geräteoperationen sind gemockt; während dieses GUI-Tickets
fand keine Gerätekommunikation statt und die Referenzdatei wurde nicht
gesendet.

## Gefährliche und ausgeschlossene Pfade

- `0x88`: SPI-Lesen und bedingtes SPI-Schreiben bei `0x21000`.
- `0x0a..0x0d`: Objekt-/Blocktransfer mit indirekten Backends; persistente
  Schreibziele sind nicht ausgeschlossen.
- `0x1b`, `0x1c`, `0xfe`: persistenznaher Konfigurationspfad `0x00126814`.
- `0x1f`: Modusmutation und möglicher Bootcallback.
- `0x09`: Displaymutation; im Updater zusätzlich Completion-Flag.
- `0x86`: Firmwareblocktransfer; `0x02`: Updater-Abschluss/Reenumeration.
- `0x45`: Konfigurationslöschung im Updater.
- `0xff` mit Payload-DWORD 1: InfoHub verwendet ihn als HID2-Transferfehler-
  Benachrichtigung; die Wirkung des indirekten Gerätecallbacks bleibt
  unaufgelöst.

## Nächster klarer Arbeitsschritt

Der freigegebene Einmaltransfer ist abgeschlossen und dokumentiert. Ein
weiterer Frame, Animationen, Dauerbetrieb, Fehlerpfadtests oder andere
JPEG-Profile sind weder aus dem Ergebnis ableitbar noch freigegeben. Jede
solche Erweiterung benötigt eine neue, eigenständige Sicherheitsbewertung und
ausdrückliche Autorisierung. Vor automatischer Bildkonvertierung müssen
Skalierung/Crop, Farbraum, 4:2:0-Sampling, Baseline-Encoderparameter,
Qualitäts-/Größengrenzen und die erneute Ausgangsvalidierung deterministisch
festgelegt und offline getestet werden. Schreibrechte bleiben deaktiviert.
Ein passiver ASUS-Referenzcapture bleibt optional zusätzliche Evidenz.
