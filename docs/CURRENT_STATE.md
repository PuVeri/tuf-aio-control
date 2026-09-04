# Aktueller Projektstand

## CURRENT LIVE HARDWARE STATE

Kanonischer Live-Stand vom 2026-09-03:

- `0x87` wurde auf dem realen Gerät getestet und lieferte `0x0049`.
- Ein eigener Interface-1-`0x08`-JPEG-Transfer wurde real erfolgreich
  ausgeführt; das JPEG erschien sichtbar auf dem physischen LCD.
- Linux-hidraw-Framing, Segmentierung, Nullpadding und sichtbarer JPEG-Commit
  sind damit für das reale v49-Gerät empirisch bestätigt.
- UI und Bildpipeline wurden real benutzt. Ein GIF wurde über die Pipeline
  gesendet; dessen erstes Frame erschien erfolgreich als Standbild auf dem LCD.
- Danach ersetzte die AIO das Standbild wieder durch ihr ASUS-Standardbild.
- Der erste begrenzte reale Refresh-Test übertrug das Referenz-JPEG bei 1,0 s
  Sollintervall exakt fünfmal: 15 vollständige 1025-Byte-Writes, ungefähr
  108–109 ms Transferdauer je Frame, kein Retry, Fehler oder Catch-up.
- Das Referenzbild war während dieses Refresh-Laufs real sichtbar. Seine
  Sichtdauer wurde nicht gemessen; lückenlose Sichtbarkeit, sichere
  Default-Unterdrückung und eine ausreichende Refreshrate sind nicht bestätigt.
- Echte GIF-Animation ist inzwischen offline implementiert, aber weiterhin
  nicht empirisch am realen LCD bestätigt.

Stand: 2026-09-03

## Offline-Stand: kontinuierlicher GUI-Dauerbetrieb

Stand: 2026-09-04

Der normale GUI-Produktionsbetrieb besitzt keinen 30-s-/30-Frame-Hardcap mehr.
Ein ausdrücklicher Klick auf `LCD starten` erzeugt genau eine Refreshsession,
die mit 1,0 s zwischen Frame-Startzeitpunkten bis `LCD stoppen`, einem sauberen
Fensterschluss oder dem ersten Fehler läuft. Es gibt keinen Autostart,
automatischen Neustart, Retry, Reconnect, Catch-up, parallelen Transfer oder
eine Framequeue. Das begrenzte Entwicklungsprofil und das feste Profil des
ersten Refresh-Livetests bleiben für ihre Offline-/Testzwecke separat erhalten.

`LCD stoppen` fordert über `request_stop()` nicht blockierend das Ende an. Ein
bereits laufender Frame darf vollständig abgeschlossen werden; danach beendet
sich der Worker und das durch `send_frame_once()` verwaltete Handle ist
geschlossen. Beim Fensterschluss wartet die GUI ausschließlich über die
Qt-Ereignisschleife auf dieses terminale Ergebnis und hängt nicht blockierend.

Der erste Transportfehler beendet die Session ohne Retry oder Reconnect und
führt zum GUI-State `error` mit sichtbarer Fehlermeldung. Der letzte gültige
`LatestFrameBuffer`-Snapshot bleibt dabei unverändert. Nach der bewussten Aktion
`Fehler bestätigen` ist eine neue Session wieder möglich.

Die sichtbare Entwicklungscheckbox `Hardware-Livebetrieb freigeben` wurde als
redundante Freigabe entfernt. `LCD starten` bleibt die notwendige explizite
Benutzeraktion. Alle Production-Safety-Gates sind unverändert aktiv: exakt
`0b05:1c7b`, Interface 1, `bcdDevice 0x0049`, Usage `ff06/01`, bekannte
Reportgrößen, keine Feature-Reports, dynamischer hidraw-Pfad und Prüfung auf
konkurrierende Writer. `lcd_transport.py` und das bestätigte `0x08`-Protokoll
wurden nicht verändert.

Das symmetrische 2×2-Telemetrielayout verwendet getrennte kurze LCD-Labels:
`CPU`, `GPU`, `CPU PKG`, `CPU CCD`, `GPU TEMP`, `GPU HOT` und `GPU MEM`.
Die vollständigen GUI-Dropdown-Namen und Metric-IDs bleiben unverändert. Alle
regulären LCD-Labels erreichen mit der technischen Condensed-Mono-Schrift die
einheitliche Zielgröße 25 px. Label und Wert werden anhand ihrer tatsächlichen
Bounding-Boxes mit exakt 6 px sichtbarem Abstand angeordnet, ungefähr 4 px
mehr als zuvor. Alle Kombinationen bleiben geprüft innerhalb des runden
Sicherheitsbereichs. Die vollständige Komposition rotiert weiterhin erst nach Basisbild und allen vier
Overlays gemeinsam um 0°, 90°, 180° oder 270°. Preview und LCD-Snapshot
verwenden weiterhin dieselben validierten JPEG-Bytes.

Die JSONL-Transportdiagnostik wird nun bei 2 MiB pro Datei rotiert, behält drei
Backups und begrenzt den Runtime-Logbestand insgesamt auf die 20 neuesten
Dateien. Transportereignisse, Generationen, Segmentzahlen, Dauer, Fehler,
Stopgrund, Workerende und Handle-Close bleiben enthalten; JPEG-Payloads und
nicht benötigte Sensortelemetrie werden weiterhin nicht geloggt.

Die vollständige Offline-Suite bestand mit 194 Tests; `compileall` und
`git diff --check` waren sauber. Getestet wurden unter anderem mehr als 30
Frames und mehr als 30 simulierte Sekunden ohne automatischen Stop,
expliziter Stop, Fensterschluss, erster Transportfehler, fehlender Retry/
Reconnect, fehlende Parallelität und Catch-up, dynamische Publikation ohne
Sessionneustart, vollständige Safety-Gates, alle Slotmetriken, alle vier
Rotationen und die Logbegrenzung. In diesem Ticket fanden keine
Gerätekommunikation, keine HID-/USB-Writes und kein Live-Test statt. Details:
`research/reports/lcd-continuous-runtime.md`.

## Offline-Stand: Hintergrund- und Tray-Betrieb

Stand: 2026-09-04

Die Anwendung besitzt nun genau ein dauerhaftes `QSystemTrayIcon` mit
`Öffnen`, `LCD starten`, `LCD stoppen` und `Beenden`. Das Fenster-X blendet das
vorhandene Fenster nur aus; Prozess, laufende Refreshsession und erforderliche
LCD-Telemetrie laufen weiter. `Öffnen` verwendet dasselbe Fenster und dieselbe
Session. Nur `Beenden` fordert einen sauberen Stop an und verlässt die
Anwendung nach Workerende und Handle-Close.

Die komplette sichtbare Sektion `Lokale Telemetrie` einschließlich CPU-,
CPU-Package-, GPU- und Quellwidgets wurde entfernt. `system_sensors.py`,
`telemetry.py`, die vier LCD-Metric-Dropdowns und der Overlayrenderer bleiben
erhalten.

Der einzige 1-Hz-Sensortimer läuft nur noch bei aktivem Overlay, mindestens
einer ausgewählten dynamischen Metric und entweder laufender LCD-Session oder
sichtbarer vorbereiteter Preview. Versteckt plus gestoppt bedeutet keinerlei
kontinuierliches hwmon-, `/proc/stat`- oder `gpu_busy_percent`-Polling. Der
Production-Sensorreader liest nur die tatsächlich ausgewählten Metric-IDs; ein
reines CPU-Auslastungslayout überspringt hwmon vollständig.

Nur geänderte sichtbare Metrics erzeugen weiterhin ein neues validiertes JPEG.
Im versteckten Zustand wird ein erforderliches LCD-Update publiziert, aber keine
Qt-Preview decodiert, skaliert oder neu gezeichnet und kein verstecktes
Metadatenwidget periodisch aktualisiert. Beim nächsten Öffnen wird die aktuelle
Preview genau einmal nachgezogen. Der Controllerstatus-Timer läuft nur während
`running`/`stopping`; seine Periode beträgt ressourcenschonende 250 ms. Die
Ergebnishistorie hält maximal die letzten 1024 Transfers, der Gesamtframezähler
bleibt vollständig.

Die validierte XDG-Vorlage
`packaging/tuf-aio-control-autostart.desktop` startet die installierte App über
den Benutzerlauncher mit `--background`. Der lokale Benutzerinstaller erzeugt
sie nur nach bewusstem Benutzeraufruf. App-Autostart und LCD-Autostart bleiben
getrennt: Die neue
persistente GUI-Option `LCD beim Programmstart automatisch starten` ist
standardmäßig aus. Aktiviert verwendet sie die wiederhergestellte letzte
Bildquelle und exakt die vorhandene ProductionFactory mit allen Safety-Gates;
Fehler enden ohne Retry/Reconnect in `error`, während Tray und GUI verfügbar
bleiben.

`packaging/99-tuf-aio-control.rules` bereitet die permanente Berechtigung vor:
nur `0b05:1c7b`, Basiszugriff `0640` für Gruppe `input` und ausschließlich
Interface 1 (`ID_USB_INTERFACE_NUM=01`) mit `0660`. Interface 0 bleibt
gruppen-read-only, `0b05:19af` bleibt unberührt. Anwendung und Tests installieren
weder udev- noch Autostartdateien und rufen kein `sudo` auf.

Die bestehende JSONL-Begrenzung bleibt aktiv. Es werden weder JPEG-Payloads
noch vollständige Sensordaten pro Poll geloggt und kein `fsync()` pro Frame
ausgeführt. Das bestätigte `0x08`-Protokoll, der 1,0-s-Refresh und sämtliche
Production-Safety-Gates wurden nicht verändert.

Die vollständige Offline-Suite bestand mit 202 Tests. Außerdem bestanden
`compileall`, `git diff --check`, `desktop-file-validate`, `sh -n` und
`udevadm verify`. In diesem Ticket fanden keine Gerätekommunikation, keine
HID-/USB-Writes, keine Installation und kein Live-Test statt. Details:
`research/reports/background-runtime-and-tray.md`.

## Offline-Stand: lokale Linux-v0.1-Installation

Stand: 2026-09-04

Die produktive Anwendung ist jetzt als eigenständige XDG-Benutzerinstallation
vorbereitet. `packaging/manage-user-installation.sh` kopiert ausschließlich die
elf erforderlichen Python-Runtimedateien nach
`${XDG_DATA_HOME:-$HOME/.local/share}/tuf-aio-control/app`, erzeugt
`$HOME/.local/bin/tuf-aio-control` sowie die normale Desktopdatei und optional
die Login-Autostartdatei. Es werden keine Tests, Research-Daten,
Dokumentationen oder manuellen Hardware-Testprogramme installiert. Die
Installation verwendet echte Kopien und enthält weder Symlink noch absoluten
Pfad zurück nach HeartdriveLAB.

Der Launcher unterstützt unverändert den normalen Aufruf und `--background`.
Desktop- und Autostartdatei verwenden ausschließlich diesen installierten
Launcher. `install` verweigert kollidierende Ziele; `update` ersetzt nur eine
markierte Installation und bewahrt einen aktivierten Autostart. `uninstall`
entfernt nur verwaltete Programm- und Desktopdateien. QSettings und Runtime-
Logs werden durch Installation, Update und Uninstall nicht gelöscht. Ein
Purge-Modus wurde bewusst nicht hinzugefügt.

JSONL-Diagnostik liegt nun unter
`$XDG_STATE_HOME/tuf-aio-control`, bei fehlender oder nicht absoluter
XDG-Angabe unter `~/.local/state/tuf-aio-control`. Die bestehende Größenrotation
und Dateianzahlbegrenzung bleiben unverändert; Tests können weiterhin einen
temporären Pfad injizieren. Das Repository und der installierte Programmbaum
werden nicht mehr als Runtime-Logziel verwendet.

Die tatsächlichen externen Runtime-Abhängigkeiten sind `/usr/bin/python3`,
PySide6 und Pillow. Offline geprüft wurden Python 3.14.7, PySide6 6.11.2 und
Pillow 12.3.0. Der Benutzerinstaller lädt nichts herunter und installiert keine
Abhängigkeiten; er prüft nur deren lokale Importierbarkeit. Die vorhandene
udev-Regel bleibt ein vollständig getrennter administrativer Schritt und wird
vom Benutzerinstaller weder kopiert noch aktiviert.

GIF-Dateien werden weiterhin vollständig im Voraus geladen; Frames, Dauern und
Loop-Metadaten bleiben gecacht. Der aktuelle Entwicklungsstand bindet diese
Frames nun an den gemeinsamen GUI-/LCD-Renderpfad an. Diese Liveanimation ist
offline implementiert, aber noch nicht am realen LCD validiert.

Die neuen Installations- und Logpfadtests verwenden ausschließlich temporäre
HOME-/XDG-Verzeichnisse. Es fanden keine echte Installation, keine
Gerätekommunikation, keine HID-/USB-Writes und kein Live-Test statt. Die
vollständige Offline-Suite bestand mit 210 Tests; außerdem bestanden `sh -n`,
`compileall`, `desktop-file-validate` für beide erzeugten Desktopdateien und
`git diff --check`. Details:
`research/reports/local-installation-layout.md`.

## Offline-Stand: GIF-Liveanimation und weiter außen liegende Slots

Stand: 2026-09-04

Die GUI verwendet für Mehrframe-GIFs nun ein einziges gecachtes
`PreparedAnimation`-Modell und einen kleinen queuefreien Timeline-Scheduler.
Die Quelldatei wird beim Bildwechsel vorbereitet und während der Wiedergabe
nicht erneut dekodiert. Jeder fällige Basisframe läuft zusammen mit den
aktuellen vier Telemetrieslots durch den bestehenden gemeinsamen
Kompositions-, Rotations-, JPEG- und Validierungspfad. Preview und LCD nutzen
denselben Renderer, werden für ihre unterschiedlichen Taktquellen aber
unabhängig fortgeschaltet.

Die frühere 125-ms-/8-FPS-Policy wurde nach dem realen Sichttest verworfen.
Animierte Mehrframe-GIFs verwenden nun ein transportgeführtes serielles Modell
mit nomineller 12-ms-Senderperiode: Nach jedem synchron abgeschlossenen
Transfer fordert der Worker genau den sequenziellen Folgeframe an. Ist dessen
skalierte Dauer bereits verstrichen, beginnt er ohne Zusatzpause; andernfalls
wartet ein Single-Shot-Timer nur die Restdauer. Auch bei Verzögerung bleibt die
Reihenfolge N→N+1 erhalten, ohne Catch-up-Schleife oder absoluten
Timeline-Sprung. Der bekannte reale JPEG-Transfer von ungefähr 108–109 ms
begrenzt die Bildrate daher natürlich auf ungefähr 9 FPS, ist aber nicht
hartcodiert. Es gibt keine zweite Session, Framequeue, Überlappung,
Burstwrites, Retry oder Reconnect. Der statische LCD-Refresh bleibt bei 1,0 s.

Die persistente Einstellung `GIF-Geschwindigkeit` bietet 1×, 1.5×, 2× und 3×;
Default für neue oder fehlende Settings ist 2×. Effektive Dauern sind
`Originaldauer / Faktor`, lediglich auf technisch notwendige 1 ms begrenzt.
Eine Änderung wirkt sofort auf beide bestehenden Scheduler, ohne erneutes
GIF-Decoding oder Neustart der LCD-Session. Die sichtbare Preview folgt der
gewählten Geschwindigkeit unabhängig vom seriellen LCD-Backpressure.

`loop=0` läuft endlos. Fehlende Loop-Metadaten bedeuten einen Durchlauf;
positive Werte zählen Wiederholungen nach diesem ersten Durchlauf. Endliche
GIFs halten anschließend ihren letzten validierten Frame, während der
LCD-Refresh mit 1,0 s weiterläuft. Änderungen von Telemetrie, Farbe,
Slotbelegung, Rotation und Overlaystatus starten weder Timeline noch Session
neu. Statisch/GIF/GIF-Wechsel verwenden weiterhin dieselben zwei vorhandenen
Scheduler und Single-Shot-Timer; es entstehen keine weiteren Worker.

Im versteckten Zustand läuft eine für das LCD benötigte Animation weiter, ohne
Preview-Decodes, Repaints oder Widgetupdates. Beim Öffnen erscheint der
aktuelle Frame ohne Neustart. Versteckt plus gestoppt bedeutet keinen
Animationstimer-Wakeup und weiterhin kein Sensorpolling.

Die Labelanker liegen oben bei `(105, 63)` und `(215, 63)`, unten bei
`(105, 225)` und `(215, 225)`. Die Wertspalten bleiben bei x=94 und x=226;
ihre y-Position wird pro Text aus den tatsächlichen Bounding-Boxes so
berechnet, dass der sichtbare Label-/Wert-Abstand exakt 6 px beträgt. Alle
kurzen LCD-Labels erreichen 25 px. Wertschrift und Farben sind unverändert.
Tatsächliche Font-Bounding-Boxes aller Labels, Prozent-/
Temperaturwerte und `—` bleiben innerhalb des runden Sicherheitsradius; die
Gesamtkomposition rotiert weiterhin erst danach gemeinsam.

Die vollständige Offline-Suite bestand nach dieser Änderung mit 230 Tests; `compileall` und
`git diff --check` waren sauber. `lcd_transport.py`,
`lcd_runtime_safety.py`, das bestätigte `0x08`-Protokoll und die
Production-Safety-Gates wurden nicht verändert. In diesem Ticket gab es keine
Gerätekommunikation, HID-/USB-Writes oder Live-Tests. Details:
`research/reports/lcd-gif-animation.md`.

## Ziel und Grenze

Ziel ist eine native Linux-Steuerung für das LCD der ASUS TUF Gaming LC III
360 ARGB LCD. OpenRGB bleibt für sämtliche RGB-Beleuchtung zuständig;
`tuf-aio-control` dupliziert diese Funktion nicht.

Das undokumentierte HID-Protokoll wird vorrangig statisch und passiv
untersucht. Zwei gesondert freigegebene, eng begrenzte reale `0x87`-Tests, der
erste `0x08`-JPEG-Test, ein Lauf des refaktorierten Einzelbildsenders und der
erste Live-Lauf der automatischen Bildpipeline sind abgeschlossen. Weitere
HID-Schreibtests sind nicht freigegeben.

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

## Statische InfoHub-LCD-Refreshworkeranalyse

Die geschlossene Workerrekonstruktion steht in
`research/reports/infohub-lcd-refresh-worker-analysis.md`. Reproduzierbarer
read-only Export:
`research/ghidra-scripts/ExportInfoHubRefreshTriage.java`.

- `0x0040b103` liegt im `DeviceMainDlg`-Initialisierungspfad
  `0x0040ada0`. Er startet über `_beginthreadex` den generischen Timerthread
  `0x00425c10` mit einer Zielperiode von 12 ms, Repeat- und Run-Flag sowie
  einem manuellen Abschluss-Event.
- Die Schleifenrückkante liegt in `0x00425c10`, nicht im Worker
  `0x00414ff0`. Der Timer zieht nur die Callbacklaufzeit von 12 ms ab; dauert
  der synchrone Transfer länger, folgt die nächste Iteration ohne zusätzlichen
  Sleep. 12 ms sind daher eine Zielperiode, keine garantierte JPEG-Framerate.
- `0x00414ff0` verarbeitet entweder genau ein Hostereignis ohne JPEG oder
  ruft im leeren Queuezustand `0x00416bc0` auf. Nur Connection-Gate, Windows-
  Power-Suppression und ein vorhandener JPEG-Puffer können den anschließenden
  Write verhindern. Der 2000-ms-Zweig ist ausschließlich ein Monitoringtask,
  nicht der Transportrefresh.
- `GetLEDData()` erzeugt vor einem Refresh kein neues Bild und konsumiert den
  Puffer nicht. Jeder berechtigte Idle-Tick sendet den jeweils letzten
  vollständigen JPEG-Stand erneut. `OnControlTimer()` und
  `DrawHideControl()` bilden den getrennten Producer: defaultmäßig 30 ms, bei
  GIF nach Metadaten mit mindestens 16 ms.
- Während der Startqueue wird nach HID-Erkennung und Konfigurationsaufbau ein
  separates Interface-0-Controlword `12 01 00 80` gesendet. Sein Payloadbyte
  stammt aus der Einstellung `led_brightness`. Eine Abschaltung des internen
  Boot-/Objektproduzenten ist dadurch nicht belegt; pro erfolgreichem
  `0x08`-Refresh existiert weiterhin kein Interface-0-Begleitbefehl.
- Belegt ist daher Strategie A: InfoHub hält das Hostbild durch wiederholte
  vollständige `0x08`-Transfers sichtbar. Ein interner Producer-Hold oder eine
  Deaktivierung ist nicht belegt. Der eigene einmalige Linux-Transfer wird
  später vom nächsten internen Commit überstimmt, während InfoHub seinerseits
  fortlaufend neue Hostcommits liefert.
- Der generische Stophelfer `0x00425bc0` löscht das Run-Flag, wartet höchstens
  1000 ms auf das Abschluss-Event und schließt es. Für die konkrete LCD-
  Timerinstanz wurde kein direkter Aufruf dieser Stopkante gefunden; ihre
  Bindung an die InfoHub-Prozess-/Dialoglebensdauer ist daher stärker gestützt
  als vollständig bewiesen.

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
Gerätestatus, getrennte Original-/Ausgabevorschauen, Pfad, Auflösungen,
Eingabeformat, JPEG-Profil, Dateigröße, Segmentzahl, Padding und
Validierungsstatus. Unterstützte Quellen werden offline vorbereitet; erst
nach einem expliziten Klick auf `Auf Display senden` kann ein Frame übertragen
werden. Nicht verarbeitbare, von Qt darstellbare Bilder bleiben nach
Möglichkeit als Originalpreview sichtbar, der Sendebutton ist dann deaktiviert
und der Validierungsfehler wird angezeigt.

Vor jedem Klicktransfer validiert die GUI die finalen JPEG-Bytes erneut und
führt die dynamische Geräteerkennung erneut aus. Danach ruft sie
`send_frame_once()` genau einmal auf; dessen VID/PID-, Interface-, Report- und
Per-Write-Revalidierungen bleiben unverändert. Es gibt kein automatisches
Senden, Retry, Reconnect, Polling-Write, IN-Read, Interface 0, Folgeframe,
Animation, Autostart oder Hintergrunddienst.

## Sichere Offline-Bildvorbereitung

`src/image_pipeline.py` akzeptiert JPEG/JPG, PNG, WebP, BMP und GIF. Es wendet
EXIF-Orientierung an, setzt Transparenz auf Schwarz zusammen, konvertiert nach
RGB und erzeugt je nach GUI-Auswahl entweder einen mittig beschnittenen Crop
oder ein vollständig sichtbares Fit-Bild mit schwarzer Restfläche. Beide Modi
erhalten das Seitenverhältnis und liefern exakt 320×320 ohne freie Verzerrung.

Die JPEG-Ausgabe entsteht ausschließlich im Speicher mit Pillow 12.3.0 und
libjpeg-turbo: Qualität 60, 4:2:0, `progressive=False`, `optimize=False`.
Anschließend muss sie den unveränderten `lcd_transport.validate_jpeg()`-
Vertrag einschließlich JFIF, SOF0, 8 Bit, Standard-Huffmantabellen, EOI ohne
Nachlauf und `N<=200` erfüllen. Quellen über 64.000.000 Pixel werden vor der
vollständigen Verarbeitung abgelehnt; Originaldateien werden nie verändert.

Die aktive GUI unterstützt GIF weiterhin ausschließlich als Standbild. Ihr
normaler `prepare_image()`-Pfad lädt nur Frame 0 und kennzeichnet die Quelle
als `GIF · erstes Bild als Standbild`; es existieren dort weder `QMovie`,
Timer noch Mehrfachframesenden. Zusätzlich kann `prepare_gif()` nun rein
offline alle Frames, originalen Millisekunden-Dauern, Loopwert und bereits
validierte 320×320-JPEGs als unveränderliches `PreparedAnimation`-Datenmodell
bereitstellen. Dieser Pfad ist nicht an GUI oder Gerät angeschlossen. Die
bisherige Einzelframepipeline steht in `docs/LCD_IMAGE_PIPELINE.md`; die neue
Offline-Erweiterung in `research/reports/lcd-refresh-sender-design.md`.

Die gesamte Offline-Suite umfasst jetzt 80 erfolgreiche Tests. Fünf
headless-Qt-Tests prüfen Referenzbild, inkompatible Preview, fehlendes Gerät,
Transportfehler ohne Retry und genau einen `send_frame_once()`-Aufruf pro
Sendeklick. Weitere Pipeline-Tests prüfen Landscape/Portrait in Crop und Fit,
Quadrat, Alpha-PNG, JPEG/PNG/WebP/BMP, animiertes GIF mit ausschließlich Frame
0, die getrennte Offline-Vorbereitung aller GIF-Frames samt Dauer-/Loopwert,
EXIF-Rotation sowie sehr kleine, große und ungültige Quellen. Alle
Geräteoperationen sind gemockt; während dieses Tickets fand keine
Gerätekommunikation statt und kein Bild wurde gesendet.

## Realer Pipeline-Live-Test und statische Persistenzanalyse

Die automatische Bildpipeline ist inzwischen auf dem realen Gerät mit
Versionswert `0x0049` live bestätigt: Ein beliebiges unterstütztes Eingabebild
wurde von `image_pipeline.py` in ein gültiges 320×320-Baseline-JPEG
umgewandelt, über GUI und den unveränderten `lcd_transport.py`-Einzelbildpfad
übertragen und sichtbar committed. Das erwartete Bild blieb nur kurz sichtbar
und wurde anschließend durch einen anderen Displayinhalt ersetzt. In der
darauffolgenden Analyse gab es keine weitere Gerätekommunikation.

Die statische Ursache und ihre Evidenzgrenzen stehen in
`research/reports/lcd-static-image-persistence-analysis.md`:

- Der v51-`0x08`-Pfad besitzt keinen belegten Frame-Verfall oder Rollback.
  Nach dem Commit bleibt sein Ringknoten sichtbar, bis ein anderer Produzent
  einen Folgeknoten bereitstellt und der gemeinsame Displaycallback diesen
  committed.
- Der interne Boot-/Objektpfad ist ein solcher Produzent. Beim Default
  `config+0x111 = 1` wiederholt der Bootcallback seine Recordfolge. `0x08`
  deaktiviert diesen Callback nicht und ändert `+0x111` nicht. Das reale
  Überschreiben passt zu diesem Mechanismus; dessen bytegenaue Identität in
  v49 bleibt mangels v49-Binärdatei formal offen.
- `config+0x110` beziehungsweise `0x1a` wählt nur zwischen zwei Zeit-/
  Skalenberechnungen und ist kein belegter Holdbefehl. `0x1f` verändert
  `+0x111`, aber keiner der rekonstruierten Werte ist als sicherer statischer
  Holdzustand belegt: `0` aktiviert den normalen gespeicherten Objektpfad,
  `1`/andere Nichtnullwerte wiederholen den Bootpfad, und `2` besitzt einen
  zusätzlichen Übergangs-/Resetablauf.
- ASUS InfoHub 1.0.0.15 setzt vor oder nach einem erfolgreichen Bildtransfer
  keinen separaten Static-/Holdmodus. Sein Leerlauf-Worker ruft den
  `0x08`-Sender wiederholt auf; `GetLEDData()` liefert denselben gespeicherten
  JPEG-Puffer erneut, ohne ihn zu verbrauchen. Die Herstellerstrategie ist
  damit laufende hostseitige Bildversorgung, nicht ein belegter Geräte-Hold.
- Periodisches Resenden ist für den einzelnen Decode/Commit nicht nötig und
  für dieses Projekt weiterhin weder implementiert noch freigegeben. Vor
  einer Mehrfachframestrategie müssen die nun bekannte 12-ms-Hosttaktung,
  Queue-/Decoder-Lease, Transferdauer, Überlappung, Fehlerabbruch und
  v49-Laufzeitgrenzen gemeinsam bewertet werden.

Die Hoststrategie, Zielperiode und Initialisierungsfolge sind statisch
geschlossen. Ein passiver Mitschnitt einer ohnehin durch InfoHub ausgeführten
statischen Bildauswahl bleibt als v49-Laufzeitabgleich sinnvoll; er soll die
tatsächlichen Transferabstände sowie das einmalige initiale Interface-0-
`0x12` auf dem realen Gerät prüfen, ohne einen eigenen unbekannten Modusbefehl
oder Mehrfachframepfad zu senden.

## Kontrollierte Offline-Refresharchitektur

Design, Grenzen und Testergebnisse stehen in
`research/reports/lcd-refresh-sender-design.md`.

- `src/lcd_refresh.py` ergänzt eine eigenständige Scheduling-Schicht ohne
  HID-Opcode, Paketbuilder, Interface-0- oder IN-Read-Pfad. Sie delegiert einen
  vollständigen Frame ausschließlich synchron an den bestehenden
  `send_frame_once()`-Pfad.
- `RefreshPlan` verlangt ohne Defaultwerte ein explizites
  Transportintervall, eine maximale Laufzeit und eine maximale Frameanzahl.
  Die technischen Hardcaps liegen bei 60 s und 500 vollständigen Frames; sie
  sind keine Freigabe oder Empfehlung für einen Live-Test.
- `RefreshController` kann nur explizit und pro Instanz genau einmal gestartet
  werden. Ein Stop-Event unterbricht Wartezeiten, der nicht als Daemon
  markierte Thread wird gejoint, und jede Session endet spätestens an einem
  Limit oder beim ersten Senderfehler.
- Prozessweite Nonblocking-Locks verhindern zwei parallele Refreshsessions
  sowie zwei gleichzeitig laufende `send_frame_once()`-Aufrufe. Es gibt keine
  Framequeue, keinen Catch-up-Burst, keinen Retry, keine Recovery und keinen
  Autostart. Die Locks koordinieren keine fremden Prozesse; externe
  LCD-Writer müssen vor einem Live-Test gesondert ausgeschlossen werden.
- Das Transportintervall beschreibt die minimale Zielperiode zwischen
  tatsächlichen Startzeitpunkten vollständiger Transfers. Die Transferdauer
  wird gemessen. Ist sie länger als das Intervall, beginnt frühestens nach
  Rückkehr genau der nächste synchrone Transfer; dessen Zeitplan wird neu
  basiert.
- JPEG-Produktion, USB-Übertragungsrate und gewünschte sichtbare Framedauer
  sind getrennt. Der aktuelle Loop erzeugt kein JPEG, sondern verwendet nur
  vollständig vorbereitete Frames. Bei Animationen wird ohne Überspringen
  zyklisch weitergeschaltet; GIF-Loopwerte werden noch nicht ausgeführt.
- `HidrawFrameSender` ist nur ein zukünftiger Adapter. Pro Frame bleiben
  dynamische Interface-1-Revalidierung, kein Retry und das `finally`-Close des
  Einzelframesenders erhalten. GUI und CLI aktivieren diesen Adapter nicht.
- 16 Offline-Refreshtests prüfen Start/Stop, Parallelität, ersten Fehler,
  fehlende Retries, Frame-/Zeitlimits, langsame Transfers, fehlende
  Catch-up-Bursts, statische Wiederverwendung, animierte Reihenfolge,
  GIF-Dauern/Loopwert, das fixierte Ersttestprofil und vollständige
  Mockbarkeit. Die gesamte Suite mit 82 Tests ist erfolgreich.

Es gab in diesem Ticket keine Gerätekommunikation und keinen HID-Write. Ein
Live-Refresh bleibt gesperrt, bis ein eigenes GO/NO-GO-Review eine konservative
Periode und wesentlich kleinere normative Testgrenzen gegen Queue,
Decoder-Lease, Transferdauer und v49-Restunsicherheit festlegt.

## Readiness des ersten kurzen Refresh-Live-Tests

Der abschließende statische Review steht in
`research/reports/lcd-first-refresh-live-readiness.md` und endet mit **GO**
für einen gesondert autorisierten, eng begrenzten Folgetest. In diesem Review
gab es keine Gerätekommunikation und keinen HID-Write; ein Refresh-Live-Test
wurde weiterhin noch nicht ausgeführt.

Das erste Testprofil ist auf die bereits live bestätigte 2236-Byte-
Referenzdatei und ihren SHA-256 festgelegt: ein unveränderliches statisches
JPEG, 1,0 s Abstand zwischen Frame-Startzeitpunkten, höchstens 6,0 s und
höchstens fünf vollständige Frames beziehungsweise 15 Writes. `12 ms` bleibt
nur die InfoHub-Worker-Zielperiode und wird nicht als sichere eigene Rate
übernommen.

`src/lcd_refresh.py` besitzt dafür nun den rein offline arbeitenden Builder
`build_first_refresh_live_test_plan()`. Er akzeptiert ausschließlich den
empirisch bestätigten Referenzhash, fixiert die genannten Grenzen, öffnet kein
Gerät und startet keinen Worker. Der eigentliche Refreshcontroller bleibt ohne
CLI-/GUI-Aktivierung und ohne Autostart.

Die Wiederholung ändert weder Paketformat noch v51-Reachability. Weiter offen
sind ein messbarer Decoder-Done-Zeitpunkt, die Lease-Wandzeiteinheit, die
Framebuffer-Ringgröße und die exakte maximale sichere v49-Rate. Der
Herstellerpfad belegt jedoch wiederholte synchrone Volltransfers ohne IN-Wait;
fünf Referenzeinträge benötigen selbst ohne Freigabe nur 15.320 von 204.800
Queuebytes. Das verbleibende Testrestrisiko ist daher flüchtige Queue-/Decoder-/
Display- oder USB-Störung. Persistente Pfade sind ab v51-`0x08` nicht
erreichbar; für v49 bleibt eine zusätzliche, unbelegte strukturelle Kante
formal unbekannt.

Vor dem gesondert autorisierten Live-Test müssen externe Writer ausgeschlossen,
nur Interface 1 temporär schreibbar gemacht und dessen ursprüngliche Rechte
unmittelbar danach auch im Fehlerfall wiederhergestellt werden. Transporterfolg
(fünf vollständige Frames/15 vollständige Writes) und sichtbarer Erfolg
(Referenzbild bleibt während der aktiven Session ohne Default-Unterbrechung)
sind getrennt zu erfassen; der Code behauptet keinen sichtbaren Erfolg.

## Implementierter Einstieg für den ersten Refresh-Test

Der ausschließlich auf dieses Profil begrenzte Einstieg liegt jetzt in
`src/test_lcd_refresh.py`; Bedienung und Code-Review stehen in
`docs/LCD_REFRESH_TEST.md` und
`research/reports/lcd-first-refresh-test-code-review.md`. In diesem Ticket gab
es keine Gerätekommunikation, keinen hidraw-Open und keinen HID-Write. Der reale
Refresh-Test wurde weiterhin nicht ausgeführt.

Standardaufruf und `--dry-run` sind reine Preview. Nur der nicht abkürzbare
Schalter `--i-understand-the-risk` kann nach vollständig bestandenem Preflight
den Livepfad erreichen. Bild, Hash, `N=3`, fünf Frames, 15 Writes, 1,0 s
Startintervall und 6,0 s Sessiongrenze sind nicht konfigurierbar.

Die read-only Discovery erfasst dafür zusätzlich `bcdDevice`, HID Usage Page/
Usage, USB-Interfaceattribute und beide Endpointprofile. Vor Sessionstart und
vor jedem Write werden Gerät `0b05:1c7b`, ausschließlich Interface 1,
`bcdDevice` numerisch exakt `0x0049`, Usage `ff06/01`, Reportgrößen,
Endpointprofil, Referenzhash,
JPEG, `N` und alle 5×3 vorbereiteten Reports geprüft. Eine lokale `/proc`-
Prüfung bricht bei einem sichtbaren fremden Writer auf genau demselben
Character Device ab; sie beendet keine Prozesse und berührt das getrennte
OpenRGB-Gerät `0b05:19af` nicht.

Im erreichbaren Refreshpfad existiert weiterhin genau eine `os.write()`-
Quelltextstelle in `lcd_transport.py` und keine `os.read()`-Stelle. Der erste
Fehler beendet ohne Retry oder Recovery; jedes per Frame geöffnete Handle wird
im `finally` geschlossen. Der Code meldet ausschließlich Transporterfolg bei
fünf Frames und 15 vollständigen Writes. Ob das Referenzbild ohne
zwischenzeitliches Defaultbild sichtbar bleibt, muss der Benutzer getrennt
beobachten.

Der erste reale Aufruf dieses Einstiegs wurde im Preflight ohne HID-Write
abgebrochen, weil sysfs `bcdDevice` als Rohtext `0049` lieferte und der Code
noch die Darstellungsform `0.49` verglich. Dieser reine Formatfehler ist
behoben: `0049`, `0x0049` und `0.49` werden zum Wert `0x0049` normalisiert;
andere oder fehlerhafte Werte bleiben gesperrt. Der damalige Abbruch lag vor
`run_live()` und konnte die einzige Write-Callsite nicht erreichen.

27 neue Offline-Tests erhöhen die vollständig gemockte Suite auf 109
erfolgreiche Tests. Wegen des gewünschten Einstiegsnamens wurde die bisherige
gleichnamige Controller-Testdatei in `test_lcd_refresh_controller.py`
umbenannt, ohne ihren Inhalt zu ändern. Der Code ist damit für genau den
gesondert autorisierten Live-Test bereit; er ist weiterhin weder in GUI noch
in einen automatischen Startpfad eingebunden.

## Erster begrenzter Refresh-Live-Test 01

Der reale Lauf ist in
`research/reports/lcd-first-refresh-live-test-01.md` dokumentiert. Das Gerät
war `0b05:1c7b` mit `bcdDevice 0.49`; gesendet wurde ausschließlich über
Interface 1 das bekannte 2236-Byte-Referenz-JPEG mit `N=3`.

Die fünf Frame-Starts lagen ungefähr bei 0,000126 s, 1,000215 s, 2,000251 s,
3,000321 s und 4,000398 s. Jeder Transfer dauerte ungefähr 108–109 ms. Alle
15 Writes waren mit jeweils 1025 Byte vollständig; es gab keinen Retry,
Fehler, Catch-up oder Recovery. Wiederholter vollständiger `0x08`-Transport
ist damit für genau diesen Fünfframe-Lauf auf dem realen v49-Gerät empirisch
bestätigt.

Das Referenzbild war real auf dem physischen LCD sichtbar. Die Sichtdauer
wurde jedoch nicht mitgemessen. Damit ist ein sichtbarer Commit während des
Refresh-Laufs bestätigt, nicht aber, dass das Bild das gesamte Testfenster
lückenlos sichtbar blieb, dass das ASUS-Defaultbild sicher nie dazwischen
erschien, wie lange das Bild nach Frame 5 sichtbar blieb oder dass 1,0 s eine
zuverlässige Persistenzrate ist.

In diesem Dokumentationsticket gab es keine weitere Gerätekommunikation und
keinen weiteren HID-Write.

## Vorbereiteter Fallback-Zeitmesstest

Der zweite, weiterhin fest begrenzte Live-Einstieg ist offline vorbereitet;
Design und Evidenzgrenzen stehen in
`research/reports/lcd-refresh-fallback-timing-test-design.md`. In diesem
Vorbereitungsticket gab es keine Gerätekommunikation, keinen hidraw-Open,
keinen HID-Write und keinen neuen Live-Test.

`src/test_lcd_refresh_fallback.py` übernimmt das real bewährte Profil
unverändert: eingefrorenes 2236-Byte-Referenz-JPEG mit festem SHA-256,
`N=3`, exakt fünf Frames, 1,0 s zwischen Frame-Startzeitpunkten, maximal
6,0 s und 15 vollständige Writes. Sämtliche Identitäts-, Descriptor-,
Endpoint-, Versions-, Referenz- und Konkurrenz-Gates bleiben erhalten. Es
gibt weiterhin keinen Retry, Catch-up, Recovery-, Interface-0- oder IN-Pfad
und im erreichbaren Refreshpfad genau eine `os.write()`-Quelltextstelle.

Nach erfolgreicher Rückkehr von Frame 5 ist dessen per Frame geöffnetes
Devicehandle bereits geschlossen. Erst nach vollständigem Ende des
Controllers beginnt eine höchstens 20 Sekunden lange, rein passive
Enter-Beobachtung. `time.monotonic()` erfasst `t_start`, den Abschlusszeitpunkt
des fünften Frames `t_last` und eine manuelle Fallbackmeldung; ausgegeben
werden die Zeiten seit Teststart und seit `t_last`. Ohne Meldung wird nur
festgehalten, dass innerhalb von 20 Sekunden kein Fallback beobachtet wurde.
Nach Frame 5 finden absolut keine weiteren Writes statt.

Sieben zusätzliche Offline-Tests prüfen Reihenfolge und Handle-Close, den
gerätefreien Beobachtungspfad, monotone Differenzen, exakten 20-s-Timeout,
fehlende Writes nach Frame 5 sowie das unveränderte Transportprofil. Die
vollständige gemockte Suite umfasst nun 116 erfolgreiche Tests.

Der spätere Lauf muss Transporterfolg, sichtbares Referenzbild,
Default-Unterdrückung während der aktiven Phase und gemessene Fallbackzeit
weiterhin strikt getrennt dokumentieren. Der Test ist für eine gesonderte
Autorisierung vorbereitet, aber noch nicht ausgeführt. Andere Intervalle,
Bilder oder Laufzeiten bleiben nicht freigegeben.

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

Der Einmaltransfer, der automatische Pipeline-Live-Test und der erste
begrenzte Fünfframe-Refresh-Test sind abgeschlossen und dokumentiert.
InfoHubs Hostrefresh ist statisch geschlossen; der eigene wiederholte
`0x08`-Transport ist bei 1,0 s Sollintervall real transportseitig bestätigt.

Die nächste offene Frage ist nicht mehr die Transportfähigkeit, sondern die
zeitliche Displaywirkung: Ob und wann das ASUS-Defaultbild zwischen oder nach
den Refreshframes erscheint, muss in einem später gesondert freigegebenen Lauf
mit zeitgestempelter Sichtbeobachtung bestimmt werden. Erst danach lässt sich
eine tatsächlich ausreichende Refreshrate bewerten. Andere Intervalle oder
Bilder, `0x1a`-/`0x1f`-Versuche, echte GIF-Animation, Dauerbetrieb und
Fehlerpfadtests bleiben nicht freigegeben. Schreibrechte bleiben deaktiviert.

## Lokale Temperaturen und LCD-Overlay

Die PySide6-GUI zeigt `CPU`, `CPU Package` und `GPU` über eine getrennte,
ausschließlich lesende hwmon-Schicht an. `src/system_sensors.py` erkennt
`k10temp` und `amdgpu` bei jedem Poll dynamisch über `name`, `temp*_label` und
`temp*_input`; wechselnde `hwmonN`-Nummern werden nicht als Geräteidentität
verwendet. Fehlende, verschwundene oder fehlerhafte GUI-Werte erscheinen als
`N/A`.

Der tatsächlich erzeugte 320×320-JPEG-Frame kann optional ein gemeinsames
Temperaturoverlay tragen: oben links `CPU Package / Tctl`, oben rechts
`GPU / edge` der konfigurierten primären GPU `0000:03:00.0` und unten mittig
`CPU CCD / Tccd1`. Fehlende Overlaywerte erscheinen als `—`. Vorschau und
späterer expliziter Einzelbildtransfer verwenden dieselben validierten
JPEG-Bytes. Bei deaktiviertem Overlay bleiben Basisframe und deterministisch
erzeugte JPEG-Bytes unverändert.

Die gemeinsame Farbe für Labels und Werte ist in der GUI frei wählbar, wird
sofort in der Vorschau angewendet und als normalisiertes `#RRGGBB` in QSettings
gespeichert. Default und sicherer Fallback für ungültige gespeicherte Werte ist
Weiß. Das interne Farbmodell besitzt bereits ein Feld pro Sensor, die GUI setzt
heute jedoch bewusst eine gemeinsame Farbe.

Ein Qt-Timer liest ungefähr einmal pro Sekunde. Nur geänderte Sensorwerte lösen
ein Overlay-Re-Rendering aus dem gecachten RGB-Basisframe und eine neue
JPEG-Erzeugung aus. Sensorpolling und Rendering sind nicht mit einem USB-Refresh
verbunden. Vorbereitete GIF-Frames behalten Reihenfolge, Dauer und Loopwert und
können offline mit neuen Werten gerendert werden; die GUI sendet weiterhin
keine GIF-Live-Animation.

Zusätzlich erkannt, aber nicht ins Standardlayout aufgenommen sind `junction`
und `mem` der primären GPU, `edge` einer zweiten GPU, die NVMe-Kanäle
`Composite`, `Sensor 1` und `Sensor 2` sowie ein unbeschrifteter r8169-Kanal.
Weitere CCDs und belegte Mainboard-/Chipsatzwerte bleiben mögliche spätere
Erweiterungen. Details und Evidenzgrenzen stehen in
`research/reports/gui-temperature-monitoring.md` und
`research/reports/lcd-temperature-overlay.md`.

Der Recovery-Audit begann ohne Änderungen und fand keine Konfliktmarker,
abgebrochenen Dateien, Syntax-, Import- oder bestehenden Testfehler. Vor den
Ergänzungen bestanden 131 Offline-Tests. Abschließend bestanden 141 Tests;
`git diff --check` war sauber. Es fanden keine Gerätekommunikation, keine
HID-/USB-Writes und keine Live-Tests statt. LCD-Transport, Refresh-Protokoll und
Fallback-Timing-Pfade blieben unverändert.

### Technische Overlay-Typografie

Das LCD-Temperaturoverlay verwendet nun eine gestufte technische
Monospace-Strategie. Bevorzugt werden `Noto Sans Mono SemiBold` für Labels und
`Noto Sans Mono Bold` für Werte; danach folgen `DejaVu Sans Mono` und
`Liberation Mono`, jeweils in kräftiger Ausprägung. Ist keine dieser Schriften
verfügbar, fällt der Renderer kontrolliert auf Pillows Standardschrift zurück.
Es besteht keine harte Abhängigkeit von einer einzelnen installierten Datei.

Die bevorzugten Größen wurden von 15 auf 13 Pixel für Labels und von 38 auf
33 Pixel für Werte reduziert. Damit ist die Darstellung ungefähr zehn Prozent
kompakter; Semibold/Bold hält sie zugleich klar lesbar. Die bestehenden
Label- und Wertmittelpunkte, Dreiecksanordnung, Rundrandprüfung, Farben und
Preview-/LCD-Renderpfade blieben unverändert. Die vollständige Offline-Suite
bestand danach mit 143 Tests. Es fanden keine Gerätekommunikation, keine
HID-/USB-Writes und keine Live-Tests statt; Transport-, Refresh- und
Sensorverhalten wurden nicht verändert.

## Geplante GUI-/Refreshintegration

Die vorhandenen Grenzen zwischen GUI, Sensorpolling, Overlayrenderer,
JPEG-Encoding, Refreshcontroller und `send_frame_once()` sind vollständig
kartiert. Für das nächste reine Offline-Ticket ist als kleinste Brücke ein
validierender `LatestFrameBuffer` vorgesehen: Der GUI-Thread publiziert darin
atomar nur fertige immutable JPEG-Frames, während der Refreshworker pro Takt
einen Snapshot liest und denselben Puffer zwischen Sensorupdates wiederverwenden
kann. Ein nicht blockierendes `request_stop()` ergänzt später die vorhandenen
`start()`-/`stop()`-/`wait()`-APIs für den Qt-Lebenszyklus.

Das geplante GUI-Modell umfasst `idle`, `starting`, `running`, `stopping` und
`error`. Sensorpolling bleibt bei ungefähr 1 Hz; Overlay/JPEG werden nur bei
geändertem Bild, Overlay oder Sensorstand erzeugt; der USB-Takt bleibt davon
getrennt und ist noch nicht festgelegt. Die gemessenen 108–109 ms pro Transfer
werden bei der späteren konservativen Taktwahl berücksichtigt.

Der Plan implementiert keinen Live-Pfad und ändert weder Controller noch
Transport. Eine spätere Aktivierung bleibt auf `0b05:1c7b`, Interface 1 und
den vorhandenen `0x08`-Sender begrenzt, ohne Autostart, Retry, Interface 0 oder
Parallelwriter. OpenRGB beziehungsweise `0b05:19af` bleiben unberührt. Details:
`research/reports/gui-live-refresh-integration-plan.md`.

### FrameSource und dynamischer Einframe-Refresh

Die Schritte 1 und 2 des GUI-/Refreshintegrationsplans sind offline
implementiert. `FrameSnapshot` hält immutable JPEG-Bytes, Generation und die
bereits durch den bestehenden Validator ermittelten Metadaten. Der
thread-sichere `LatestFrameBuffer` validiert jeden Kandidaten vor seinem kurzen
Lock und ersetzt darunter nur atomar den letzten gültigen Snapshot. Erfolgreiche
Publikationen erhöhen die Generation; ungültige Frames verändern weder Stand
noch Generation. Es existiert keine Framequeue.

`RefreshController` akzeptiert optional eine `FrameSource` für statische
Einframepläne und liest unmittelbar vor jedem Senderaufruf genau einen
Snapshot. Ein laufender Transfer behält seine alte immutable Referenz, während
parallel bereits die nächste Generation publiziert werden kann. Der folgende
Transfer übernimmt erst danach den neuen Stand. Statische Einframepläne und die
bestehende Animationsrotation bleiben unverändert; dynamische Quellen werden
nicht mit Mehrframeplänen vermischt.

`request_stop()` setzt nicht blockierend ausschließlich das vorhandene
Stop-Event; `stop()` verwendet es weiterhin zusammen mit dem bisherigen Join,
und `wait()` bleibt unverändert. 24 gezielte Tests, darunter wiederholte
Konkurrenzläufe, sowie die vollständige Suite mit 152 Tests bestanden offline.
Es gab keine Gerätekommunikation, keine HID-Writes und keine GUI-Live-
Verdrahtung. Nächster offener Schritt ist das weiterhin rein offline geplante
GUI-State-Modell mit injizierbarer Controller-/Senderfabrik.

### GUI-State- und Controller-Integrationslayer

Die Schritte 3 bis 6 des GUI-/Refreshintegrationsplans sind nun offline
implementiert. `GuiRefreshState` modelliert explizit `idle`, `starting`,
`running`, `stopping` und `error`; die zentral abgeleitete UI-Freigabe steuert
`LCD starten`, `LCD stoppen`, den direkten Einzelbildtransfer sowie Bild-,
Skalierungs- und Overlayänderungen. Es gibt keinen Autostart. Beim Schließen
einer laufenden Session wird nicht blockierend `request_stop()` angefordert und
erst nach dem terminalen Workergebnis geschlossen. Ein Transportfehler endet
ohne Retry in `error`; erst eine ausdrückliche Benutzerbestätigung führt nach
`idle` zurück.

Die GUI akzeptiert eine injizierbare `ControllerFactory` auf der schmalen
`RefreshControllerLike`-Schnittstelle. Die Factory erhält ausschließlich die
`FrameSource` der Session. Es existiert bewusst keine Produktions-Factory:
Die GUI erzeugt keinen `HidrawFrameSender`, legt kein Transportintervall fest
und kann ohne explizite Injection keine LCD-Refreshsession starten.

Beim Start wird der vorbereitete, erneut validierte Frame als Generation 1 in
einem sessionspezifischen `LatestFrameBuffer` publiziert. Während `running`
führen erfolgreiche Bild-, Crop/fit-, Overlay-, Farb- und tatsächlich relevante
Sensoränderungen über Basisframe, Overlay, JPEG-Encoding und Validator zu genau
einer atomaren Publikation. Render- oder Validierungsfehler lassen den letzten
gültigen Snapshot und dessen Generation unverändert. Während `stopping` wird
nichts Neues publiziert.

Das vorhandene 1000-ms-Sensorpolling bleibt ausschließlich im GUI-Thread. Nur
geänderte Tctl-, primäre-GPU-edge- oder Tccd1-Werte erzeugen bei aktivem Overlay
ein neues JPEG; ein unveränderter Folgepoll publiziert nichts. Der
Refreshworker liest weder sysfs noch Sensorobjekte.

Fünf neue headless-Qt-Integrationstests verwenden Fake-hwmon,
Fake-Controller und Fake-Sender. Sie prüfen den vollständigen Start-/Snapshot-/
Sensorupdate-/Folgetransfer-/Stop-Pfad, exakt eine Generation pro Änderung,
keine parallelen Transfers, Farb-, Overlay-, Bild- und Skalierungsänderungen,
den letzten gültigen Frame bei Renderfehlern, `error` ohne Retry sowie den
nichtblockierenden Fensterschluss. `os.open()` und `send_frame_once()` wurden im
Fake-End-to-End-Pfad überwacht und nicht erreicht. Die vollständige
Offline-Suite bestand mit 157 Tests; `git diff --check` war sauber. Es fanden
keine Gerätekommunikation, keine HID-/USB-Writes und keine Live-Tests statt.

Der nächste offene Schritt ist ein gesondert freizugebendes Hardwareticket:
eine Produktions-Factory mit realem `HidrawFrameSender`, erneuter sicherer
Geräteprüfung, explizitem konservativem Intervall, begrenzter Sessionpolitik und
GO/NO-GO. Externe Writer und Sichtbarkeitskriterien müssen davor ebenfalls
festgelegt werden. Interface 0, OpenRGB/`0b05:19af`, GIF-Liveanimation und
Dauerbetrieb bleiben ausgeschlossen.

### Produktionsverdrahtung des GUI-Refreshpfads

Die Produktionsverdrahtung ist nun implementiert, aber noch nicht live
ausgeführt. `ProductionControllerFactory` verwendet ausschließlich die
vorhandene dynamische Suche für `0b05:1c7b`/Interface 1, den bestehenden
`HidrawFrameSender`, `RefreshController` und die sessionspezifische
`LatestFrameBuffer`-`FrameSource`. Die GUI erzeugt keine Pakete und verändert
den bestätigten `0x08`-Transport nicht.

Die gemeinsamen Runtime-Safety-Gates wurden aus dem bewährten Fünfframe-
Testwerkzeug in `lcd_runtime_safety.py` überführt und werden von beiden Pfaden
verwendet. Vor dem Start müssen VID/PID, Interface 1, vorhandener Produktname,
`bcdDevice == 0x0049`, Usage `ff06/01`, unnummerierte Reports, Input 16 Byte,
Output 1024 Byte, fehlende Feature-Reports, HID-Interface- und Endpointprofil
sowie ein dynamisch entdeckter `/dev/hidraw*`-Pfad passen. Zusätzlich dürfen
keine lokal erkennbaren fremden Writer denselben Character Device geöffnet
halten. Jeder Fehler beendet den Start vor Sender- und Controllererzeugung und
wird in der GUI ohne Retry als `error` angezeigt.

Für den ersten GUI-Livepfad gilt ein isoliertes temporäres Entwicklungsprofil:
1,0 s minimale Frame-Startperiode, höchstens 30,0 s und höchstens 30
vollständige Frames. Die Werte sind nicht konfigurierbar. Der bestehende
Scheduler verhindert Überlappung und Catch-up; der erste Transportfehler beendet
die Session. Unbegrenzter Dauerbetrieb und Autostart existieren nicht.

Die neue GUI-Option `Hardware-Livebetrieb freigeben` ist bei jedem Programmstart
aus und wird nicht persistent wiederhergestellt. Ohne sie sind sowohl
`LCD starten` als auch der bestehende Einzelbild-Writepfad vor Aufruf der
Produktions-Factory beziehungsweise vor hidraw-Open und Write gesperrt. Mit
Freigabe erzeugt der Startklick über die ProductionFactory genau eine begrenzte
Session. `LCD stoppen` bleibt über
`request_stop()` nicht blockierend; ein laufender synchroner Frame darf samt
`finally`-Close sauber enden.

Das bereits implementierte dynamische Publishing bleibt unverändert:
Sensoränderungen an Tctl, Tccd1 oder primärer GPU-edge, Bild-, Crop/fit-,
Overlay- und Farbänderungen erzeugen während `running` zunächst ein vollständig
validiertes JPEG und publizieren dann atomar eine neue Generation. Der
Refreshworker liest weder sysfs noch Sensorobjekte und verwendet zwischen
Änderungen denselben immutable Snapshot. Renderfehler lassen den letzten
gültigen Stand aktiv.

Neun neue Factory- und zwei zusätzliche GUI-Tests prüfen Fake-Device-
Verdrahtung, sämtliche Safety-Gates, falsche Version, Interface- und
Reportgrößen, Konkurrenzwriter, exakte Ziel-Discovery, 30-s-/30-Frame-Hardcap,
Stop, ersten Fehler ohne Retry und die standardmäßig ausgeschaltete
Hardwarefreigabe. Bestehende Tests decken dynamische Sensor-/Farbpublikation und
fehlende Paralleltransfers ab. Die vollständige Offline-Suite bestand mit 168
Tests; `git diff --check` war sauber. Es fanden keine Gerätekommunikation,
keine HID-/USB-Writes und kein Live-Test statt. Interface 0,
OpenRGB/`0b05:19af` und die Protokollimplementierung blieben unberührt.

Nächster Schritt ist ausschließlich ein gesondert autorisierter, beaufsichtigter
GUI-Live-Test mit temporärer Interface-1-Schreibberechtigung, ausgeschlossenem
Fremdwriter und getrennten Kriterien für Transport, sichtbare Kontinuität,
Stopverhalten sowie das harte 30-s-/30-Frame-Ende. Daraus folgt weiterhin keine
Freigabe für andere Intervalle, Animation oder Dauerbetrieb.

### Erster kontrollierter GUI-Hardware-Live-Test 01

Der einmalig freigegebene GUI-Live-Test wurde ausgeführt und anschließend ohne
zweiten Lauf beendet. Der vollständige Offline-Preflight bestand mit 168 Tests
und sauberem `git diff --check`. Dynamisch erkannt wurden `/dev/hidraw7` als
Interface 0 und `/dev/hidraw8` als Interface 1 desselben Geräts
`0b05:1c7b`. Interface 1 erfüllte sämtliche Production-Gates: Produktname,
`bcdDevice 0x0049`, Usage `ff06/01`, Input 16 Byte, Output 1024 Byte, keine
Feature-Reports, korrektes HID-/Endpointprofil und keine konkurrierenden Writer.

Nur Interface 1 wurde temporär von `0640` auf `0660 root:input` gesetzt;
Interface 0 blieb durchgehend `0640` und effektiv nicht schreibbar. Nach erneut
bestandenem read-only Preflight und ausdrücklicher menschlicher Freigabe wurde
die normale GUI gestartet. Bildwahl, Overlayaktivierung,
Hardware-Livefreigabe, Sessionstart und eine Farbänderung während `running`
erfolgten ausschließlich manuell.

Die GUI blieb responsiv und zeigte Bild, Temperaturwerte sowie die neue Farbe.
Auf dem physischen LCD erschien jedoch weder das ausgewählte Bild noch Tctl,
Tccd1 oder GPU-edge. Das ASUS-Defaultbild lief permanent und ohne beobachtete
Änderung weiter. Damit sind sichtbarer GUI-Framecommit, sichtbare
Temperaturupdates und sichtbare Farbaktualisierung für diesen Lauf nicht
bestätigt. Ob Frames transportseitig ankamen, nicht committed oder sofort vom
internen Defaultproduzenten überstimmt wurden, bleibt ohne persistentes
Transportresultat unbekannt.

Der Refreshworker war nach dem Lauf beendet, kein Gerätewriter war mehr offen
und keine automatische Folgesession startete. Die tatsächliche Framezahl und
Controllerlaufzeit wurden im GUI-Prozess nicht persistent protokolliert und vor
dem Schließen nicht abgelesen; belastbar bestätigt sind deshalb nur die harten
Obergrenzen von 30 vollständigen Frames und 30,0 s, keine erfundenen Istwerte.
Dieser Beobachtungsmangel wird nicht durch einen zweiten Test kompensiert.

Nach Beendigung der senderlosen GUI wurde die temporäre Berechtigung entfernt.
Der Postflight bestätigte beide Interfaces wieder als `0640 root:input`, für
den Benutzer nicht schreibbar, weiterhin ohne konkurrierenden Writer,
GUI-Prozess oder Hintergrundsession. Interface 0 und `0b05:19af`/OpenRGB wurden
nicht beschrieben oder verändert. Details:
`research/reports/gui-first-live-test-01.md`.

Der 30-s-/30-Frame-Entwicklungshardcap darf im nächsten Ticket nicht durch
normalen Dauerbetrieb ersetzt werden. Vor einem weiteren Live-Test müssen
zunächst offline persistente Controller-/Transportdiagnostik und eine gezielte
Auswertung des negativen Sichtbefunds entworfen werden. Andere Intervalle,
Interface-0-Steuerung, weitere Opcodes, GIF-Liveanimation und Dauerbetrieb
bleiben nicht freigegeben.

### Persistente Diagnostik vor GUI-Live-Test 02

Der GUI-Produktionspfad besitzt nun eine sessionspezifische JSONL-Diagnostik
unter `logs/gui-refresh-*.jsonl`. Sie erfasst mit monotonen Zeitstempeln Start,
Factory und Safety-Gates, dynamischen hidraw-Pfad, Controller und Worker,
Snapshotgenerationen, jeden `send_frame_once()`-Aufruf, geplante und
vollständig geschriebene Segmente, Transferergebnis und -dauer, Framezähler,
normalisierten Stopgrund, Exceptions mit Phase sowie Workerende und den vom
unveränderten Transport-`finally` bestätigten Handle-Close. JPEG- und
HID-Payloads werden nicht geloggt; Retry und Recovery wurden nicht ergänzt.

Der statische Vergleich mit `src/test_lcd_refresh.py` fand keinen zweiten oder
abweichenden Transportaufruf. Beide Pfade enden in demselben
`lcd_transport.send_frame_once()`. Der erfolgreiche Fünfframe-Test verwendete
jedoch ein fixes Referenz-JPEG, vorbereitete Drei-Segment-Frames und einen
lokalen `write_observer`, während die GUI dynamische `LatestFrameBuffer`-
Snapshots verwendete und ihr Resultat bislang nur im Prozessspeicher hielt.
Dies ist eine belegte Diagnoselücke, aber kein nachgewiesener funktionaler
Transportbug.

Der neue Fake-End-to-End-Test durchläuft GUI, echte ProductionFactory,
RefreshController, `FrameSource.snapshot()`, bestehenden HidrawFrameSender und
einen Fake an der `send_frame_once()`-Gerätegrenze. Er bestätigt exakt 30
Senderaufrufe, 90 simulierte vollständige Segment-Writes, Framezähler 30,
keine Parallelität und terminal `30 Frames`; ein reales `os.open()` ist
verboten und wurde nicht erreicht. Die vollständige Offline-Suite bestand mit
171 Tests; `git diff --check` und `compileall` waren sauber. In diesem Ticket
fanden keine Gerätekommunikation, keine HID-Writes und kein Live-Test statt.

Beim nächsten gesondert freigegebenen manuellen Live-Test können damit
Transporterreichbarkeit, verwendete Generation, Teil-/Vollwrites,
Transferzeiten, tatsächliche Framezahl und Laufzeit, Stopgrund, Exceptions,
Workerende und Handle-Close nach Prozessende ausgewertet werden. Der
30-s-/30-Frame-Hardcap bleibt bis zu diesem Nachweis unverändert. Details:
`research/reports/gui-live-transport-diagnostics.md`.

### Konfigurierbare LCD-Telemetrie und Rotation

Die GUI rotiert die vollständige fertige 320×320-Komposition per Button im
Uhrzeigersinn durch 0°, 90°, 180° und 270°. Der eindeutige Renderpfad ist nun
in `compose_lcd_frame()` zusammengefasst: ungedrehtes 320×320-Basisbild,
Datenoverlay, einmalige Rotation der gesamten RGB-Komposition, JPEG-Encoding
und bestehende Validierung. Die separate ungedrehte Originalvorschau wurde
entfernt; die einzige LCD-Preview decodiert exakt dieselben JPEG-Bytes wie der
spätere `LatestFrameBuffer`-Snapshot. Asymmetrische Pixeltests bestätigen
Hintergrund und vier Overlayblöcke gemeinsam und ohne Doppelrotation.

Das konfigurierbare Overlay besitzt jetzt ein symmetrisches 2×2-Layout mit
oben links, oben rechts, unten links und unten rechts. Alle vier Positionen
haben unabhängige Dropdowns und geprüfte, nicht überlappende Grenzen innerhalb
des runden Sicherheitsbereichs. Neue Defaults sind CPU-Auslastung,
GPU-Auslastung, CPU Package/Tctl und GPU edge. Das allgemeine ID-basierte
Metric-Modell bietet außerdem CPU CCD/Tccd1, junction/hotspot, mem sowie `Aus`.
Fehlende Werte erscheinen als `—`, Lastwerte mit `%` und Temperaturen mit
`°C`.

Winkel, Overlayfarbe/-zustand und alle vier Slotbelegungen werden in
`QSettings` persistiert. Bei alten Drei-Slot-Einstellungen bleiben gültige
Werte für oben links und oben rechts erhalten; `bottom_center` wird nach
unten links migriert und der neue Slot unten rechts erhält den sicheren
GPU-Temperatur-Default. Ungültige IDs fallen auf den jeweiligen neuen Default
zurück.

Gesamt-CPU-Last wird ohne Sleep aus zwei aufeinanderfolgenden `/proc/stat`-
Samples berechnet. GPU-Last kommt read-only aus `gpu_busy_percent` am dynamisch
aufgelösten PCI-Gerätepfad derselben primären AMD-GPU wie der edge-Sensor;
card- und hwmon-Nummern bleiben dynamisch. Nur eine sichtbare Änderung einer
ausgewählten Metrik erzeugt im ungefähr 1-Hz-Poll ein neues validiertes JPEG.
Rotation, Slotwahl und Farbe publizieren während `running` sofort eine neue
Generation, ohne Sessionneustart. Der Worker liest weiterhin keine Sensoren.

Der alte GUI-Button `Auf Display senden` samt direktem Einmal-Sendecode wurde
entfernt. Der bestätigte Transport und die CLI-/Testwerkzeuge bleiben
unverändert. `LCD starten`, `LCD stoppen`, `Gerät aktualisieren` und die
standardmäßig ausgeschaltete Entwicklungs-Hardwarefreigabe bleiben bestehen;
deren späterer Cleanup wird zusammen mit der Dauerbetriebspolitik geprüft.
Der 30-s-/30-Frame-Hardcap blieb unverändert.

Die vollständige Offline-Suite bestand mit 188 Tests; `git diff --check` und
`compileall` waren sauber. Kein hidraw-Open, kein HID-/USB-Write und kein
Live-Test fanden statt. Details:
`research/reports/lcd-configurable-telemetry.md`.
