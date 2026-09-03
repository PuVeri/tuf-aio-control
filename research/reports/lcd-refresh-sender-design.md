# Kontrollierter hostseitiger LCD-Refreshpfad

Stand: 2026-09-03

## Umfang und Ergebnis

Dieses Ticket implementiert ausschließlich die offline testbare Architektur
für wiederholte vollständige `0x08`-JPEG-Transfers. Es gab keine
Gerätekommunikation, keinen HID-Write und keinen Live-Refresh. Die vorhandene
GUI sendet weiterhin nur genau einen Frame pro Klick; es wurde weder ein
Refreshschalter noch GIF-Live-Animation aktiviert.

Der empirisch bestätigte Einzelframepfad bleibt die einzige
Transportprimitive. `send_frame_once()` validiert und segmentiert weiterhin
genau ein JPEG, öffnet ausschließlich Interface 1, schreibt jedes Segment
einmal und schließt das Handle im `finally`. Das Paketformat, Nullpadding,
fehlende Interface-0-Kommunikation und der Verzicht auf `08 81`-Reads wurden
nicht verändert.

## 1. Architektur

```text
Offline-Bildvorbereitung
  -> unveränderliche RefreshFrame-/RefreshPlan-Daten
  -> explizit gestarteter RefreshController
  -> synchroner FrameSender-Aufruf
  -> optional HidrawFrameSender
  -> bestehendes send_frame_once()
```

### `src/lcd_refresh.py`

Die neue Schicht enthält keinen HID-Opcode, keine Reportbildung und keinen
eigenen Dateideskriptorpfad:

- `RefreshFrame` nimmt unveränderliche JPEG-Bytes auf und validiert sie beim
  Erzeugen mit `lcd_transport.validate_jpeg()` vollständig. Bei Animationen
  trägt es zusätzlich die gewünschte sichtbare Framedauer.
- `RefreshPlan` enthält ein unveränderliches Frame-Tupel sowie drei zwingend
  explizite Grenzen: Transportintervall, maximale Sessiondauer und maximale
  Zahl vollständiger Frames. Es existiert keine Default-Rate.
- `RefreshController` besitzt `start()`, `stop()` und `wait()`. Eine Instanz
  darf genau einmal gestartet werden und läuft auf einem nicht als Daemon
  markierten Thread.
- `FrameSender` ist eine kleine injizierbare Callable-Schnittstelle. Tests
  können daher Zeit und Sender vollständig ersetzen, ohne Discovery,
  `os.open()` oder `os.write()` zu erreichen.
- `HidrawFrameSender` ist nur der zukünftige Adapter zum bestehenden
  `send_frame_once()`. Jeder Frame erhält damit dessen vollständige
  Revalidierung, Nonblocking-Open, Abbruchregeln und `finally`-Close.
- `RefreshResult` hält Stopgrund, Zahl abgeschlossener Frames, gemessene
  Gesamtlaufzeit, jede Transferdauer, gesendete Frameindizes und gegebenenfalls
  den ersten Fehler fest.

Der Controller besitzt keine Framequeue und keine API zum Nachschieben von
Frames. Alle JPEGs stehen validiert im RAM, bevor `start()` überhaupt möglich
ist. Ein Aufruf des Senders muss vollständig zurückkehren, bevor ein weiterer
beginnen kann.

### Erhalt der Einzelframe-Semantik

`send_frame_once()` bleibt öffentlich und wird von CLI und GUI unverändert
genau einmal aufgerufen. Neu ist nur ein prozessweiter Nonblocking-Lock um
seine vollständige Ausführung. Ist bereits ein Frame-Sender aktiv, wird vor
Validierung und Geräteöffnung abgebrochen. Dadurch können Einzelframe- und
Refreshpfad innerhalb desselben Prozesses niemals gleichzeitig schreiben.

Der Refreshcontroller besitzt zusätzlich einen prozessweiten Session-Lock.
Eine zweite Refreshsession wird schon in `start()` abgewiesen, auch während
die erste Session zwischen zwei Frames wartet.

Diese Locks schützen ausschließlich den eigenen Prozess. Vor einem späteren
Live-Test muss zusätzlich ausgeschlossen werden, dass ein anderer Prozess das
LCD-Interface gleichzeitig beschreibt.

## 2. Sicherheitsgrenzen

| Grenze | Implementierung |
| --- | --- |
| Expliziter Start | Nur `RefreshController.start()` erzeugt den Thread; Import oder Konstruktion startet nichts. |
| Expliziter Stop | `stop()` setzt ein Event und joint den Thread. Wartephasen werden sofort unterbrochen. |
| Kein Autostart | Kein CLI-, GUI-, Dienst-, Timer- oder Persistenzeintrag wurde ergänzt. |
| Keine Parallelität | Globaler Refreshsession-Lock plus globaler `send_frame_once()`-Lock. |
| Ein vollständiger Frame gleichzeitig | Senderaufruf ist synchron; kein zweiter Task und keine Framequeue. |
| Erster Fehler beendet | Jede Senderexception oder inkonsistente Writeanzahl erzeugt `SEND_ERROR`; kein weiterer Aufruf. |
| Kein Retry/Recovery | Der Controller wiederholt keinen fehlgeschlagenen Frame, öffnet nicht automatisch neu und ersetzt keinen Fehler durch einen Folgeframe. |
| Handle-Lebensdauer | Der Geräteadapter delegiert pro Frame an `send_frame_once()`, dessen `finally` das Handle immer schließt. |
| Maximale Sessiondauer | Zwingend explizit, hart auf höchstens 60 s begrenzt. |
| Maximale Frameanzahl | Zwingend explizit, hart auf höchstens 500 vollständige Frames begrenzt. |
| Kein Interface 0 | Neue Schicht enthält keine Interfaceauswahl oder Controlwords; der Adapter kennt nur den bestehenden Interface-1-Sender. |
| Kein IN-Read | Weder Controller noch Adapter besitzen eine Readfunktion oder `08 81`-Abhängigkeit. |

Ein Stop kann einen gerade laufenden synchronen Einzelframe nicht mitten im
Segmentstrom abbrechen. Er verhindert den nächsten Frame und beendet nach
Rückkehr beziehungsweise Fehler des laufenden Senders. Das ist absichtlich:
Es gibt höchstens einen in-flight Frame, und ein künstlicher Teilframeabbruch
wäre kein sauberer Recoverymechanismus. Der bestehende Geräteopen verwendet
`O_NONBLOCK`; dennoch ist vor einem Live-Test zu bewerten, welche obere
Transferdauer praktisch akzeptabel ist.

Die maximale Laufzeit wird vor jedem neuen Frame, nach jedem vollständigen
Frame und beim Warten geprüft. Überschreitet ein bereits laufender Transfer
die Deadline, wird er nicht parallel abgebrochen; nach seiner Rückkehr startet
kein weiterer Frame.

## 3. Timingmodell

Die drei Raten sind getrennt:

### A. JPEG-Neuerzeugungsrate

Im Refreshthread ist sie **null**. Alle JPEGs werden vor `start()` offline
erzeugt und validiert. Ein statischer Frame wird byte- und objektidentisch
wiederverwendet. Auch sämtliche vorbereiteten GIF-Frames liegen vor dem Start
als 320x320-JPEGs im RAM.

Eine spätere dynamische Producerpipeline kann getrennt entworfen werden; der
aktuelle Controller besitzt bewusst keine Queue und keine API für laufende
JPEG-Erzeugung.

### B. USB-Übertragungsrate

`transport_interval_seconds` ist eine explizite **minimale Zielperiode
zwischen den Startzeitpunkten zweier vollständiger Senderaufrufe**. Die
Transferdauer wird mit einer injizierbaren monotonen Uhr gemessen und im
Ergebnis gespeichert.

Für Transferstart `S`, Transferende `E` und Intervall `I` gilt:

```text
nächster frühester Start = max(E, S + I)
```

Dauert ein Transfer länger als das Intervall, gibt es keinen parallelen Send
und keinen zusätzlichen Sleep. Der nächste Frame darf erst nach Rückkehr
beginnen. Sein eigener Zeitplan wird auf seinen tatsächlichen Start bezogen;
verpasste alte Deadlines werden nicht nachgeholt. Dadurch entsteht kein
Catch-up-Burst.

Die aus InfoHub bekannte 12-ms-Zielperiode ist **kein Default und keine
Empfehlung** des neuen Codes. Vor einem Live-Test muss ein eigener konservativer
Wert festgelegt werden.

### C. Gewünschte sichtbare Animationsrate

Bei mehreren Frames trägt jedes `RefreshFrame` eine positive
`duration_seconds`. Nach dem erfolgreichen Transfer eines neu gewählten
Frames beginnt dessen gewünschte Sichtdauer. Solange sie nicht abgelaufen ist,
kann der Transport denselben JPEG-Frame gemäß Transportintervall erneut
senden. Danach wird genau zum nächsten Frame im Tupel gewechselt.

Ist Transfer plus Transportintervall langsamer als die gewünschte
Animationsrate, wird die Animation langsamer. Der Controller überspringt keine
Frames, sendet niemals mehrere Frames zum Aufholen und wahrt deshalb immer die
Reihenfolge `0, 1, ..., N-1, 0`.

Die sichtbare Hardware-Framerate bleibt bis zu einem späteren Live-Test
unbekannt. `duration_seconds` beschreibt nur das gewünschte Hostmodell; weder
Decoderabschluss noch tatsächlicher LCD-Commit werden durch den Host gelesen.

## 4. GIF-Vorbereitung

Die bisherige `prepare_image()`- und GUI-Semantik bleibt bestehen: Bei GIF
wird weiterhin nur Frame 0 als Standbild vorbereitet und angezeigt.

Zusätzlich kann `image_pipeline.prepare_gif()` nun offline ein
`PreparedAnimation` erzeugen:

- alle GIF-Frames in Quellreihenfolge;
- originaler ganzzahliger Dauerwert jedes Frames in Millisekunden;
- der von Pillow gelesene Loopwert beziehungsweise `None`, wenn keiner
  vorhanden ist;
- pro Frame ein bereits skaliertes, encodiertes und mit dem bestehenden
  Transportvalidator geprüftes 320x320-SOF0-JFIF-YCbCr-4:2:0-JPEG;
- Quellindex, JPEG-Metadaten und unveränderliche JPEG-Bytes.

Die Offline-Vorbereitung ist auf 500 Frames und insgesamt 64.000.000
Quellpixel über alle Frames begrenzt. Framedauer null wird als Quelldatum
erhalten; sie kann noch nicht direkt als positives Controllerintervall benutzt
werden. Eine spätere GIF-Live-Freigabe muss dafür eine ausdrücklich
dokumentierte Mindestdauerpolitik definieren. Der gespeicherte GIF-Loopwert
wird ebenfalls noch nicht ausgeführt; die Session endet ausschließlich durch
Stop, Fehler, maximale Dauer oder maximale Frameanzahl.

Damit sind Quelldekodierung und Datenmodell vorbereitet, ohne echte
GIF-Live-Animation oder eine GUI-Aktivierung einzuführen.

## 5. Offline-Tests

`tests/test_lcd_refresh.py` deckt ab:

- expliziten Start und interruptiblen Stop;
- Ablehnung einer zweiten parallelen Refreshsession;
- Ablehnung eines parallelen direkten Einzelframe-Senders vor Geräteöffnung;
- sofortigen Stop beim ersten Sender-/Writefehler;
- keine Wiederholung eines fehlgeschlagenen oder unvollständig gemeldeten
  Frames;
- exakte maximale Frameanzahl;
- Stop an der maximalen Laufzeit vor einem weiteren Frame;
- gemessene Transferdauer;
- langsamen Transfer oberhalb des Zielintervalls ohne Überlappung;
- Neubasierung nach einem langsamen Transfer ohne Catch-up-Burst;
- byteidentische Wiederverwendung eines statischen Frames;
- zyklische animierte Reihenfolge ohne Sprung;
- vollständig injizierbaren Geräteadapter.

`tests/test_image_pipeline.py` prüft zusätzlich, dass GIF-Frames,
Durationswerte, Reihenfolge und Loopwert erhalten bleiben und jedes vorbereitete
JPEG den bestehenden Transportvertrag erfüllt.

Die vollständige Suite läuft mit ausschließlich gemockten Geräteoperationen.
Die bereits vorhandenen Tests belegen weiterhin `finally`-Close,
Short-Write-Abbruch, fehlende Retries, exakt eine `os.write()`-Callsite,
Einzelframe-CLI und unveränderte GUI-Einmalaufrufe.

## 6. Voraussetzungen für einen ersten kurzen Refresh-Live-Test

Der Code ist offline bereit, aber ein Live-Refresh ist noch nicht freigegeben.
Vor einem ersten kurzen Test fehlen:

1. ein gesondertes GO/NO-GO-Review für wiederholte vollständige Transfers
   gegen v51-Queue, Decoder-Lease, Transferdauer und das v49-Restunsicherheits-
   modell;
2. eine begründete konservative Transportperiode; 12 ms darf nicht ungeprüft
   aus InfoHub übernommen werden;
3. wesentlich kleinere normative Testgrenzen innerhalb der technischen Caps,
   insbesondere konkrete maximale Dauer und Frameanzahl;
4. Beschränkung des ersten Tests auf ein bereits live bestätigtes statisches
   JPEG, ohne GIF, Framewechsel, Interface 0, Retry oder Recovery;
5. ein ausschließlich explizit erreichbarer Live-Einstieg mit Preview,
   dynamischer Interface-1-Validierung und eindeutiger Nutzerfreigabe;
6. optional ein passiver InfoHub-v49-Capture, um reale vollständige
   Transferabstände vor der Ratenwahl abzugleichen;
7. erneute Prüfung der temporären Schreibberechtigung unmittelbar vor dem
   gesondert autorisierten Test und Entfernung danach;
8. Ausschluss eines konkurrierenden externen LCD-Writers während des Tests.

Bis diese Punkte geschlossen sind, bleibt `lcd_refresh.py` eine nicht in GUI
oder CLI aktivierte, offline getestete Scheduling-Schicht.
