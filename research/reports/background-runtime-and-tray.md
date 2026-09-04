# Hintergrundbetrieb und Tray-Lifecycle

Datum: 2026-09-04

## Ziel und Sicherheitsgrenze

Die Anwendung ist nun für einen dauerhaften, ressourcenschonenden
Hintergrundbetrieb mit genau einem Qt-Prozess, einem Fenster und einem
System-Tray-Icon vorbereitet. Die eigenständige sichtbare Sektion
`Lokale Telemetrie` wurde entfernt; Sensorbackend, Metric-Modell,
LCD-Dropdowns und Overlayrenderer bleiben erhalten.

Dieses Ticket wurde vollständig offline umgesetzt und geprüft. Es gab keine
Gerätekommunikation, kein hidraw-Open, keine HID-/USB-Writes, keine Installation
von Autostart- oder udev-Dateien und keinen Live-Test. `lcd_transport.py`, das
bestätigte `0x08`-Protokoll und sämtliche Production-Safety-Gates wurden nicht
verändert.

## Tray- und Fenster-Lifecycle

Das einmalig beim Fensteraufbau erzeugte `QSystemTrayIcon` besitzt die Aktionen
`Öffnen`, `LCD starten`, `LCD stoppen` und `Beenden`. Start und Stop folgen
dem vorhandenen GUI-State-Modell und sind nur in passenden Zuständen aktiv.
`Öffnen` zeigt dasselbe vorhandene Fenster, hebt es an und erzeugt weder eine
zweite App-Instanz noch einen weiteren Controller.

Das normale Fenster-X blendet das Fenster nur aus. Prozess, Tray, laufende
LCD-Session und erforderliches Sensorpolling laufen weiter. Wiederholtes
Ausblenden und Öffnen erzeugt keine zusätzlichen QTimer, Signalverbindungen,
Sensorpoller oder Refreshworker.

Nur die explizite Tray-Aktion `Beenden` fordert ein Prozessende an. Bei einer
laufenden Session ruft sie zunächst nicht blockierend `request_stop()` auf.
Ein begonnener Frame darf fertig werden; nach terminalem Workergebnis und
Handle-Close werden Timer und Tray beendet und anschließend die Qt-Anwendung
verlassen. Es gibt keinen Retry, Reconnect oder automatischen Sessionneustart.

## Sensorpolling-Policy

Es existiert weiterhin genau ein Qt-Sensortimer mit ungefähr 1 Hz. Er läuft
nur, wenn das Datenoverlay aktiv ist, mindestens ein LCD-Slot eine dynamische
Metric enthält und zusätzlich entweder die LCD-Session läuft oder das Fenster
mit einer vorbereiteten Preview sichtbar ist.

Damit gilt insbesondere:

- verstecktes Fenster und gestopptes LCD: kein hwmon-, `/proc/stat`- oder
  `gpu_busy_percent`-Polling;
- verstecktes Fenster und laufendes LCD: Polling bleibt ausschließlich für die
  tatsächlich ausgewählten Metrics aktiv;
- deaktiviertes Overlay oder viermal `Aus`: kein Sensorpolling;
- sichtbare Preview mit aktiven Metrics: weiterhin ungefähr 1 Hz.

`SystemTelemetryReader.sample()` erhält die Menge ausgewählter Metric-IDs.
Ein reines CPU-Auslastungslayout überspringt hwmon vollständig; nicht gewählte
Temperaturkanäle und GPU-Auslastung werden nicht gelesen. Injizierte ältere
Testreader ohne selektive API bleiben als vollständig offline testbarer
Fallback unterstützt. Der HID-Worker liest weiterhin niemals Sensoren oder
`/proc/stat`.

## Rendering- und Preview-Policy

Nur eine sichtbare Änderung einer ausgewählten Metric löst eine neue
Komposition, JPEG-Validierung und atomare Publikation in den
`LatestFrameBuffer` aus. Unveränderte Werte sowie Änderungen nicht ausgewählter
Metrics erzeugen kein neues JPEG. Bild, Crop/fit, Rotation, Farbe,
Slotbelegung und Overlayzustand bleiben die weiteren expliziten Renderauslöser.

Ist das Fenster verborgen, wird ein für das laufende LCD benötigtes JPEG
weiterhin vollständig erzeugt und publiziert. Qt decodiert und skaliert dann
aber keine Preview und aktualisiert keine versteckten Metadatenwidgets. Die
Preview wird lediglich als veraltet markiert und beim nächsten `Öffnen` genau
einmal aus denselben validierten JPEG-Bytes aktualisiert. Die laufende Session
und ihr Framepuffer werden dabei weiterverwendet.

Der Refreshworker bleibt eventbasiert: 1,0 s zwischen Frame-Startzeitpunkten,
fertiger immutable JPEG-Snapshot, keine Sensorabfrage, kein Rendering, keine
Queue, kein Catch-up und kein Busy-Wait. Der GUI-seitige Controllerstatus wird
nur während `running` oder `stopping` mit einem einzigen 250-ms-QTimer geprüft.
Außerhalb einer Session ist dieser Timer gestoppt.

Die bisher unbegrenzt wachsenden Ergebnislisten des Controllers sind für den
Dauerbetrieb auf die letzten 1024 Transferdauern und Frameindizes begrenzt.
Der vollständige Frame-Gesamtzähler bleibt erhalten. Die bestehende
größenbasierte JSONL-Rotation bleibt unverändert. Sie schreibt keine JPEG-
Payloads, keine Poll-Sensordaten und verwendet kein `fsync()` pro Frame.

## App- und LCD-Autostart

Unter `packaging/tuf-aio-control-autostart.desktop` liegt eine validierte
XDG-Desktopdatei für den Start mit `--background`. Das optionale
`manage-user-autostart.sh` installiert oder entfernt sie ausschließlich nach
bewusstem Benutzeraufruf unter `${XDG_CONFIG_HOME:-$HOME/.config}/autostart`.
Die Anwendung selbst schreibt dort nichts.

App-Autostart und LCD-Autostart sind getrennt. Die neue persistente Option
`LCD beim Programmstart automatisch starten` ist standardmäßig aus. Für eine
aktivierte Option werden letzte Bildquelle und Skalierungsmodus wiederhergestellt
und exakt der normale `ProductionControllerFactory`-Pfad verwendet. Ein
Safety-Gate-Fehler führt ohne Retry nach `error`; Fenster und Tray bleiben zur
Diagnose verfügbar. Es gibt keinen automatischen Reconnect.

## Permanente Interface-1-udev-Regel

`packaging/99-tuf-aio-control.rules` ist für eine spätere bewusste
Administratorinstallation vorbereitet. Sie passt ausschließlich auf hidraw,
VID `0b05` und PID `1c7b`. Die Basiszeile setzt beide Interfaces für Gruppe
`input` auf `0640`; nur `ID_USB_INTERFACE_NUM==01` erhält anschließend final
`0660`. Interface 0 bleibt gruppenseitig read-only, `0b05:19af` wird nicht
erfasst.

Die Anwendung installiert keine Regel, ruft kein `sudo` auf und verändert keine
Systemberechtigung. Installations-, Prüf- und Entfernungshinweise stehen in
`packaging/README.md`. `udevadm verify` bestätigte die Repositoryregel offline.

## Offline-Prüfung

Die vollständige Suite bestand mit 202 Tests. Abgedeckt sind insbesondere:

- Fenster-X blendet aus, ohne Session oder Prozess-Lifecycle zu beenden;
- Tray-Öffnen verwendet dasselbe Fenster und startet keine zweite Session;
- Tray-Start/Stop und explizites Quit folgen dem GUI-State-Modell;
- Quit während eines laufenden Frames wartet nicht im GUI-Thread und beendet
  erst nach Workerende;
- keine sichtbare lokale Telemetriesektion oder zugehörigen Widgets;
- Sensorbackend, Metric-Modell und dynamische LCD-Publikation bleiben aktiv;
- versteckt plus idle pollt nicht, versteckt plus running pollt nur ausgewählte
  Metrics;
- unveränderte Metrics erzeugen kein neues JPEG, versteckte Updates keinen
  Preview-Repaint;
- wiederholtes Hide/Show vervielfacht weder Timer noch Worker;
- LCD-Autostart ist standardmäßig aus; ein Gate-Fehler endet ohne Retry und
  ohne hidraw-Open;
- XDG-Datei, Hilfsskript und eng begrenzte Interface-1-udev-Regel sind offline
  geprüft.

Zusätzlich bestanden `compileall`, `git diff --check`,
`desktop-file-validate`, `sh -n` und `udevadm verify`. Es fand kein Live-Test
und keine Installation statt.
