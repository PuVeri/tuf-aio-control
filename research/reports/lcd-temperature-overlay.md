# LCD-Temperaturoverlay und gemeinsame Schriftfarbe

Datum: 2026-09-03

## Ziel und Sicherheitsgrenze

Der tatsächlich erzeugte 320×320-LCD-Frame kann drei lokale Temperaturen über
dem weiterhin sichtbaren Basisbild darstellen. Vorschau und später explizit
gesendeter Einzelbild-Frame verwenden dieselben JPEG-Bytes. Dieser Arbeitsblock
blieb vollständig offline: keine Gerätekommunikation, keine HID-/USB-Writes und
keine Live-Tests. Der bestätigte LCD-Transport und das Refresh-Protokoll wurden
nicht verändert.

## Recovery-Audit nach dem Stromausfall

Der vorgefundene Working Tree enthielt keine Konfliktmarker, abgebrochenen
Dateien, Syntaxfehler oder Importfehler. Vor jeder Ergänzung bestand die
vollständige Offline-Suite mit 131 Tests; `git diff --check` meldete keinen
Fehler. Transport- und Refresh-Dateien waren unverändert.

Bereits vollständig oder weitgehend vorhanden waren:

- read-only hwmon-Discovery und Polling im getrennten Sensormodul,
- die explizite Auswahl von `Tctl`, `Tccd1` und `edge` der konfigurierten
  primären AMD-GPU,
- das Drei-Sensor-Datenmodell und ein gemeinsamer Overlay-Renderer,
- die Integration in das validierte JPEG, das Vorschau und Sendepfad nutzen,
- das gecachte RGB-Basisbild für Neuberechnung ohne erneutes sysfs-Lesen,
- GUI-Schalter, gemeinsamer Farbwähler und QSettings-Persistenz,
- Weiß als sicherer Default und Normalisierung auf `#RRGGBB`.

Offensichtlich noch nicht abgeschlossen waren die gezielten Tests für Layout,
Overlay an/aus, Formate, Farbe, Persistenz und Polling-Trennung sowie dieser
Bericht. Außerdem fehlte eine Funktion, mit der bereits vorbereitete
GIF-Frames bei neuen Temperaturen neu gerendert werden können, ohne Reihenfolge
oder Timing anzutasten. Der vorzeitig ergänzte Abschnitt in
`docs/CURRENT_STATE.md` enthielt noch den Zwischenstand von 129 Tests.

## Layout und Rendering

Das Standardlayout bildet ein Dreieck innerhalb des runden Displays:

| Position | Anzeige | Label-Mitte | Wert-Mitte |
| --- | --- | ---: | ---: |
| oben links | `CPU Package / Tctl` | `(102, 66)` | `(102, 100)` |
| oben rechts | `GPU / edge` | `(218, 66)` | `(218, 100)` |
| unten mittig | `CPU CCD / Tccd1` | `(160, 216)` | `(160, 250)` |

Labels werden kleiner als Werte gesetzt. Jeder Block wird vor dem Zeichnen
gegen die rechteckige Sicherheitszone `(24, 24)` bis `(296, 296)` und einen
runden sicheren Radius von 148 Pixeln um `(160, 160)` geprüft. Werte erscheinen
mit `°C`; ein fehlender oder nicht endlicher Wert wird als `—` dargestellt.
Eine schwarze Kontur verbessert die Lesbarkeit, ohne das Hintergrundbild zu
verdecken.

`src/image_pipeline.py` hält für jedes vorbereitete Bild den unveränderten
320×320-RGB-Basispuffer. Der gemeinsame Renderer erzeugt daraus sowohl die
GUI-Vorschau als auch genau die JPEG-Bytes, die der bestehende explizite
Einzelbildpfad später verwenden würde. Bei deaktiviertem Overlay bleiben
Basispixel und deterministisch erzeugte JPEG-Bytes unverändert. HID- und
Transportcode kennen weder Sensoren noch Overlaydetails.

## Farbe und Persistenz

Die GUI bietet eine gemeinsame frei wählbare Farbe für Labels und Werte. Sie
wird sofort auf die Vorschau angewendet und unter
`lcd_temperature_overlay/color` in den vorhandenen QSettings gespeichert.
Gespeichert wird normalisiertes `#RRGGBB`; Default ist `#FFFFFF`. Ungültige
Werte werden beim Start auf Weiß zurückgesetzt und in sicherer Form
zurückgeschrieben.

Das Renderingmodell besitzt intern bereits getrennte Felder für CPU Package,
GPU und CPU CCD. Die GUI setzt diese heute bewusst gemeinsam, sodass spätere
sensorindividuelle Farben ohne Änderung des Rendervertrags ergänzt werden
können.

## Aktualisierungsmodell und GIF

Der GUI-Timer ruft ungefähr einmal pro Sekunde genau den injizierbaren
Sensorreader auf. Nur geänderte Overlaywerte lösen eine Neuberechnung aus einem
gecachten Basispuffer aus. Sensorpolling, Overlay-Rendering und JPEG-Encoding
sind damit vom USB-Refresh getrennt. Ein USB-Write bleibt ausschließlich über
den vorhandenen expliziten Sendeklick erreichbar; es wurde kein Live-Refresh
aktiviert.

Die GIF-Vorbereitung behält Source-Index, Framedauer, Reihenfolge und Loopwert.
Bereits vorbereitete Frames lassen sich nun gemeinsam mit neuen
Temperaturwerten aus ihren gecachten Basispuffern neu rendern. Die GUI und der
Sendepfad behandeln GIF weiterhin ausschließlich als Standbild aus Frame 0;
eine GIF-Live-Animation wird nicht gesendet.

## Read-only Sensorinventar dieses Systems

Die Namen sind eine Momentaufnahme von sysfs; `hwmonN` ist keine stabile
Identität.

| Gerät/Quelle | Erkannte Temperaturkanäle | Verwendung |
| --- | --- | --- |
| `k10temp`, `0000:00:18.3` | `Tctl`, `Tccd1` | Standard: CPU Package und CPU CCD |
| `amdgpu`, `0000:03:00.0` | `edge`, `junction`, `mem` | Standard: nur `edge`; `junction` und `mem` sind Kandidaten |
| `amdgpu`, `0000:0e:00.0` | `edge` | zusätzliche GPU, nicht im Standardlayout |
| `nvme`, NVMe 0 | `Composite`, `Sensor 1`, `Sensor 2` | mögliche Laufwerkstemperaturen |
| `r8169_0_a00:00` | unbeschrifteter `temp1` | ohne belegte Semantik kein Standardkandidat |
| `asus`/WMI | keine Temperaturkanäle | keine Anzeige |

Sinnvolle spätere Erweiterungen sind GPU-Junction/Hotspot, GPU-Speicher,
weitere CCDs, NVMe sowie belegte Mainboard-/Chipsatzwerte. Sie werden nicht
automatisch in das Dreiecks-Standardlayout aufgenommen.

## Offline-Prüfungen

Die Tests decken Layout und runden Randabstand, Tctl/Tccd1/primäre GPU,
fehlende Werte, Overlay an/aus, PNG/JPEG/GIF, Standard- und benutzerdefinierte
Farbe, Speicherung/Wiederherstellung, ungültige gespeicherte Farbe, identische
Preview-/LCD-JPEG-Erzeugung, getrenntes Sensorpolling, erhaltene GIF-Zeitdaten
und blockierte HID-/USB-Aufrufe ab. Das abschließende Gesamtergebnis wird im
Projektstatus festgehalten. Die vollständige Offline-Suite bestand mit 141
Tests; `git diff --check` blieb ohne Befund.
