# Lokale Temperaturanzeige der GUI

Datum: 2026-09-03

## Ziel und Grenzen

Die bestehende PySide6-Oberfläche zeigt CPU-, CPU-Package- und GPU-Temperatur
aus dem lokalen Linux-hwmon-Dateisystem an. Die Sensorschicht arbeitet
ausschließlich lesend unter `/sys/class/hwmon/`. Sie verwendet kein Netzwerk,
keine Cloud, keine Telemetrie, keinen externen Monitoringdienst und benötigt
keine Root-Rechte.

Dieser Arbeitsblock verändert weder LCD-Refresh-, JPEG-, GIF- noch
HID-Transportlogik. Es fand keine Gerätekommunikation und kein HID-Write statt.
Der vorbereitete Fallback-Zeitmesstest blieb unverändert.

## Sensorarchitektur

`src/system_sensors.py` trennt Discovery, Quellenmodell und Sampling von der
GUI. Bei jedem Sample werden `hwmon*`-Verzeichnisse neu gesucht. Die Zuordnung
verwendet den Inhalt von `name`, die tatsächlich angebotenen `temp*_label` und
die zugehörigen `temp*_input`-Dateien; eine bestimmte `hwmonN`-Nummer wird
nicht vorausgesetzt.

Für `k10temp` gelten folgende konservative Rollen:

- `Tdie`, `CPU`, `CPU Temp` oder `CPU Temperature` können `CPU` liefern.
- `Tctl`, `Tctl/Tdie`, `CPU Package`, `Package` oder `Package id N` können
  `CPU Package` liefern.
- Andere Kanäle bleiben in der Discovery sichtbar, werden aber nicht ohne
  belegte Semantik als einer der beiden Gesamtwerte ausgegeben.

Für `amdgpu` wird `edge` als primärer GPU-Wert bevorzugt. Fehlt er, können ein
expliziter allgemeiner GPU-Labelwert und danach `junction`/`hotspot` dienen.
Alle GPU-Kanäle bleiben im Discovery-Modell erhalten, sodass `junction` und
`mem` später separat ergänzt werden können. Bei mehreren AMD-GPUs gewinnt bei
gleichem Primärlabel zunächst das Gerät mit dem reicheren Temperaturprofil;
anschließend dient der aufgelöste sysfs-Gerätepfad als stabile Reihenfolge.
Die Auswahl hängt daher nicht von einer wechselnden `hwmonN`-Nummer ab.

`temp*_input` wird als ganzzahliger Milligrad-Celsius-Wert gelesen und in Grad
Celsius konvertiert. Nicht lesbare, verschwundene, nicht ganzzahlige oder
außerhalb des plausiblen Bereichs liegende Werte werden als nicht verfügbar
behandelt. Die Discovery läuft bei jedem Poll erneut, sodass verschwundene
Sensoren und eine Umnummerierung nach Neustart keinen gecachten, veralteten
Pfad hinterlassen.

## Tatsächliche Zuordnung dieses Systems

Die folgende Bestandsaufnahme ist direkt aus dem lokalen sysfs gelesen. Die
damaligen Namen `hwmon2`, `hwmon3` und `hwmon4` sind nur eine Momentaufnahme und
keine Identität.

| GUI-Wert | Zuordnung | Begründung |
| --- | --- | --- |
| `CPU` | nicht verfügbar | `k10temp` bietet `Tctl` und `Tccd1`, aber keinen separaten `Tdie`- oder allgemeinen CPU-Kanal. `Tccd1` ist ein CCD-Wert und wird nicht als Gesamt-CPU-Wert umbenannt. |
| `CPU Package` | `k10temp` → `Tctl` → `temp1_input`, Gerät `0000:00:18.3` | `Tctl` ist der tatsächlich vorhandene Package-/Control-Kandidat. |
| `GPU` | `amdgpu` → `edge` → `temp1_input`, Gerät `0000:03:00.0` | Dieses AMD-GPU-Gerät bietet zusätzlich `junction` und `mem` und wird gegenüber dem zweiten reinen `edge`-Profil bevorzugt. |

Ein zweites `amdgpu`-Gerät unter `0000:0e:00.0` bietet ebenfalls `edge`. Es
wird erkannt, ist aber nach der beschriebenen geräteunabhängigen Auswahl nicht
die primäre GUI-Quelle. Auf `0000:03:00.0` bleiben `junction` und `mem` für eine
spätere Erweiterung erhalten.

Insbesondere wird `Tctl` nicht zusätzlich als `CPU` dupliziert. Die GUI zeigt
damit auf diesem System bewusst `CPU: N/A` und `CPU Package: <Tctl-Wert>`, statt
denselben oder semantisch ungeeigneten Wert unter zwei Namen auszugeben.

## GUI und Polling

Die vorhandene dunkle Kartenoptik wurde um die Karte `Lokale Temperaturen`
ergänzt. Sie enthält gut sichtbar `CPU`, `CPU Package` und `GPU`, jeweils mit
Wert und tatsächlichem hwmon-/Sensorlabel. Fehlende Werte erscheinen als
`N/A`.

Ein parent-gebundener Qt-`QTimer` stößt alle 1000 ms genau ein lokales Sample
an. Es gibt keine eigene blockierende Schleife und keine Verbindung zwischen
dem Polling und einem HID-, LCD- oder Transportpfad. Fehler eines Samples
setzen die Anzeigen auf nicht verfügbar und beenden die GUI nicht.

## Offline-Prüfungen

Temporäre Fake-hwmon-Verzeichnisse prüfen CPU- und Package-Erkennung,
GPU-`edge`, mehrere Labels und Geräte, fehlende Sensoren, fehlerhafte Eingaben,
Milligrad-Konvertierung, dynamische Nummern, erneute Discovery nach
Umnummerierung, verschwundene Dateien und die priorisierte Mehrfach-GPU-
Auswahl. Der headless Qt-Test prüft zusätzlich `N/A` und das 1000-ms-Intervall.

Alle Sensortests verwenden ausschließlich temporäre Verzeichnisse. Die GUI-
Tests injizieren einen lokalen Sensorreader und mocken die LCD-Geräteerkennung;
es erfolgen keine echten HID-Zugriffe. Die vollständige Offline-Suite endete
mit 129 erfolgreichen Tests. Zusätzlich wurden die vier betroffenen Python-
Dateien erfolgreich per AST geparst; Ruff ist auf dem System nicht installiert.
