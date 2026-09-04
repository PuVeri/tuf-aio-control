# Kontinuierlicher LCD-Dauerbetrieb

Datum: 2026-09-04

## Ziel und Sicherheitsgrenze

Der normale GUI-Produktionspfad betreibt genau eine ausdrücklich durch
`LCD starten` ausgelöste Refreshsession nun ohne Zeit- oder Frame-Hardcap. Die
Session endet ausschließlich durch `LCD stoppen`, einen sauberen
Fensterschluss oder den ersten Fehler. Es gibt keinen Autostart, automatischen
Neustart, Retry oder Reconnect.

Dieses Ticket wurde vollständig offline umgesetzt und geprüft. Es gab keine
Gerätekommunikation, kein hidraw-Open, keine HID-/USB-Writes und keinen
Live-Test. `lcd_transport.py` und das bestätigte Interface-1-`0x08`-Protokoll
wurden nicht verändert.

## Session- und Refreshpolitik

`ProductionControllerFactory` erzeugt für die normale GUI jetzt einen
Einframeplan mit 1,0 s zwischen Frame-Startzeitpunkten und ohne automatische
Laufzeit- oder Framegrenze. Das bisherige 30-s-/30-Frame-Entwicklungsprofil
bleibt separat für begrenzte Offline-Tests verfügbar und begrenzt die
Produktionssession nicht mehr. Auch das feste Fünfframeprofil des ersten
Live-Refreshwerkzeugs bleibt unverändert.

Der synchrone Sender verhindert überlappende Transfers. Der nächste Start wird
vom Startzeitpunkt des vorherigen Frames berechnet; bei einer längeren
Übertragung beginnt er erst nach deren Abschluss. Dadurch entstehen weder
Catch-up-Bursts noch eine Framequeue. Die real gemessenen ungefähr 108–109 ms
Transferdauer liegen deutlich innerhalb des konservativen 1,0-s-Intervalls.

Der Worker verwendet pro Takt ausschließlich den letzten vollständig
validierten, unveränderlichen Snapshot aus `LatestFrameBuffer`. Sensoren,
hwmon und `/proc/stat` werden weiterhin nur im GUI-Thread gelesen.

## Start, Stop und Shutdown

`LCD starten` ist nur im GUI-State `idle`, mit vorhandenem validiertem Frame,
read-only erkanntem Gerät und vorhandener Produktions-Factory aktiv. Der Klick
erzeugt genau einen sessionspezifischen Framepuffer, durchläuft die bestehenden
Production-Safety-Gates und startet genau einen Worker. Prozessweite
Controller- und Transportlocks verhindern eine zweite parallele Session oder
einen zweiten Sender.

`LCD stoppen` ruft nicht blockierend `request_stop()` auf. Vor einem neuen
Transfer prüft der Worker die Stopanforderung erneut. Ein bereits laufender
synchroner Frame darf vollständig enden; `send_frame_once()` schließt sein
Handle weiterhin im bestehenden `finally`. Danach endet der Worker und die GUI
kehrt nach `idle` zurück.

Beim Schließen während `running` wird derselbe Stop angefordert und das erste
Close-Ereignis abgelehnt. Die Qt-Ereignisschleife bleibt responsiv. Erst nach
dem terminalen Workergebnis wird das Fenster erneut geschlossen. Während
`stopping` beginnen keine dynamischen Publikationen und keine neue Session.

## Fehlerverhalten

Der erste Transportfehler beendet den Controller mit `send-error`. Es folgen
kein Retry, Reconnect, Recovery-Transfer oder automatischer Neustart. Die GUI
wechselt mit einer verständlichen Meldung nach `error`; erst
`Fehler bestätigen` ermöglicht bewusst eine spätere neue Session.

Ein fehlgeschlagener Transfer verändert den letzten gültigen
`LatestFrameBuffer`-Snapshot nicht. Der bestehende Sender schließt ein geöffnetes
Handle auch im Fehlerfall, der Worker endet terminal und die Diagnose erfasst
Fehlerphase, Stopgrund, Workerende und Handle-Close-Status.

## Hardwarefreigabe und Safety-Gates

Die redundante sichtbare Entwicklungscheckbox
`Hardware-Livebetrieb freigeben` wurde entfernt. `LCD starten` ist nun selbst
die ausdrückliche Benutzeraktion. Es gibt weiterhin keinen Autostart.

Unverändert vorgeschaltet bleiben alle Production-Safety-Gates:

- VID/PID exakt `0b05:1c7b`;
- ausschließlich Interface 1;
- `bcdDevice` exakt `0x0049`;
- Usage Page/Usage `0xff06/0x01`;
- unnummerierter Input-Report mit 16 Byte und Output-Report mit 1024 Byte;
- keine Feature-Reports;
- bekanntes HID-Klassen-, Alternate-Setting- und Endpointprofil;
- absoluter, dynamisch entdeckter `/dev/hidraw*`-Pfad;
- kein lokal in `/proc` erkennbarer konkurrierender Writer.

## Vier weiter außen liegende Telemetrieslots

Schriftart, Schriftgröße, Schriftgewicht, Farbe und Metric-Modell bleiben
unverändert. Ausschließlich die symmetrischen Positionen wurden verschoben:

| Slot | Labelmittelpunkt | Wertmittelpunkt |
| --- | --- | --- |
| oben links | `(102, 73)` | `(102, 105)` |
| oben rechts | `(218, 73)` | `(218, 105)` |
| unten links | `(102, 215)` | `(102, 247)` |
| unten rechts | `(218, 215)` | `(218, 247)` |

Gegenüber `x=108/212` wuchs der Spaltenabstand von 104 auf 116 Pixel. Der
entsprechende Zeilenabstand wuchs von 132 auf 142 Pixel. Tests setzen jede
verfügbare Metric einschließlich der längeren Labels und der Wertebereiche
N/A, 0 und 100 in jeden Slot ein. Alle gemessenen Textgrenzen bleiben
überlappungsfrei innerhalb der rechteckigen Sicherheitsgrenze und des runden
Sicherheitsradius von 148 Pixeln.

Die Renderreihenfolge bleibt unverändert: Basisbild, vier Overlays, vollständige
320×320-Komposition, Rotation, JPEG-Validierung sowie derselbe JPEG-Bytepfad für
Preview und LCD-Snapshot. 0°, 90°, 180° und 270° verwenden weiterhin nur die
Rotation der Gesamtkomposition.

## Dynamische Änderungen

Bild, Crop/fit, Rotation, Slotauswahl, Overlayzustand, Farbe und relevante
Sensorwerte werden während `running` weiterhin neu gerendert und validiert.
Erst danach ersetzt `LatestFrameBuffer.publish()` den Snapshot atomar. Der
nächste Refresh übernimmt die neue Generation ohne Controller- oder
Sessionneustart. Ein Render- oder Validierungsfehler lässt den letzten gültigen
Snapshot aktiv.

## Begrenzte persistente Diagnostik

Die sessionspezifische JSONL-Diagnostik behält Sessionstart, Safety-Gates,
Framezähler, Generationen, `send_frame_once()`, Segmentzahlen,
Transferdauer, Fehler, Stopgrund, Workerende und Handle-Close bei. JPEG- und
HID-Payloads werden nicht geloggt; zusätzliche Sensortelemetrie wird nicht
aufgezeichnet.

Eine aktive Datei wird bei 2 MiB rotiert; pro Sessiondatei bleiben höchstens
drei nummerierte Backups. Beim Anlegen einer neuen Session werden insgesamt nur
die 20 neuesten `gui-refresh-*.jsonl*`-Dateien behalten. Damit bleibt der
persistente Diagnoseumfang ohne externe Abhängigkeit begrenzt.

## Offline-Prüfung

Die vollständige Suite bestand mit 194 Tests. Darin enthalten sind insbesondere:

- Produktionsbetrieb über 35 Frames und über 30 simulierte Sekunden ohne
  automatischen Stop;
- terminaler expliziter Stop sowie nicht blockierender Fensterschluss;
- Abbruch beim ersten Transportfehler ohne Retry oder Reconnect;
- keine parallele Session, kein überlappender Sender und kein Catch-up;
- dynamische Publikation ohne Sessionneustart und unveränderter letzter gültiger
  Snapshot bei Renderfehlern;
- entfernte Hardwarefreigabe, expliziter Start, kein Autostart und vollständige
  Production-Safety-Gates;
- weiter außen liegende, symmetrische, nicht überlappende und rundsichere Slots
  für alle Metrics sowie Rotation der vollständigen Komposition;
- größenbasierte JSONL-Rotation und zahlenmäßige Runtime-Logbegrenzung.

Zusätzlich bestanden `compileall` und `git diff --check`. Sämtliche Geräte-
Callsites blieben in den Runtime-Tests gesperrt oder durch Fakes ersetzt. Es
fand kein Live-Test statt.
