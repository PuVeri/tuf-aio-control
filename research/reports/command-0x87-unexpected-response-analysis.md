# Statische Analyse der unerwarteten `0x87`-Antwort

Stand: 2026-08-05, Europe/Berlin

## Fragestellung und Sicherheitsrahmen

Untersucht wurde ausschließlich anhand vorhandener Quellen, warum der einmalige
reale `0x87`-Test zwar genau 440 Byte empfing, deren Inhalt aber nicht mit

```text
87 01 00 80 51 00 | 434-mal 00
```

übereinstimmte. Es fand keine Gerätekommunikation statt. Das HID-Gerät wurde
nicht geöffnet, es wurden keine Schreibrechte aktiviert und weder Firmware noch
Geräteprotokoll wurden ausgeführt oder emuliert.

Die tatsächlichen Antwortbytes des Tests wurden nicht gespeichert. Deshalb kann
keine der nachstehenden Erklärungen durch einen Vergleich mit diesem Report
bestätigt oder ausgeschlossen werden.

## Untersuchte Quellen

- `src/test_command_0x87.py` und `src/discover_device.py`
- `research/reports/ghidra-static-export-v4.txt`
- `research/reports/ghidra-dispatcher-call-paths.txt`
- `research/reports/ghidra-firmware-map.md`
- `research/reports/command-0x87-safety-review.md`
- `research/ghidra-scripts/ExportFirmwareAnalysis.java`
- `research/ghidra-scripts/ExportDispatcherCallPaths.java`
- extrahierte v51-Firmware mit SHA-256
  `c4679ec340fc5edd3dea960ee027281cf6bd81cbbf347afb40e0d0b4f40aeb9f`
- bereits gesicherter USB-Deskriptor `captures/usb-descriptor-0b05-1c7b.txt`
- Linux-`hidraw`-Dokumentation und -Quellcode:
  [HIDRAW API](https://docs.kernel.org/hid/hidraw.html),
  [HID transport](https://docs.kernel.org/hid/hid-transport.html) und
  [`drivers/hid/hidraw.c`](https://github.com/torvalds/linux/blob/master/drivers/hid/hidraw.c)

Aus der Binärdatei wurden nur zwei gezielte 32-Bit-Literale kontrolliert, kein
vollständiger Rohdump: Die Headermaske bei `0x00129ad4` ist
`0x800000ff`; der Queuezeiger bei `0x00129ad8` ist `0x003b5ee0`.

## Ergebnis in Kurzform

Für die analysierte v51-Firmware ist der normale `0x87`-Antwortbauer
deterministisch. Er erzeugt genau ein 440-Byte-Paket mit dem Header
`87 01 00 80`, legt `51 00` an Offset 4 und 5 ab und lässt alle folgenden
434 Byte null. Weder der gemeinsame Dispatcherprolog noch ein Laufzeitzustand
verschiebt oder verändert diese Bytes in diesem Pfad.

Die bisher als allgemeingültig behandelte Antwort ist jedoch nur für die
analysierte **v51-Firmware** statisch belegt. Der vorhandene USB-Deskriptor des
angeschlossenen Geräts meldete zuvor `bcdDevice 0.49`. Zusammen mit dem
Dateinamen der analysierten v51-Firmware und deren Konstante `0x0051` ist die
kleinste und derzeit stärkste Erklärung, dass `0x87` einen buildabhängigen
Versionswert liefert und das getestete Gerät eine andere Firmware als v51
ausführte. Eine plausible, aber nicht bestätigte v49-Antwort wäre dann
`87 01 00 80 49 00 | 434-mal 00`.

Ein alter oder unabhängiger Report bleibt ebenfalls technisch möglich: Das
Testprogramm prüft die Eingabequeue nach dem Öffnen nicht und liest nach dem
Write genau den ersten verfügbaren Report. Dafür gibt es ohne die verlorenen
Antwortbytes aber keinen positiven Beleg. Insbesondere kann kein Report, der
bereits **vor** dem Öffnen im Linux-`hidraw`-Puffer lag, in den neu angelegten
per-Open-Puffer übernommen worden sein.

## Hostseitiger Ablauf und Queue-Semantik

### Was vor dem Öffnen geschieht

`discover()` liest sysfs-Dateien und fragt optional udev-Metadaten ab. Es öffnet
keinen `hidraw`-Knoten. Erst `_run_once()` öffnet das dynamisch ausgewählte
Interface mit `O_RDWR | O_NONBLOCK`.

Der Linux-Treiber legt bei jedem `hidraw_open()` eine neue, nullinitialisierte
`hidraw_list` mit eigenem Kopf, Ende und Reportpuffer an. Eingehende Reports
werden durch `hidraw_report_event()` in die Puffer aller **zu diesem Zeitpunkt
geöffneten** Leser kopiert. Daraus folgt:

- Ein Report, den Linux vollständig vor diesem `open()` empfangen hatte, kann
  nicht als Altbestand in der neuen per-Open-Queue dieses Programms liegen.
- Ein noch geräteseitig, im USB-Transport oder in der Firmware ausstehender
  Report kann nach dem Öffnen eintreffen und dann in die neue Queue gelangen.
- Ein Report, der nach dem Öffnen durch einen anderen Hostprozess oder
  unabhängig vom `0x87`-Write ausgelöst wird, gelangt ebenfalls in diese Queue.

Die HID-Transportspezifikation beschreibt Inputreports auf dem Interruptkanal
als asynchron; sie dürfen mit oder ohne explizite Anfrage erzeugt werden. Der
`hidraw.read()`-Pfad stellt deshalb von sich aus keine kausale Verbindung zu
einem vorherigen `write()` her.

### Zeitfenster vor dem Write

Nach `os.open()` führt das Programm `_validate_open_target()` aus. Dabei werden
Gerätenummer, sysfs-Identität, Interface und Reportgrößen erneut geprüft. Erst
danach folgt der einzige `os.write()`.

Zwischen `open()` und `write()` gibt es weder `select()` noch `poll()` noch
einen Leseversuch. Ein in diesem Zeitfenster eintreffender Inputreport bleibt
unbemerkt in der per-Open-Queue liegen.

### Welcher Report nach dem Write gelesen wird

Nach dem Write ruft der Code genau einmal `select.select()` und anschließend
genau einmal `os.read(fd, 440)` auf. Linux liefert bei `hidraw_read()` den
Eintrag am Queue-Ende und erhöht dieses danach. Damit liest das Programm den
ältesten für diesen Dateideskriptor noch vorhandenen Report, nicht zwingend den
durch den unmittelbar vorherigen Write verursachten Report.

Das Verhalten des Programms war sicher im Sinne des Einmaltests: Eine
Abweichung führte zum Schließen und nie zu einem weiteren Write. Es war aber
nicht ausreichend, um die Herkunft des einen gelesenen Reports festzustellen.

## Firmwareseitiger Aufbau der v51-Antwort

### Befehlsspezifischer Handler

Der `0x87`-Case bei `0x00127588..0x001275a4`:

1. schreibt das Halbwort `0x0051` auf den lokalen Stack,
2. setzt die Datenlänge auf 2,
3. setzt Präfixzeiger und Präfixlänge auf null,
4. setzt den Antwortbefehl auf `0x87`,
5. ruft den gemeinsamen Antwortbauer bei `0x001298f8` auf.

Der Case liest weder Request-Payload noch befehlsspezifische Globals und besitzt
keine alternative Verzweigung.

### Header und Segmentfeld

Der Antwortbauer nullt zunächst alle 440 Byte. Für zwei Datenbytes und kein
Präfix berechnet er genau ein Paket. Die konstante Maske
`DAT_00129ad4 = 0x800000ff` bewahrt nur Befehlsbyte und First-Packet-Bit; die
Paketanzahl wird in Bits 8 bis 30 eingesetzt. Daraus entsteht das
Little-Endian-Steuerwort:

```text
DWORD 0x80000187 -> Bytes 87 01 00 80
```

Die Bytes `01 00` sind hier die Paketanzahl 1, keine laufende
Transaktionssequenz. Für diese kurze Antwort sind sie nicht zustandsabhängig.
Erst Folgepakete einer längeren Antwort würden an dieser Stelle einen
Segmentindex tragen.

### Position des Antwortwerts

Da die Präfixlänge null ist, kopiert der Builder die beiden Datenbytes an den
Beginn seines 436-Byte-Payloadbereichs. `0x0051` liegt Little Endian daher
zwingend an Reportoffset 4 und 5:

```text
Offset 0..3:    87 01 00 80
Offset 4..5:    51 00
Offset 6..439:  434-mal 00
```

In der analysierten v51-Firmware gibt es im normalen `0x87`-Pfad keine andere
Position für `0x0051`.

### Zustandsabhängigkeit und gemeinsamer Prolog

Der gemeinsame Prolog kann abhängig von Konfigurationsmodus und einem
Initialisierungsflag flüchtige RAM- und Peripheriezustände ändern. Er verändert
aber weder die Argumente des späteren `0x87`-Cases noch die Buildermaske oder
die lokale Konstante `0x0051`.

Alternative Zustände führen in den statisch sichtbaren Pfaden zu einem anderen
Seiteneffekt, zu keiner Zustellung oder zu keiner Antwort, nicht zu einer anders
gebauten `0x87`-Antwort:

- falsches internes Ereignis: Dispatcher lehnt ab, keine `0x87`-Antwort;
- unvollständiger Segmenttransport: Handler wird nicht erreicht;
- volle Antwortqueue: Paket wird nicht eingereiht, erwartbarer Hosttimeout;
- dauerhaft beschäftigter USB-Controller: Verzögerung oder Timeout.

Der gemeinsame Prolog erklärt daher keine inhaltlich andere 440-Byte-Antwort.

## Gemeinsamer IN-Pfad und unabhängige Antworttypen

Der Antwortbauer ist nicht exklusiv für `0x87`. Der Gerätedispatcher verwendet
ihn unter anderem für `0x0d`, `0x1e` und `0x80` bis `0x87`; zusätzlich erzeugt
der Transportdispatcher bei Ereignis `0x3b` darüber einen `0xff`-Report. Alle
Aufrufe verwenden denselben Builder und dessen Queueobjekt bei `0x003b5ee0`.
Die vorhandenen Ghidra-Endpointberichte ordnen diesen 440-Byte-Antwortpfad
Interface 0 und `0x82` IN zu.

Damit können verschiedene 440-Byte-Antworttypen über denselben IN-Endpunkt
laufen. Der Headerbefehl unterscheidet sie, aber der USB-/`hidraw`-Transport
enthält keine Anfrage-ID und korreliert sie nicht mit dem zuletzt ausgeführten
Userspace-Write.

Die Firmware besitzt eine gemeinsam genutzte, gepufferte Antwortstruktur. Ein
noch ausstehender Inhalt aus einem früheren oder parallelen Ablauf ist daher
statisch plausibel. Ob beim Live-Test tatsächlich ein solcher Inhalt vorhanden
war, ist nicht beobachtet. Die exakte Laufzeitbelegung und zeitliche Herkunft
der damaligen Firmwarequeue lassen sich offline nicht rekonstruieren.

## Gewichtung der Erklärungen

### 1. Andere laufende Firmwareversion – derzeit stärkste Erklärung

Die analysierte Binärdatei stammt aus dem offiziellen v51-Paket und enthält im
`0x87`-Case `0x0051`. Der zuvor am Gerät erfasste USB-Deskriptor meldet dagegen
`bcdDevice 0.49`. Da `0x87` bereits als Versionsabfragekandidat bewertet wurde,
passt eine buildabhängige Konstante am besten zu beiden statischen Befunden.

Diese Schlussfolgerung ist eine starke Inferenz, keine Bestätigung: Weder ist
die Semantik von `0x87` durch einen gespeicherten Laufzeitreport bewiesen, noch
wurde `bcdDevice` zum exakten Testzeitpunkt erneut protokolliert. Ohne die
Antwortbytes kann insbesondere `49 00` an Offset 4/5 nicht nachgewiesen werden.

### 2. Alter oder unabhängiger Report – technisch plausibel, nicht belegt

Die fehlende Vorabprüfung erlaubt, dass nach dem Öffnen und vor dem Write ein
Report in der Hostqueue ankommt. Ebenso kann ein schon geräteseitig ausstehender
oder durch einen parallelen Ablauf erzeugter Report zuerst eintreffen. Das
Programm würde genau diesen ältesten Report lesen.

Gegen eine stärkere Aussage spricht, dass keine unerwarteten Bytes vorliegen.
Es ist daher nicht erkennbar, ob das Befehlsbyte von `0x87` abwich oder nur der
vermutliche Versionswert. Ein Report aus der Hostqueue **vor** `open()` ist
durch die per-Open-Implementierung ausgeschlossen; nur ein nach `open()`
zugestellter Alt-/Fremdreport bleibt möglich.

### 3. Falsche Byteposition oder zustandsabhängiger v51-Builder – statisch
unwahrscheinlich

Headerformel, Maske, Länge, Präfixlänge und Kopierziel sind für den betrachteten
v51-Pfad eindeutig. Weder eine andere Position von `0x0051` noch ein
zustandsabhängiger Header ist darin sichtbar. Eine abweichende Firmwareversion,
ein anderer Betriebsmodus oder ein Firmwarefehler liegen außerhalb dieses
Belegs.

## Folgerung für die erwartete Antwortstruktur

Die bisherige exakte Folge bleibt als **v51-spezifische statische Erwartung**
korrekt:

```text
v51: 87 01 00 80 51 00 | 434-mal 00
```

Sie darf nicht mehr ohne vorherigen Firmwarebeleg als universelle Antwort des
angeschlossenen Geräts bezeichnet werden. Als noch unbestätigte
versionsübergreifende Hypothese bietet sich an:

```text
87 01 00 80 VV 00 | 434-mal 00
```

Dabei ist `VV=51` nur für die analysierte v51-Binärdatei belegt. `VV=49` für
das zuvor mit `bcdDevice 0.49` beobachtete Gerät ist plausibel, aber nicht
bestätigt. Das Testprogramm soll eine abweichende Antwort weiterhin sicher als
unerwartet behandeln; eine Lockerung des Erfolgsvergleichs wäre ohne neue
Evidenz nicht gerechtfertigt.

## Erforderliche rein lesende Vorprüfungen vor einem möglichen späteren Test

Vor jeder neuen Erwägung eines Schreibtests wären mindestens folgende
getrennte, rein lesende Schritte erforderlich:

1. Geräteidentität, Seriennummer, `bcdDevice`, Interface 0 und Reportdeskriptor
   unmittelbar vor dem Test erneut erfassen und protokollieren.
2. Interface 0 in einem eigenen, zeitlich begrenzten `O_RDONLY`-Lauf während
   eines normalen Ruhezustands beobachten. Jeder spontane 440-Byte-Report ist
   als Beleg für einen nicht exklusiven Antwortstrom zu dokumentieren.
3. Prüfen, ob andere Prozesse den betreffenden `hidraw`-Knoten geöffnet haben.
   Eine parallele Nutzung verhindert eine eindeutige Zuordnung.
4. In einer späteren Einmaltest-Implementierung **nach** Öffnen des endgültigen
   Dateideskriptors und **vor** jedem Write eine begrenzte Readiness-/Quiet-
   Window-Prüfung durchführen. Ist der Deskriptor lesbar, muss der Test ohne
   Write schließen und abbrechen.
5. Einen vorhandenen Report nicht automatisch leeren und anschließend trotzdem
   schreiben. Drain-and-continue würde die Ursache verdecken und kann nicht
   garantieren, dass die Gerätequeue leer ist.
6. Nach dem Write weiterhin höchstens einen Report lesen. Einen fremden Report
   automatisch zu überspringen würde zusätzliche Reads und eine neue, bisher
   nicht abgesicherte Korrelationslogik einführen.

Ein ruhiges Zeitfenster kann Queuekontamination nur reduzieren, nicht
mathematisch ausschließen: Ein unabhängiger Report kann unmittelbar danach
eintreffen. Solange das Protokoll keine Transaktionskennung enthält, bleibt der
Headerbefehl die einzige sichtbare semantische Zuordnung.

## Abschlussbewertung

- **Wahrscheinlichste Erklärung:** Das Gerät lief vermutlich nicht mit der
  analysierten v51-Firmware; `bcdDevice 0.49` und die v51-Konstante `0x0051`
  sprechen für einen versionsabhängigen Antwortwert.
- **Alter oder unabhängiger Report:** möglich, weil die Einmaltest-
  Implementierung keine Pre-Write-Readiness prüft und danach den ältesten
  verfügbaren Report liest; anhand der vorhandenen Evidenz aber nicht als
  wahrscheinlich bestätigt.
- **Korrektur der Erwartung:** Die exakte Antwort ist für v51 korrekt, aber
  nicht als versionsunabhängige Laufzeiterwartung belegt. Die variable
  Versionsstruktur bleibt bis zu passiver oder anderweitig autorisierter
  Bestätigung eine Hypothese.
- **Weiterer Test:** derzeit nicht vertretbar. Zuerst sind der Firmwarestand und
  das Auftreten spontaner Interface-0-Reports rein lesend zu klären und die
  Pre-Write-Abbruchprüfung separat zu entwerfen und zu prüfen. Der fehlende
  Rohreport allein ist kein Wiederholungsgrund.

Während dieser Analyse wurde nichts an das Gerät gesendet.
