# Produktionsverdrahtung des GUI-LCD-Refreshpfads

Datum: 2026-09-03

## Ziel und ausgeführter Umfang

Die bestehende PySide6-GUI ist nun über eine klar getrennte
`ProductionControllerFactory` mit dem vorhandenen `RefreshController`,
`LatestFrameBuffer`, `HidrawFrameSender` und `lcd_transport` verdrahtet. Der
bestätigte Interface-1-`0x08`-JPEG-Transport, seine Paketbildung und sein
Scheduler wurden nicht neu implementiert.

Während dieses Tickets fanden keine Gerätekommunikation, kein hidraw-Open,
keine HID-/USB-Writes und kein Live-Test statt. Alle Produktionspfade wurden
ausschließlich mit injizierten Fake-Geräten und Fake-Sendern geprüft.

## ProductionControllerFactory

`src/gui_refresh_factory.py` besitzt die einzige Produktionsverdrahtung für
eine GUI-Refreshsession. Die Factory führt in dieser Reihenfolge aus:

1. vorhandene dynamische `discover_lcd_interface()`-Erkennung für exakt
   `0b05:1c7b` aufrufen;
2. das eindeutig gefundene Interface mit den gemeinsamen strengen
   Runtime-Safety-Gates prüfen;
3. lokal erkennbare konkurrierende Writer für genau diesen Character-Device-
   Knoten ausschließen;
4. aus dem bereits validierten `FrameSource`-Snapshot den festen temporären
   Entwicklungsplan erzeugen;
5. den vorhandenen `HidrawFrameSender` für das gefundene Interface erzeugen;
6. den vorhandenen `RefreshController` mit derselben dynamischen `FrameSource`
   zurückgeben.

Die Factory öffnet selbst kein Gerät und startet keinen Worker. Erst der
anschließende explizite GUI-Start erreicht `RefreshController.start()`.
Interface 0 und andere VID/PID-Kombinationen werden durch die Gates abgelehnt.
Es gibt keinen Pfad zu `0b05:19af` und keine OpenRGB-Integration.

Die Factory bleibt injizierbar: Discovery, Konkurrenzprüfung, Sendererzeugung
und Controllerkonstruktion können in Offline-Tests ersetzt werden. Die GUI
selbst erhält weiterhin nur die schmale `ControllerFactory`-Schnittstelle.

## Gemeinsame Geräte-Safety-Gates

Die zuvor im bestätigten Fünfframe-Testwerkzeug enthaltenen read-only
Geräteprüfungen liegen nun gemeinsam in `src/lcd_runtime_safety.py`. Das
Testwerkzeug verwendet dieselben Funktionen weiter; dadurch existieren keine
abweichenden GUI- und Testdefinitionen für das Zielgerät.

Vor dem Start müssen alle folgenden Merkmale passen:

- VID/PID exakt `0b05:1c7b`;
- Interface exakt 1;
- Hersteller `ASUS Tek` und Produkt
  `TUF GAMING LC III 360 ARGB LCD`, sofern jeweils vorhanden;
- `bcdDevice` nach numerischer Normalisierung exakt `0x0049`;
- HID Usage Page/Usage exakt `0xff06/0x01`;
- unnummerierter HID-Report;
- Input-Report 16 Byte und Output-Report 1024 Byte;
- keine deklarierten Feature-Reports;
- HID-Interfaceklasse `03/00/00`, Alternate Setting 0;
- exakt die bekannten Interrupt-Endpunkte `0x03` OUT/1024 und `0x84` IN/16;
- absoluter, dynamisch entdeckter `/dev/hidraw*`-Pfad;
- kein lokal in `/proc` erkennbarer fremder Writer auf demselben
  Character Device.

Scheitert Discovery, Metadatenprüfung oder Konkurrenzprüfung, wirft die Factory
einen verständlichen `ProductionControllerFactoryError`. Die GUI wechselt ohne
Retry nach `error`. Da Sender und Controller erst nach allen Gates erzeugt
werden, ist ein Schreib-Open in diesem Fehlerpfad nicht erreichbar.

Der Produktions-`HidrawFrameSender` gibt die gemeinsame strenge
`runtime_device_error()`-Prüfung zusätzlich an den bestehenden
`send_frame_once()`-Pfad weiter. Damit ergänzen die vorhandene dynamische
Revalidierung unmittelbar vor jedem Write und die vollständigen Runtime-Gates
einander. Handle-Close, Segmentabbruch und fehlender Retry bleiben unverändert
im bestehenden Transport implementiert.

## Temporäre Sessionpolitik

Die erste GUI-Produktionsverdrahtung verwendet ein isoliertes und im Quelltext
ausdrücklich als temporär markiertes Entwicklungsprofil:

- 1,0 s minimale Zeit zwischen Frame-Startzeitpunkten;
- maximal 30,0 s Sessiondauer;
- maximal 30 vollständig gesendete Frames.

Diese Werte sind nicht benutzerkonfigurierbar. Der vorhandene
`RefreshController` verhindert Catch-up-Bursts und parallele Transfers. Ein
langsamer Transfer verschiebt den nächsten Start nach hinten. Der erste
Transportfehler beendet die Session ohne Retry; Zeit- oder Framegrenze beendet
sie sauber ohne automatischen Neustart.

Das Profil ist in `build_gui_development_plan()` gekapselt und kann später als
Einheit durch eine gesondert geprüfte Produktionspolitik ersetzt werden. Es
gibt weiterhin keine unbegrenzte Dauersession und keinen Autostart.

## Explizite GUI-Hardwarefreigabe

Die GUI zeigt die deutlich bezeichnete Option
`Hardware-Livebetrieb freigeben`. Sie ist bei jedem Programmstart aus und wird
nicht aus Einstellungen wiederhergestellt. Ohne aktivierte Option bleiben
`LCD starten` und der bestehende Einzelbild-Sendebutton gesperrt; auch direkte
Methodenaufrufe brechen vor dem sessionbezogenen Factory-/Discovery-Aufruf,
hidraw-Open und Write ab. Die bestehende read-only Statussuche beim GUI-Start
bleibt davon getrennt.

`LCD starten` wird nur in `idle`, mit validiertem vorbereitetem Frame,
read-only erkanntem Gerät, vorhandener Produktions-Factory und aktivierter
Hardwarefreigabe angeboten. Während `starting`, `running`, `stopping` und
`error` ist die Freigabe nicht veränderbar.

`LCD stoppen` ruft weiterhin ausschließlich das nicht blockierende
`request_stop()` auf. Ein bereits begonnener synchroner Frame wird vollständig
beendet und sein Handle vom bestehenden Transport im `finally` geschlossen;
erst danach endet der Worker. Der Qt-Thread wartet nicht blockierend.

## Dynamische Frames während der Session

Die Produktions-Factory erhält denselben sessionspezifischen
`LatestFrameBuffer`, den der GUI-State-Layer bereits verwaltet. Deshalb bleiben
die zuvor offline belegten dynamischen Pfade unverändert wirksam:

```text
Bild / Crop oder fit / Overlay / Farbe / geänderte Sensorwerte
-> gecachter RGB-Basisframe
-> Temperaturoverlay
-> validiertes JPEG
-> LatestFrameBuffer.publish()
-> nächster RefreshController-Snapshot
```

Das ungefähr 1-Hz-Sensorpolling bleibt ausschließlich im Qt-GUI-Thread. Nur
eine Änderung von Tctl, Tccd1 oder `edge` der primären GPU erzeugt bei aktivem
Overlay eine neue Generation. Zwischen Änderungen verwendet der HID-Worker
denselben immutable JPEG-Snapshot und liest weder sysfs noch Sensorobjekte.

Bild-, Skalierungs-, Overlay- und Farbänderungen benötigen keinen Neustart der
Session. Ein Render- oder Validierungsfehler lässt den vorherigen Snapshot und
seine Generation aktiv.

## Offline-Prüfung

Neun neue Factory-Tests sowie zwei zusätzliche GUI-Tests prüfen unter anderem:

- Factoryaufbau mit Fake-Gerät, bestehendem Sender, Controller und FrameSource;
- jedes Identitäts-, Interface-, HID-, Report-, Feature- und Endpoint-Gate;
- falsches `bcdDevice`, falsches Interface sowie falsche Reportgrößen;
- fehlende oder mehrdeutige Discovery und erkannte Konkurrenzwriter;
- ausschließlich auf `0b05:1c7b` begrenzte Standard-Discovery;
- das exakte 1,0-s-/30-s-/30-Frame-Entwicklungsprofil;
- sauberen Stop und ersten Senderfehler ohne Retry;
- standardmäßig deaktivierte GUI-Hardwarefreigabe;
- keinerlei Factory-, `send_frame_once()`- oder `os.open()`-Erreichbarkeit ohne
  Freigabe;
- sichtbaren GUI-`error` bei einem Produktions-Gate-Fehler vor jedem Open.

Die bestehenden Tests belegen zusätzlich dynamische Sensor- und Farb-
Generationen, atomare Snapshots, fehlende parallele Sender, Renderfehler mit
altem Frame sowie den nicht blockierenden GUI-Stop. Die vollständige
Offline-Suite bestand mit 168 Tests. `git diff --check` war sauber.

## Verbleibender Schritt zum ersten echten GUI-Livebetrieb

Die technische Produktionsverdrahtung ist implementiert, aber noch nicht live
ausgeführt oder dafür freigegeben. Der nächste Schritt ist ein gesonderter,
ausdrücklich autorisierter und beaufsichtigter GUI-Live-Test mit temporärer
Schreibberechtigung ausschließlich für das dynamisch gefundene Interface 1.
Vorher müssen externe Writer ausgeschlossen und Transporterfolg,
Defaultbild-Unterdrückung, sichtbare Kontinuität, Stopverhalten und das harte
30-s-/30-Frame-Ende als getrennte Beobachtungskriterien festgelegt werden.

Interface 0, `0b05:19af`, OpenRGB, andere Intervalle, GIF-Liveanimation,
unbegrenzter Dauerbetrieb und automatische Wiederholung nach Fehlern bleiben
außerhalb dieses Schritts.
