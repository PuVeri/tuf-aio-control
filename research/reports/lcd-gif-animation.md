# LCD-GIF-Liveanimation

Stand: 2026-09-04

## Ergebnis und Sicherheitsgrenze

Die GUI kann vorbereitete GIF-Frames zeitlich nacheinander als aktuelle
LCD-Komposition veröffentlichen. Die Funktion wurde offline implementiert und
getestet und anschließend manuell auf einer ASUS TUF GAMING LC III 360 ARGB
LCD erfolgreich live-validiert. Die GIF-Wiedergabe war sichtbar flüssig und
wie gewünscht. Das bestätigte `0x08`-Protokoll und alle
Production-Safety-Gates blieben unverändert.

## Einheitliches 4-Slot-Layout

Die festen symmetrischen Anker sind jetzt:

```text
oben links:     Label (105, 63),  Wertspalte x=94
oben rechts:    Label (215, 63),  Wertspalte x=226
unten links:    Label (105, 225), Wertspalte x=94
unten rechts:   Label (215, 225), Wertspalte x=226
```

Die Wert-y-Position ist absichtlich nicht blind festgelegt: Das Layout misst
zuerst Label- und Wert-Bounding-Box und setzt den Wert dann exakt 6 Pixel unter
die sichtbare Labelkante. Das sind ungefähr 4 Pixel mehr Abstand als zuvor.

Das Metric-Modell besitzt neben dem unveränderten vollständigen Dropdownnamen
ein eigenes kurzes LCD-Label: `CPU`, `GPU`, `CPU PKG`, `CPU CCD`, `GPU TEMP`,
`GPU HOT` und `GPU MEM`. Alle sieben regulären LCD-Texte erreichen mit der
technischen Condensed-Mono-Semibold-Schrift dieselbe Zielgröße von 25 px.
Auto-Fit bleibt nur als Sicherheitsnetz für unerwartete Texte bestehen.
Wertschrift, Farbe, IDs und GUI-Dropdownnamen sind unverändert.

Die Tests messen mit den tatsächlich geladenen Label- und Wertefonts alle
Metric-Labels, Prozentwerte, Temperaturwerte, Extremwerte und `—`. Sämtliche
Ecken ihrer Bounding-Boxes bleiben innerhalb des runden Sicherheitsradius von
153 Pixeln um `(160, 160)`. Das entspricht weiterhin knapp acht Pixeln Abstand
zum physischen Kreisrand im ungünstigsten geprüften Fall. Die vollständige
Komposition rotiert danach gemeinsam um 0°, 90°, 180° oder 270°.

## Vorbereitung und gemeinsamer Renderpfad

`prepare_gif()` liest die Quelldatei einmal beim Bildwechsel und cached alle
skalierten 320×320-RGB-Basisframes, ihre originalen Millisekunden-Dauern und
den Loopwert als unveränderliches `PreparedAnimation`-Modell. Während einer
Wiedergabe wird die GIF-Datei weder erneut geöffnet noch dekodiert.

Jeder fällige Frame verwendet denselben bestehenden Kompositionspfad:

```text
gecachter GIF-RGB-Basisframe
→ aktuelle vier Telemetrieslots
→ vollständige 320×320-Komposition
→ Rotation
→ validiertes JPEG
→ je nach Taktquelle Preview oder LatestFrameBuffer.publish()
```

Für denselben Basisframe und Zustand entstehen identische Bytes; Preview und
LCD dürfen wegen ihrer unabhängigen Taktung jedoch gleichzeitig verschiedene
Frameindizes zeigen.

Änderungen von Telemetrie, Overlayfarbe, Slotbelegung, Rotation oder
Overlaystatus rendern den aktuellen GIF-Basisframe neu, ohne Timeline oder
LCD-Session zu starten. Der folgende Animationsframe verwendet automatisch den
neuesten Zustand.

## Scheduler und Timing-Policy

`src/gif_animation.py` ist eine kleine Qt- und transportunabhängige
Timeline-Steuerung. Sie verwaltet ausschließlich Frameindex, effektive Dauer,
abgeschlossene Loops und nächste Deadline. Sie besitzt weder Thread noch
Framequeue und kennt keine Sensoren, JPEGs oder Geräte.

Die nach einem realen Sichttest als ruckelig bewertete 125-ms-/8-FPS-Policy ist
verworfen. Die persistente GUI-Einstellung bietet 1×, 1.5×, 2× und 3×; Default
ist 2×. Effektive Dauern werden als `Originaldauer / Wiedergabefaktor`
berechnet. Nur eine technische 1-ms-Untergrenze verhindert eine ungültige
Nulldauer; sie ist keine Transport- oder FPS-Policy.

Bei laufendem LCD führt der synchrone Transfer den Producer: Nach einem
vollständig abgeschlossenen Frame fordert der Worker genau den sequenziellen
Folgeframe an und wartet auf dessen Bereitstellung. Ist die skalierte Dauer des
vorherigen Frames bereits während des Transfers verstrichen, wird N+1 sofort
gerendert; andernfalls wartet ein Single-Shot-Timer nur die Restdauer. Auch bei
großer Verzögerung wird weder auf einen absoluten Timeline-Frame gesprungen
noch eine Catch-up-Schleife abgearbeitet. Mehrere Bedarfssignale werden zu
einem Signal zusammengefasst, nicht aufgereiht.

Preview und LCD verwenden getrennte kleine Scheduler auf derselben einmalig
dekodierten `PreparedAnimation`. Deshalb zeigt die sichtbare Preview die
gewählte Geschwindigkeit tatsächlich, ohne künstliches USB-Backpressure. Eine
Faktoränderung skaliert die laufenden Fristen sofort und lädt weder GIF noch
LCD-Session neu.

Die nominelle Senderperiode für GIF beträgt wie beim rekonstruierten
InfoHub-Verhalten 12 ms. Dauert ein synchroner Transfer länger, gibt es danach
keine zusätzliche Taktpause. Der reale Lauf vom 2026-09-04 erreichte mit dem
damaligen per-Frame-Open/Close-Pfad nur 3,0939 FPS. Mit dem persistenten
Produktionssender ergab der beobachtete Live-Ausschnitt ungefähr 29 FPS im
Mittel und etwa 32 FPS im Median für den End-to-End-Frametakt. Einzelne
Segmentwrites lagen typischerweise bei rund 125 µs; USB/hidraw ist damit nicht
mehr der V1-Engpass. Transferüberlappung, Queue, Retry, Reconnect und Catch-up
bleiben ausgeschlossen. Statische Bilder und beendete endliche GIFs verwenden
weiterhin den konservativen 1,0-s-Refresh.

Der persistente Transport ändert den Producer-/Sender-Handshake nicht: Erst
nach dem vollständigen seriellen Transfer wird der Folgeframe angefordert.
Legacy- und Sessionpfad verwenden dieselben 0x08-Reports. Details und die neue
Segmenttiming-Diagnostik stehen in
`research/reports/hidraw-transport-performance.md`.

## Loop-Verhalten

- `loop=0` läuft unbegrenzt bis Stop, Quit oder Sessionfehler.
- Fehlende Loop-Metadaten spielen genau einen Durchlauf.
- Ein positiver GIF-Loopwert bezeichnet Wiederholungen nach dem ersten
  Durchlauf.
- Nach dem letzten endlichen Durchlauf bleibt der letzte Frame im
  `LatestFrameBuffer`; nur die Timeline schläft. Die LCD-Session läuft mit
  statischem 1-Hz-Refresh weiter und stoppt nicht automatisch.

## Bildwechsel und Hintergrundbetrieb

Statisch → GIF, GIF → statisch und GIF A → GIF B ersetzen atomar den
vorbereiteten Inhalt. Die je einmal vorhandenen Preview-/LCD-Scheduler und
Single-Shot-Timer werden wiederverwendet; es entstehen keine zusätzlichen
Worker, Timer, Sender oder LCD-Sessions.

Bei versteckter GUI und laufendem LCD bleibt die GIF-Timeline aktiv. Neue
Kompositionen werden validiert und publiziert, aber nicht als `QPixmap`
dekodiert, skaliert oder neu gezeichnet. Beim Öffnen wird der aktuelle
Snapshot einmal angezeigt, ohne die Animation neu zu starten. Sind GUI
versteckt und LCD gestoppt, ist der Animationstimer inaktiv; auch das bereits
bestehende bedarfsgesteuerte Sensorpolling bleibt aus.

## Offline-Tests

Die vollständige Suite bestand mit 237 Tests. Neu beziehungsweise weiterhin
abgedeckt sind:

- Faktoren 1×/1.5×/2×/3×, Default 2×, Persistenz und 1-ms-Sicherheitsminimum,
- korrekte Dauerskalierung und Änderung ohne Neudekodierung oder Sessionstart,
- mehrere tatsächlich wechselnde Basisframes statt dauerhaft Frame 0,
- strikt sequenzielle Frames auch bei Verspätung, ohne Catch-up oder Queue,
- endlose und endliche Loops sowie gehaltener letzter Frame,
- Stop-/Quit-Verhalten und ruhender Hidden+Idle-Scheduler,
- statisch/GIF/GIF-Wechsel mit wiederverwendeten Preview-/LCD-Schedulern,
- Telemetrie-, Farb- und Rotationsänderung ohne Timeline-/Sessionneustart,
- vier Slots auf jedem GIF-Frame und alle vier Gesamtrotationen,
- transportunabhängige Preview-Taktung mit der gewählten Geschwindigkeit,
- Hidden-LCD-Publishing ohne Preview-Repaint,
- transportgeführtes Producer-Handshake mit unterschiedlichen simulierten
  Transferzeiten, ohne Zusatzpause nach langsamen Transfers,
- weiterhin maximal ein Sender ohne Überlappung oder Queue,
- kurze LCD-Labels einheitlich bei 25 px und exakt 6 px sichtbarer Abstand,
- reale Text-Bounding-Boxes aller Metrics innerhalb des runden Bereichs.

`compileall` und `git diff --check` waren ebenfalls sauber. Sämtliche
Hardwarepfade blieben in den Tests fake beziehungsweise gemockt.
