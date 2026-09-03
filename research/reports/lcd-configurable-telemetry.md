# Konfigurierbare LCD-Telemetrie und Rotation

Datum: 2026-09-03

## Umfang und Sicherheitsgrenze

Die normale GUI unterstützt nun eine vollständige LCD-Rotation in
90-Grad-Schritten sowie drei frei belegbare Datenpositionen. Die read-only
Systemsensorschicht liefert zusätzlich Gesamt-CPU- und primäre AMD-GPU-
Auslastung sowie GPU-Hotspot- und GPU-Speichertemperatur.

Dieses Ticket führte keine Gerätekommunikation, kein hidraw-Open, keine
HID-/USB-Writes und keinen Live-Test aus. `lcd_transport.py`, der bestätigte
`0x08`-Transport und das bestehende Entwicklungsprofil von 1,0 s, maximal
30,0 s und maximal 30 Frames wurden nicht verändert.

## Rotation der vollständigen Komposition

Der Button `LCD drehen: <Winkel>°` schaltet im Uhrzeigersinn durch
`0 → 90 → 180 → 270 → 0`. Die Bildpipeline hält weiterhin das skalierte,
ungedrehte 320×320-RGB-Basisbild im Cache. Bei jeder Ausgabe gilt nun:

```text
Basisbild 320×320
-> Datenoverlay an den logischen Positionen
-> vollständige RGB-Komposition rotieren
-> JPEG kodieren
-> ASUS-JPEG validieren
-> Preview und gegebenenfalls LatestFrameBuffer.publish()
```

Damit drehen Basisbild, Labels und Werte als Einheit. Die logischen
Overlaykoordinaten bleiben oben links, oben rechts und unten Mitte; erst das
fertige Ergebnis wird ohne Resampling per Pillow-Transpose gedreht. Die GUI-
Preview decodiert exakt dieselben validierten JPEG-Bytes, die als späterer
LCD-Snapshot bereitliegen.

Der Winkel liegt in den bestehenden `QSettings` unter
`lcd_output/rotation_degrees`. Nur 0, 90, 180 und 270 sind gültig; jeder andere
gespeicherte Wert wird auf 0 zurückgesetzt. Eine Änderung während `running`
rendert und publiziert eine neue Generation, ohne Controller oder Session neu
zu starten.

## Bereinigte GUI

Der veraltete Button `Auf Display senden` und sein GUI-spezifischer direkter
Einmal-Sendepfad wurden entfernt. Der gemeinsame bestätigte Transportcode und
die eigenständigen Test-/CLI-Werkzeuge bleiben bestehen.

`Bild auswählen`, `Gerät aktualisieren`, `LCD starten`, `LCD stoppen` und
`Fehler bestätigen` bleiben erhalten. Die bestehende Entwicklungsoption
`Hardware-Livebetrieb freigeben` bleibt unverändert standardmäßig aus und
weiterhin Voraussetzung für `LCD starten`. Ihre mögliche Entfernung oder
Umgestaltung gehört zusammen mit der späteren Dauerbetriebspolitik in ein
eigenes Safety-Ticket.

## CPU-Auslastung

`CpuUsageSampler` liest ausschließlich die aggregierte `cpu`-Zeile aus
`/proc/stat`. Beim ersten gültigen Sample wird nur der kumulative
Zählerstand gespeichert und N/A geliefert. Jeder spätere ungefähr 1-Hz-GUI-
Poll berechnet aus Gesamt- und Idle-Deltas:

```text
usage = 100 * (delta_total - delta_idle) / delta_total
```

Idle enthält `idle + iowait`; die summierten Gesamtzähler umfassen user, nice,
system, idle, iowait, irq, softirq und steal, ohne die bereits in user/nice
enthaltenen guest-Zähler doppelt zu zählen. Es gibt keinen Sleep und keine
blockierende Zwischenmessung. Fehlende, leere, malformed, rückläufige oder
zeitlich nicht fortgeschrittene Samples liefern N/A. Gültige Ergebnisse sind
auf 0–100 % begrenzt.

## GPU-Auslastung und zusätzliche Temperaturen

Die GPU-Quelle bleibt an dieselbe konfigurierte primäre PCI-Adresse gebunden,
die bereits für `edge` verwendet wird. Die dynamische hwmon-Erkennung löst den
`device`-Symlink des passenden `amdgpu`-Eintrags auf; an genau diesem
PCI-Gerätepfad wird `gpu_busy_percent` gelesen. Es wird weder eine card- noch
eine hwmon-Nummer fest codiert. Andere GPUs werden nicht als Fallback für die
primäre GPU verwendet.

Ganzzahlen von 0 bis 100 sind gültig. Fehlende, unlesbare, malformed oder
außerhalb des Bereichs liegende Inhalte liefern N/A. Am selben primären Gerät
werden außerdem `junction` beziehungsweise `hotspot` und `mem` dynamisch als
GPU-Hotspot- und GPU-Speichertemperatur gelesen.

## Allgemeines Metric-Modell

`src/telemetry.py` trennt stabile interne Identität von Darstellung und
Sensorquelle. `MetricId`, `MetricDefinition` und `MetricValue` liefern ID,
kurze Displaybezeichnung, numerischen Wert, Einheit, optionales Quelllabel und
den berechneten Verfügbarkeitsstatus. Der Renderer erhält fertige
`MetricValue`-Objekte und enthält keine Fallunterscheidung anhand deutscher
Labels oder bestimmter Sensorarten.

Verfügbar sind:

- `cpu_usage`: CPU, `%`;
- `gpu_usage`: GPU, `%`;
- `cpu_package`: CPU Package, `°C`;
- `cpu_ccd`: CPU CCD, `°C`;
- `gpu_temperature`: GPU Temperatur, `°C`;
- `gpu_hotspot`: GPU Hotspot, `°C`;
- `gpu_memory`: GPU Memory, `°C`;
- `off`: Aus, ohne Renderblock.

Ein fehlender Wert erscheint als `—`; verfügbare Messwerte werden ganzzahlig
mit `%` beziehungsweise `°C` dargestellt. Weitere Definitionen wie RAM,
Lüfter oder NVMe können später durch einen neuen Sensoradapter und eine neue
Metric-Definition ergänzt werden, ohne Layout- oder Zeichenlogik zu ändern.

## Drei unabhängige Slots

Die GUI besitzt je ein Dropdown für `Oben links`, `Oben rechts` und
`Unten Mitte`. Jeder Slot kann unabhängig jede Metric-ID oder `Aus` wählen.
Die Defaults entsprechen dem bisherigen Layout:

- oben links: CPU Package / Tctl;
- oben rechts: GPU Temperatur / edge;
- unten Mitte: CPU CCD / Tccd1.

Gespeichert wird unter `lcd_data_slots/<slot>` ausschließlich die stabile
Metric-ID. Eine unbekannte oder veraltete ID fällt pro Slot auf dessen eigenen
Default zurück. Schriftfamilien, Größen, Gewicht, Farbe, logische Positionen
und runder Sicherheitsbereich bleiben erhalten.

Rotation, Slotauswahl, Overlayzustand und Farbe lösen unmittelbar einen
Rerender aus. Beim ungefähr 1-Hz-Telemetriepoll wird nur die sichtbare Signatur
der ausgewählten Slots verglichen; Änderungen an nicht ausgewählten Metriken,
Quellpfaden oder an Nachkommastellen ohne sichtbare Rundungsänderung erzeugen
keine neue Generation. Der Refreshworker erhält weiterhin ausschließlich
fertige immutable JPEG-Snapshots und liest weder hwmon, `gpu_busy_percent`
noch `/proc/stat`. Es existieren weder Framequeue noch Sessionneustart.

## Offline-Tests

Die erweiterten Tests decken ab:

- exakte 0°-/90°-/180°-/270°-Rotation und Rückkehr nach vier Klicks;
- Rotation der fertigen Komposition vor JPEG-Encoding sowie Identität von
  Preview- und Snapshot-JPEG;
- Winkelpersistenz und Fallback eines ungültigen Settingswerts auf 0°;
- korrekte CPU-Deltas für 0 %, 50 % und 100 %, ersten Sample, fehlende und
  malformed Daten;
- dynamische primäre AMD-GPU-Auswahl bei mehreren GPUs,
  `gpu_busy_percent`, junction/hotspot und mem einschließlich aller N/A-Fälle;
- alle stabilen Metric-IDs, Einheiten, Verfügbarkeit und Gedankenstrich für
  fehlende Werte;
- unabhängige Slots, `Aus`, Defaults, Persistenz und Fallback veralteter IDs;
- neue Generation bei Rotation, Slot- oder sichtbarer Auslastungsänderung
  während `running`, ohne neuen Controller und ohne doppeltes Publishing bei
  unverändertem sichtbarem Wert;
- gesperrte reale `os.open()`- und `send_frame_once()`-Callsites in den
  Runtime-Tests.

Die vollständige Offline-Suite bestand mit 185 Tests. `git diff --check` und
`compileall` waren sauber. Es gab keinen Gerätezugriff und keinen Live-Test.
