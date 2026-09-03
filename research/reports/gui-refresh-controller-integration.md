# Offline-Integration von GUI und LCD-Refreshcontroller

Datum: 2026-09-03

## Ziel und Grenze

Dieses Ticket implementiert ausschließlich den GUI-State- und
Controller-Integrationslayer für einen späteren LCD-Livebetrieb. Die GUI
erzeugt weiterhin keinen `HidrawFrameSender` und besitzt keine
Produktions-Factory für reale Hardware. Ohne explizit injizierte Factory ist
`LCD starten` deaktiviert.

Es fanden keine Gerätekommunikation, keine HID-/USB-Writes und keine Live-Tests
statt. Interface 0, OpenRGB und das getrennte Gerät `0b05:19af` wurden nicht
berührt. Das Refreshintervall wurde nicht festgelegt und GIF bleibt in der GUI
ein Standbild aus Frame 0.

## GUI-State-Modell

`src/tuf_aio_gui.py` enthält nun das explizite Enum `GuiRefreshState` mit den
Zuständen `idle`, `starting`, `running`, `stopping` und `error`. Eine zentrale
Zustandsfunktion steuert alle betroffenen Bedienelemente:

- In `idle` ist `LCD starten` nur mit vorbereitetem validem Frame und
  injizierter Controller-Factory aktiv.
- `starting` sperrt Start, Stop, Einzelbildtransfer und relevante Änderungen,
  während Framepuffer und Controller erzeugt und genau einmal gestartet werden.
- In `running` ist Start gesperrt und Stop aktiv. Bild, Crop/fit,
  Temperaturoverlay und Overlayfarbe bleiben änderbar; der direkte
  Einzelbildtransfer ist gesperrt.
- Vor Eintritt in `stopping` wurde `request_stop()` bereits nicht blockierend
  aufgerufen. Eine weitere Session oder Framepublikation ist dort gesperrt.
- `error` ist terminal für die Session. Es gibt keinen Retry oder automatischen
  Neustart. Erst `Fehler bestätigen` führt ausdrücklich nach `idle` zurück.

Ein separater kurzer Qt-Timer beobachtet nur `is_running` und `result`. Er
wartet nicht blockierend auf den Worker. `SEND_ERROR`, `INTERNAL_ERROR` und ein
fehlendes Ergebnis führen sichtbar nach `error`; erwartete Stopgründe führen
nach `idle`.

Beim Schließen einer laufenden GUI wird zuerst `request_stop()` ausgelöst und
das Close-Ereignis vorübergehend abgelehnt. Erst nachdem der nicht-daemonisierte
Worker terminal ist, wird das Fenster über die Qt-Ereignisschleife erneut und
erfolgreich geschlossen. Ein laufender synchroner Transfer wird nicht
künstlich unterbrochen.

## Controller- und Sender-Injection

Die neue schmale `RefreshControllerLike`-Schnittstelle umfasst ausschließlich
`start()`, `request_stop()`, `is_running` und `result`. Eine
`ControllerFactory` erhält nur die lesende `FrameSource` der aktuellen Session.
Damit können Tests einen Fake-Controller und Fake-Sender vollständig außerhalb
der GUI bereitstellen.

Die Factory hat absichtlich keine Produktionsvoreinstellung. Insbesondere
werden weder `HidrawFrameSender` noch Gerätesuche, Transportplan oder
Transportintervall durch den neuen Startbutton konstruiert. Diese
Hardwareverdrahtung bleibt ein eigener späterer Schritt.

## Dynamisches Frame-Publishing

Bei einem expliziten Start erzeugt die GUI aus dem bereits vorbereiteten JPEG
einen neuen `LatestFrameBuffer`; dessen erste validierte Veröffentlichung ist
Generation 1. Während `running` verwenden Bildwechsel, Crop/fit-Wechsel,
Overlay an/aus und Farbänderungen weiterhin die gemeinsame Bildpipeline:

```text
gecachter 320x320-RGB-Basisframe
-> Temperaturoverlay
-> JPEG-Encoding
-> bestehende ASUS-JPEG-Validierung
-> LatestFrameBuffer.publish()
```

Erst nach erfolgreichem Rendering, Preview-Decoding und erneuter Validierung
publiziert die GUI atomar. Der Refreshworker erhält nur immutable Snapshots.
Es gibt keine Queue und keinen teilweise sichtbaren Zwischenstand.

Ein Bild- oder Overlay-Renderfehler beendet die Transportsession nicht. Der
vorherige `PreparedImage`-Stand und der letzte gültige Frame-Snapshot bleiben
aktiv, die Generation bleibt unverändert und der Fehler wird sichtbar
angezeigt. Es folgt weder ein Render- noch ein Transport-Retry.

## Sensorupdate-Verhalten

Das bestehende ungefähr 1-Hz-Sensorpolling bleibt im Qt-GUI-Thread. Es liest
über den injizierbaren `TemperatureReader`; der Refreshworker kennt weder
`TemperatureSnapshot` noch sysfs.

Nur eine tatsächliche Änderung der für das aktivierte Overlay relevanten Werte
Tctl, primäre GPU `edge` oder Tccd1 löst ein neues Overlay/JPEG und anschließend
genau eine neue Framegeneration aus. Ein unveränderter Folgepoll publiziert
nichts. Bei deaktiviertem Overlay werden Sensoränderungen weiterhin in der GUI
angezeigt, erzeugen aber keinen identischen LCD-Frame neu.

## Offline-Tests

Fünf neue headless-Qt-Tests ergänzen die vorhandenen Controller- und
FrameBuffer-Tests. Der vollständige Fake-End-to-End-Pfad verwendet ein
temporäres Fake-hwmon, einen Fake-Controller und einen Fake-Sender:

```text
GUI-Start
-> Generation 1 publiziert
-> erster Fake-Transfer
-> Tctl ändert sich
-> Generation steigt genau einmal
-> unveränderter Folgepoll bleibt ohne Publikation
-> nächster Transfer erhält den neuen immutable Snapshot
-> Stop endet mit explicit-stop
```

Der Fake-Sender bestätigt maximal einen gleichzeitigen Transfer. Weitere Tests
decken Buttonzustände, den transienten `starting`-Lock, Farbänderung,
Overlay-Deaktivierung, Bildwechsel, Crop/fit-Wechsel, Renderfehler mit altem
Frame, Publikationssperre während `stopping`, nichtblockierendes Schließen und
den ersten Transportfehler ab. Der Fehlerpfad ruft den Sender genau einmal auf,
endet in `error` und benötigt eine ausdrückliche Bestätigung.

Im End-to-End-Test sind `os.open()` und `send_frame_once()` als verbotene
Callsites überwacht und wurden nicht erreicht. Die vollständige Offline-Suite
bestand mit 157 Tests; die 40 fokussierten GUI-/Controller-Tests bestanden
ebenfalls. `git diff --check` war sauber.

## Verbleibender Schritt zur realen GUI-Hardwareverdrahtung

Ein gesondertes, ausdrücklich freizugebendes Ticket muss eine
Produktions-Factory bereitstellen, die den realen `HidrawFrameSender` erst nach
erneuter sicherer Geräteprüfung mit einem explizit festgelegten konservativen
Transportintervall und begrenzter Sessionpolitik verbindet. Vor einem solchen
Live-Ticket müssen außerdem externe Writer ausgeschlossen sowie GO/NO-GO,
Sessiongrenzen und Sichtbarkeitskriterien festgelegt werden. Aus der jetzigen
Offline-Integration folgt keine Freigabe für reale Writes oder Dauerbetrieb.
