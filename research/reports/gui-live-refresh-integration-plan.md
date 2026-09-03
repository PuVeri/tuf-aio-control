# Plan zur Integration von GUI, Temperaturoverlay und LCD-Refresh

Datum: 2026-09-03

## Ziel und Grenze

Dieser Bericht kartiert den vorhandenen Offline-Datenfluss und definiert die
kleinsten Schnittstellen für eine spätere GUI-gesteuerte Refreshsession. Es
wurde keine Live-GUI-Anbindung implementiert, kein neuer HID-Pfad angelegt und
kein Gerät angesprochen. Der bestehende `0x08`-Einzelframetransport,
Refreshcontroller, Sensorpfad und deren Sicherheitsgrenzen bleiben
unverändert.

Eine spätere Live-Aktivierung benötigt weiterhin einen eigenen Auftrag mit
festgelegtem Transportintervall und begrenzter Sessionpolitik. Insbesondere ist
aus diesem Plan keine Dauerbetriebsrate abgeleitet.

## 1. Exakte Ist-Architektur

### GUI-Bildauswahl und Preview

`MainWindow.choose_image()` endet nach dem Dateidialog mit einem Aufruf von
`MainWindow.load_image(path)`. Dort endet die eigentliche Bildauswahl:

1. Der Pfad wird aufgelöst und in `_selected_path` gespeichert.
2. `_load_original_preview()` liest ausschließlich die Originalvorschau.
3. `image_pipeline.prepare_image()` erzeugt den finalen Frame.
4. `_load_final_preview()` dekodiert genau dessen JPEG-Bytes für die GUI.
5. `_show_prepared_image()` speichert das Ergebnis als `_prepared` und zeigt
   Metadaten und Validatorstatus.

Nur der visuelle GUI-Pfad wird von `_load_original_preview()`,
`_load_final_preview()` und `_update_scaled_preview()` bedient. Dagegen ist
`_prepared.jpeg_bytes` kein Preview-Sonderformat: Es sind dieselben validierten
Bytes, die `send_selected_image()` aktuell an `send_frame_once()` übergibt.

### Bildpipeline und Overlay

`image_pipeline.prepare_image()` liest Frame 0, richtet ihn per EXIF aus,
konvertiert Transparenz deterministisch gegen Schwarz und skaliert auf
320×320. `_prepare_frame()` hält den RGB-Basisframe als `base_rgb_bytes` fest.
`_encode_and_validate_frame()` ruft den gemeinsamen
`render_temperature_overlay()` auf, encodiert per `_encode_jpeg()` und prüft
das Ergebnis mit `lcd_transport.validate_jpeg()`.

`rerender_prepared_image()` verwendet den gecachten RGB-Basisframe und erzeugt
bei geänderten Overlaydaten ein neues `PreparedImage`, ohne Quelldatei oder
Sensoren zu lesen. `rerender_prepared_animation()` tut dasselbe für alle
vorbereiteten GIF-Frames und erhält Reihenfolge und Timing. Die GUI nutzt für
GIF weiterhin nur Frame 0; es existiert keine Live-GIF-Anbindung.

### Sensorwerte

Der injizierbare Reader der GUI ist standardmäßig
`system_sensors.read_lcd_temperatures()`. `MainWindow.refresh_temperatures()`
wird von einem 1000-ms-`QTimer` im GUI-Thread aufgerufen und speichert das
Ergebnis in `_latest_temperature_snapshot`. `_overlay_values()` bildet daraus
genau `Tctl`, `edge` der konfigurierten primären GPU und `Tccd1` auf
`TemperatureOverlayValues` ab.

Nur wenn sich diese Overlaywerte geändert haben, das Overlay aktiv und ein
Bild vorbereitet ist, ruft die GUI `_rerender_temperature_overlay()` auf.
Dieser Pfad aktualisiert heute `_prepared` und die Preview; er publiziert noch
nichts an den Refreshcontroller.

### Refreshcontroller und Transport

`RefreshController` erhält beim Konstruktor einen unveränderlichen
`RefreshPlan`. In `_run_loop()` wählt er
`self._plan.frames[frame_index]` und übergibt dessen `jpeg_bytes` synchron an
den injizierten `FrameSender`. Bei einem statischen Plan wird dasselbe
Bytes-Objekt über alle Refreshzyklen wiederverwendet.

Die bestehende öffentliche Lebenszyklus-API lautet:

- `start()`: startet genau einmal einen nicht-daemonisierten Worker;
- `stop(timeout)`: setzt das Stop-Event und joint den Worker;
- `wait(timeout)`: joint ohne Stopanforderung;
- `is_running`: zeigt einen lebenden Worker an;
- `result`: liefert thread-sicher den terminalen `RefreshResult`.

`HidrawFrameSender` ist der vorhandene schmale Adapter zu
`lcd_transport.send_frame_once()`. Nur dieser Transport erzeugt die bekannten
`0x08`-Segmente, validiert Interface 1 und führt die synchronen HID-Writes aus.
Der Controller selbst enthält weder HID-Opcode noch Geräteöffnung.

### Heutiger und geplanter Datenfluss

Heute existieren zwei getrennte Enden:

```text
GUI -> Dateipfad -> prepare_image/rerender_prepared_image
    -> PreparedImage.jpeg_bytes -> Preview oder Einzelframe-Sendeklick

RefreshPlan.frames -> RefreshController -> FrameSender
    -> optional HidrawFrameSender -> send_frame_once
```

Die geplante minimale Verbindung lautet:

```text
GUI-Thread
  -> Bildquelle / gecachter 320x320-RGB-Basisframe
  -> TemperatureSnapshot (QTimer, ca. 1 Hz)
  -> TemperatureOverlayValues + OverlayConfig
  -> rerender_prepared_image
  -> validierte JPEG-Bytes
  -> LatestFrameBuffer.publish()        [kurzer Lock, atomarer Austausch]

Refreshworker
  -> LatestFrameBuffer.snapshot()       [kurzer Lock, immutable Referenz]
  -> vorhandener RefreshController-Takt
  -> vorhandener FrameSender
  -> HidrawFrameSender
  -> vorhandenes send_frame_once()
  -> ausschließlich 0x08 / 0b05:1c7b / Interface 1
```

## 2. Minimale neue Schnittstellen

### Besitzer des aktuellen JPEG-Puffers

Eine neue kleine Klasse `LatestFrameBuffer` in `lcd_refresh.py` soll die
maßgebliche gemeinsame Besitzerin des aktuell publizierten,
transportfähigen Frames sein. Die `MainWindow`-Instanz besitzt genau einen
solchen Puffer pro Refreshsession; der Worker erhält nur dessen lesende
`FrameSource`-Schnittstelle. GUI-`_prepared` darf denselben immutable
Bytepuffer weiterhin für Preview und Metadaten referenzieren.

Die minimalen Datentypen und Operationen sind:

```text
FrameSnapshot
  generation: int
  frame: RefreshFrame

FrameSource.snapshot() -> FrameSnapshot

LatestFrameBuffer(initial_jpeg)
LatestFrameBuffer.publish(jpeg_bytes) -> FrameSnapshot
LatestFrameBuffer.snapshot() -> FrameSnapshot
```

`publish()` konstruiert und validiert zuerst außerhalb des Locks einen neuen
unveränderlichen `RefreshFrame`. Erst danach ersetzt es unter einem eigenen
`threading.Lock` atomar das Paar aus Generation und Frame. Bei Validierungs-
oder Encodingfehler bleibt der letzte gute Frame aktiv. `snapshot()` hält den
Lock nur zum Kopieren der beiden Referenzen. Während eines HID-Transfers wird
kein Pufferlock gehalten; das immutable `bytes`-Objekt des Snapshots bleibt bis
zum Ende dieses Senderaufrufs gültig.

Es gibt bewusst keine Queue. Treffen mehrere GUI-Updates vor dem nächsten
USB-Refresh ein, konsumiert der Worker den neuesten vollständig validierten
Stand; Zwischenstände werden nicht nachgesendet.

### Kleine Erweiterung des Controllers

`RefreshController` benötigt optional eine `FrameSource`. Ohne sie bleibt die
bestehende `RefreshPlan.frames`-Semantik bytegleich erhalten. Eine dynamische
Quelle ist nur bei einem statischen Einframeplan zulässig; sie wird nicht mit
der bestehenden Animationsrotation vermischt. Unmittelbar vor jedem
Senderaufruf holt der Worker genau einen Snapshot und verwendet konsistent
dessen `frame.jpeg_bytes` und `frame.jpeg_info`.

Zusätzlich ist `request_stop()` als nicht blockierende Operation sinnvoll. Sie
setzt ausschließlich das vorhandene Stop-Event. Das bestehende `stop()` kann
intern `request_stop()` plus Join bleiben. Dadurch muss der Qt-GUI-Thread nicht
auf einen gerade laufenden synchronen Transfer warten.

### Kommunikation und Thread-Sicherheit

- GUI, `QTimer`, Bildauswahl, Overlaykonfiguration, Rendering und Preview
  bleiben vollständig im Qt-GUI-Thread.
- Nur `LatestFrameBuffer.publish()` übergibt einen fertigen immutable Frame an
  die Workerwelt.
- Der Refreshworker greift auf kein `QWidget`, `QPixmap`, `QSettings` oder
  `TemperatureSnapshot` zu und liest niemals sysfs.
- Stop läuft vom GUI-Thread über `request_stop()` zum bestehenden
  `threading.Event`.
- Ein kurzer GUI-`QTimer` darf `is_running` und `result` beobachten und daraus
  Qt-Zustand aktualisieren. Es ist kein Callback vom Worker in Qt-Objekte nötig.
- `_ACTIVE_REFRESH_LOCK` verhindert weiterhin eine zweite Refreshsession;
  `_FRAME_SEND_LOCK` verhindert parallel dazu jeden konkurrierenden direkten
  Einzelframe-Sender im selben Prozess.

## 3. GUI-State-Modell

| Zustand | Eintritt | `LCD starten` | `LCD stoppen` | Verhalten |
| --- | --- | --- | --- | --- |
| `idle` | Startzustand oder sauber beendete Session | aktiv nur bei validiertem `_prepared`, eindeutigem read-only Gerätestatus und keinem Controller | inaktiv | Bild- und Overlayänderungen normal möglich |
| `starting` | expliziter Startklick | inaktiv | inaktiv | aktuellen Frame validieren, neue Sessionobjekte erzeugen, Gerät erneut prüfen, Controller genau einmal starten |
| `running` | `start()` erfolgreich und Worker aktiv | inaktiv | aktiv | letzter guter Frame wird wiederholt konsumiert; Status wird beobachtet |
| `stopping` | expliziter Stop oder Fensterende | inaktiv | inaktiv | `request_stop()` ist gesetzt; auf terminales Ergebnis warten, keinen zweiten Worker starten |
| `error` | Startfehler, `SEND_ERROR`, `INTERNAL_ERROR` oder fehlendes Workerresultat | inaktiv bis explizite Bestätigung/Rückkehr nach `idle` | inaktiv | ersten Fehler anzeigen, kein Retry und kein automatischer Neustart |

`MAX_DURATION` und `MAX_FRAMES` sind erwartete Grenzen eines bewusst begrenzten
Plans. Sie führen nach Anzeige des Stopgrunds zurück nach `idle`, nicht zu
einem versteckten Neustart. Ein echter unbegrenzter Dauerbetrieb ist mit den
heutigen Caps weder implementiert noch durch diesen Plan autorisiert.

Während `running` dürfen Bildauswahl, Skalierungsmodus, Overlay an/aus,
Overlayfarbe und die 1-Hz-Sensoraktualisierung geändert werden. Jede Änderung
erzeugt zunächst vollständig einen validierten neuen JPEG-Frame und publiziert
ihn dann atomar. Ein ungültiges neues Bild oder ein Renderfehler lässt den
letzten guten Frame aktiv und wird separat angezeigt. Der direkte Button
`Auf Display senden` bleibt während `starting`, `running` und `stopping`
deaktiviert.

Transportintervall, maximale Dauer, maximale Framezahl, Zielgerät und
Primär-GPU-Zuordnung werden für eine laufende Session nicht verändert. Während
`stopping` werden bild- und overlaybezogene Änderungen deaktiviert oder erst
nach Rückkehr nach `idle` angenommen. Beim Schließen des Fensters muss eine
aktive Session zuerst `request_stop()` erhalten; die Anwendung darf den
nicht-daemonisierten Worker nicht unbeaufsichtigt zurücklassen.

## 4. Getrenntes Timingmodell

### Sensorpolling

Der vorhandene Qt-Timer bleibt bei ungefähr 1 Hz. Ein Poll liest sysfs genau
einmal über `read_lcd_temperatures()`, aktualisiert
`_latest_temperature_snapshot` und vergleicht die drei Overlaywerte mit dem
Vorgänger. Der Refreshworker ruft diese Funktion nie auf.

### Overlay und JPEG

Eine Neuerzeugung erfolgt nur bei:

- erfolgreich ausgewähltem oder neu skaliertem Bild,
- Änderung von Overlay an/aus,
- Änderung der Overlayfarbe,
- tatsächlich geändertem Tctl-, GPU-edge- oder Tccd1-Wert.

Gerenderte 320×320-RGB-Basisdaten werden weiterverwendet. Erst nach erfolgreichem
JPEG-Encoding und ASUS-Validierung steigt die Framegeneration. Ohne Änderung
bleibt derselbe immutable JPEG-Puffer publiziert.

### USB-Refresh

Der Refreshcontroller besitzt weiterhin einen eigenen expliziten
`transport_interval_seconds`-Takt. Bei jedem Takt liest er nur den letzten
Frame-Snapshot und darf denselben JPEG-Puffer beliebig oft wiederverwenden. Er
liest weder sysfs noch Quelldateien und encodiert kein JPEG.

Die real gemessene Dauer eines vollständigen Transfers beträgt ungefähr
108–109 ms. Der vorhandene Scheduler startet nie zwei Transfers parallel. Für
Start `S`, Ende `E` und Intervall `I` bleibt seine Regel:

```text
nächster frühester Start = max(E, S + I)
```

Ist `I` kürzer als ein tatsächlicher Transfer, beginnt der nächste frühestens
nach dessen Ende; es gibt keinen Catch-up-Burst. Daraus wird hier bewusst keine
finale Rate abgeleitet. Ein konservativer Takt, Sessiondauer und Framegrenzen
müssen vor einer Live-Aktivierung gesondert beschlossen und getestet werden.

## 5. Safety-Grenzen der späteren Integration

1. Ziel bleibt ausschließlich VID/PID `0b05:1c7b`, Interface 1 mit der
   bestätigten unnummerierten 1024-Byte-OUT-Reportstruktur.
2. Der Integrationscode enthält keine Interface-0-Befehle, keine alternativen
   Opcodes und keine eigene Reportbildung; er delegiert nur an
   `HidrawFrameSender` und `send_frame_once()`.
3. Konstruktion, Bildwahl, Settings-Wiederherstellung und Sensor-QTimer starten
   keinen Writer. Nur ein expliziter `LCD starten`-Klick darf später
   `RefreshController.start()` erreichen.
4. Der erste Transportfehler beendet die Session mit `SEND_ERROR`. Es gibt
   weder Retry, Reconnect, Recovery, Framewiederholung nach Fehler noch
   automatischen Neustart.
5. Der globale Sessionlock und der globale Einzelframe-Sendelock bleiben
   verpflichtend. Der Einzelframe-Button wird während einer Session zusätzlich
   in der GUI gesperrt.
6. Vor einem später autorisierten Start wird das Ziel dynamisch neu entdeckt
   und unmittelbar vor jedem Write durch den bestehenden Transport erneut
   validiert. Ein externer konkurrierender LCD-Writer muss zusätzlich im
   Live-Testverfahren ausgeschlossen werden; Prozesslocks reichen dafür nicht.
7. OpenRGB und das getrennte Gerät `0b05:19af` werden nicht entdeckt, geöffnet
   oder verändert. RGB-Beleuchtung bleibt ausdrücklich außerhalb des Projekts.
8. Ein Stop unterbricht keinen begonnenen Segmentstrom künstlich. Er verhindert
   den nächsten Frame und wird nach Rückkehr des höchstens einen laufenden
   synchronen Transfers terminal.
9. Alle Integrationstests vor einer gesonderten Live-Freigabe verwenden einen
   injizierten Fake-Sender. `HidrawFrameSender`, `os.open()` und `os.write()`
   dürfen dabei nicht erreicht werden.

## 6. Kleine Implementierungsreihenfolge für das nächste Offline-Ticket

1. `FrameSnapshot`, `FrameSource` und `LatestFrameBuffer` ergänzen; Validierung,
   Generation, letzten guten Frame und atomaren Austausch mit reinen
   Threadtests prüfen.
2. `RefreshController` optional aus einer dynamischen Einframequelle lesen
   lassen und `request_stop()` ergänzen; statische und animierte Altpfade
   unverändert halten und vollständig regressionsprüfen.
3. Das GUI-State-Modell als kleines Enum plus zentrale Button-/Transitionlogik
   einführen; Controller- und Senderfabrik injizierbar machen, ohne den realen
   Adapter zu verdrahten.
4. Erfolgreiche Ergebnisse von `load_image()` und
   `_rerender_temperature_overlay()` an den Latest-Frame-Puffer publizieren;
   bei Fehlern den letzten guten Frame behalten. Bild-, Farb- und
   Overlayänderungen im Zustand `running` offline prüfen.
5. Sensorpolling mit der Publikation verbinden und belegen, dass 1-Hz-sysfs-
   Reads nur bei geänderten Werten rendern, während mehrere Refreshzyklen
   denselben Puffer ohne sysfs-Zugriff konsumieren.
6. Einen vollständigen headless Qt-Integrationstest mit temporärem Bild,
   Fake-hwmon, Fake-Uhr und Fake-Sender ergänzen: `idle -> starting -> running
   -> stopping -> idle`, atomarer Framewechsel, erster Fehler nach `error`,
   keine HID-/USB-Aufrufe.
7. Erst in einem weiteren, ausdrücklich autorisierten Live-Ticket den realen
   `HidrawFrameSender` hinter den Startklick schalten und zuvor Takt,
   Sessiongrenzen, externe Writerprüfung und GO/NO-GO festlegen. Dieser Schritt
   gehört nicht zur nächsten reinen Offline-Implementierung.

Damit bleibt jeder Schritt klein, unabhängig testbar und bis zur separaten
Freigabe vollständig gerätefrei.
