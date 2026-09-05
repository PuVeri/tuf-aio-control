# GIF-Rendering: letzter Efficiency-Block vor V1

Stand: 2026-09-06. Implementierung und Offline-Prüfung am 2026-09-05/06;
der manuelle CPU-/Sichttest wurde anschließend live ausgeführt.

## Reale Ausgangslage und Geltungsbereich

Vom Benutzer für einen Ryzen 7 9800X3D mit Linux `top` berichtet:

| Zustand | CPU-Anteil eines logischen Threads |
| --- | --- |
| GIF, GUI sichtbar, LCD aktiv | etwa 41–45 %; 44,9 / 42 / 41 / 42 / 43 / 41 |
| GIF, GUI sichtbar, LCD gestoppt | etwa 40–42 %; 39,9 / 40 / 40 / 42 / 40 / 40 |
| PNG / statisches Bild | etwa 0–2 % |
| Idle / Tray ohne aktive Animation | zuvor praktisch 0 % |

Die erhöhte Lüfterdrehzahl ist eine Benutzerbeobachtung. Die bereits manuell
bestätigte flüssige GIF-Wiedergabe liegt im beobachteten Ausschnitt bei ungefähr
29–32 FPS, Segmentwrites bei 0,12–0,13 ms und ein vollständiger Transfer mit
14 Segmenten bei 2,6–3,4 ms. Diese Hardwarebefunde stammen aus dem Auftrag und
dem vorherigen Transportticket, nicht aus dieser Arbeit. USB/hidraw wird hier
nicht als Performanceengpass behandelt.

Dieser Block verändert weder GIF-Dauern/Geschwindigkeitsfaktoren noch die
Scheduler, Senderperiode, Frameorder, Handshake, JPEG-Parameter oder das
bestätigte Protokoll.

## Finaler manueller CPU-/Sichttest

Der anschließende Live-Test auf einem Ryzen 7 9800X3D bestätigt den
GIF-Rendering-/Efficiency-Block für V1. Die reale GIF-Wiedergabe auf dem AIO
blieb sichtbar flüssig; es gab keine FPS-Reduktion und keine Frame-Skips.
Telemetrie und Rotation blieben korrekt. Der persistente HID-Transport blieb
unverändert.

| Zustand | Vorher | Nachher |
| --- | ---: | ---: |
| GIF sichtbar, LCD läuft | etwa 41–45 % | 11,9 % |
| GIF sichtbar, LCD gestoppt | etwa 40–42 % | 3,5 % |
| GIF im Tray verborgen, LCD gestoppt | praktisch 0 % beobachtet | zunächst 2,7 %, nach kurzer Ruhephase 0,0 % |
| GIF im Tray verborgen, LCD läuft | nicht separat als CPU-Wert dokumentiert | 11,5 % |
| PNG, LCD läuft | etwa 0–2 % | 0,3 % |

Alle Angaben sind Anteile eines logischen CPU-Threads aus der realen Messung;
sie sind keine Ableitung aus dem Offline-Benchmark. Der Befund bestätigt, dass
die hohe Ausgangslast im GIF-Renderingpfad lag und nicht im USB-/hidraw-
Transport.

## Nachvollzogener Baseline-Codepfad

Ausgangspunkt ist der saubere Repositorystand `4941d3c`. Maßgebliche Callsites:
`src/image_pipeline.py`, `src/tuf_aio_gui.py`, `src/gif_animation.py`,
`src/lcd_refresh.py`, `src/lcd_transport.py`, `src/system_sensors.py` und
`src/telemetry.py`.

### Beim Laden

`MainWindow.load_image()` → `prepare_gif()` → Pillow `Image.open()` und
`source.seek/load()` je Quellframe. Pillow erledigt GIF-Disposal und Compositing
beim sequenziellen Laden. Danach folgen `convert("RGBA").copy()`,
`ImageOps.exif_transpose()`, `_rgb_on_black()` mit Alpha-Komposition auf Schwarz,
`_scale_image()` mit LANCZOS-Crop/Fit und `tobytes()`.

Die immutable `PreparedAnimation.frames` enthalten bereits alle 320×320-RGB-
Basisframes, Dauern und Loop-Metadaten. Die Baseline encoded und validiert
zusätzlich alle Basis-Kompositionen als JPEG beim Laden. Diese JPEG-Caches
werden vom laufenden GUI-Renderer nicht wiederverwendet; sogar Frame 0 wird
danach nochmals über `render_prepared_animation_frame()` erzeugt.

### Je Animationsframe

Die sichtbare Preview wird durch `_animation_timer` (Single-Shot) und
`_advance_gif_animation()` → `_advance_preview_animation()` geführt. Das LCD
verwendet den eigenen `_lcd_animation_scheduler` mit
`_request_transport_frame()` → Qt-Signal → `_produce_transport_frame()`;
`_transport_animation_timer` wartet gegebenenfalls nur die noch fehlende Dauer.
Beide rufen unabhängig `_prepare_animation_frame()` auf:

```text
PreparedAnimation.frames[index].base_rgb_bytes       # Lookup, kein GIF-Decode
→ compose_lcd_frame(): Image.frombytes("RGB")
→ render_data_overlay(): convert("RGB").copy()
→ layout_data_overlay(): Fonts laden, Auto-Fit, Bounding-Boxes, Sicherheitsrand
→ Fonts erneut laden/fitten; acht Texte mit Stroke zeichnen
→ rotate_composition(): Transpose bzw. Kopie bei 0°
→ _encode_jpeg(): BytesIO, Pillow JPEG quality=60 / subsampling=2
→ validate_jpeg(): Marker-/Profilprüfung, kein Pixel-Decode
```

Für die Preview folgen `_load_final_preview()` →
`QPixmap.loadFromData(jpeg, "JPEG")` → JPEG-Pixeldecode in Qt →
`pixmap.scaled(..., SmoothTransformation)` → `QLabel.setPixmap()`.
`_show_prepared_image()` aktualisiert zusätzlich pro Preview-Frame sämtliche
Metadaten und Control-States. Die Baseline erzeugt diese JPEGs selbst dann,
wenn das LCD gestoppt ist.

Für das LCD folgen `_publish_running_frame()` → `LatestFrameBuffer.publish()`:
erneute JPEG-Validierung vor dem kurzen Condition-Lock, genau ein neuer frozen
`FrameSnapshot` mit unveränderlichen JPEG-Bytes, Generation und Metadaten;
keine Queue. Der Worker übernimmt unter kurzem Lock einen Snapshot und ruft
den persistenten Sender synchron auf. Dieser validiert das JPEG, baut die
bekannten 0x08-Reports und sendet seriell über das bestehende Sessionhandle.
Erst nach vollständigem Transfer fordert er N+1 an und wartet auf dessen
Generation. Die Pending-Flag/Lock-Kombination bündelt Signale. Es gibt kein
Catch-up, keinen Timeline-Sprung oder Paralleltransfer.

### Frequenzen und doppelte Arbeit

| Arbeit | Baseline-Frequenz | Optimierter Pfad |
| --- | --- | --- |
| GIF-Datei öffnen, Disposal/Decode, EXIF, Alpha, RGB, Resize | einmal je Frame beim Laden | gleich; redundante RGBA-Kopie entfernt |
| Basisframe-Lookup | je Preview-/LCD-Schritt | gleich, ohne Decode/Resize |
| Fonts suchen/laden | mehrfach je Text und Renderframe | höchstens einmal je Fontcache-Miss |
| Slotwerte/Strings/Layout | Slotaufbau und Textlayout je Renderframe | Slotaufbau bei Snapshot-/Auswahlwechsel; Layoutcache |
| Glyphen zeichnen | acht Texte je Renderframe | nur neue Text-/Layoutmasken bei Cache-Miss |
| Overlay auf Basis komponieren | separat je Preview-/LCD-Frame | Masken-Pastes; fertige Komposition bei gleichem Schlüssel geteilt |
| Rotation | je Komposition, auch Kopie bei 0° | einmal je neue Komposition; 0° ohne Zusatzkopie |
| JPEG-Encoding/Validierung | je Preview- und LCD-Render, außerdem für alle Frames beim Laden | nur auf LCD-Anforderung, höchstens einmal je Kompositionsobjekt |
| Qt-JPEG-Decode | je sichtbare Preview | entfällt vollständig |
| RGB → QImage/QPixmap, Skalierung | implizit nach JPEG-Decode | direkt, ausschließlich sichtbar |
| Metadatenwidgets | je Previewframe | Laden/Einstellungswechsel und vorhandener 250-ms-Statustimer |
| Sensorpolling | bedarfsgesteuerte 1 Hz | unverändert 1 Hz |
| Publish/Reports | je benötigtem LCD-Frame | unverändert; Preview veröffentlicht nichts |

Sensoren wurden bereits vorher nicht je GIF-Frame gelesen. Der einzige
1-Hz-Timer liest nur ausgewählte Metrics. Allerdings erzeugte ein geänderter
Snapshot selbst bei versteckter laufender GIF-Ausgabe zusätzlich eine
unsichtbare Preview-Komposition samt JPEG. Das entfällt. Bei aktiver GIF-
Timeline übernimmt der nächste angeforderte LCD-Frame den neuesten Snapshot;
beim gehaltenen letzten Frame eines endlichen GIFs wird weiterhin unmittelbar
mit der Telemetrieaktualisierung publiziert. Unveränderte sichtbare Werte
lösen keinen zusätzlichen Telemetrie-Render aus.

## Profilingmethodik und Reproduktion

`research/benchmark_gif_rendering.py` benötigt nur vorhandenes Python 3.14.7,
Pillow 12.3.0, PySide6 6.11.2 und die Standardbibliothek. Kein Download.
`QT_QPA_PLATFORM=offscreen`, temporäre INI-Einstellungen, gemockte Discovery
und injizierte Sensor-Snapshots verhindern jeden realen Geräte-/Sensorzugriff.

Aus `tests/fixtures/lcd-0x08-reference.jpg` entstehen reproduzierbar zwölf
verschobene GIF-Frames mit jeweils 60 ms Dauer, Loop 0 und Disposal 2.
SHA-256 des erzeugten GIFs:
`7e579a27fcfd857840103f9b2915779a2c7d90d9c85fe03ba033d010aec973af`.
Verwendet werden Crop, 90° Rotation, Defaultgeschwindigkeit 2× und vier
Slots: CPU %, GPU %, CPU Package und GPU Temperatur. Simulierte Telemetrie
ändert sich einmal pro Sekunde. Das Referenz-JPEG dient auch als statische
Kontrolle. Seine Inhalte und Herkunft werden nicht geändert.

Jeder Messlauf enthält 60 Warmup-Schritte und 600 gemessene Schritte.
GIF-Schritte entsprechen einer Gelegenheit alle 1/30 s; das ist nur die
simulierte Eingabe für den Benchmark, kein Limit in der Anwendung.
Die statische Kontrolle misst ebenfalls 600 Updates, jedoch mit 1-Hz-
Simulationszeit. Ohne Overlay wiederholt sie nur den vorhandenen Snapshot.
Laden ist separat erfasst und nicht in den Frametimings enthalten.

Die Tabelle verwendet den Median dreier uninstrumentierter `perf_counter_ns()`-
Läufe. Komponenten werden in einem weiteren Lauf mit verschachtelten,
exklusiven Timern gemessen; der Elternwert enthält keine gemessenen Kinder.
Ein separater `cProfile`/`pstats`-Lauf erfasst Call-Sites. Dessen verzerrte
Laufzeiten werden ausdrücklich nicht als normale ms/frame ausgegeben.
Insbesondere vergrößert cProfile die Kosten der Python-JPEG-Scanprüfung.
Die ursprüngliche Previewmessung wurde nach Ende der Baseline-Tests wiederholt;
die übernommenen Vergleichsläufe liefen ohne parallele Tests.

LCD und kombinierter Pfad verwenden die echten GUI-Producer-/Buffer-Callbacks
und einen synchronen `MemoryController`: Snapshot lesen, echten Validator und
Reportbau ausführen, Bytes nur im Speicher halten. Der Benchmark startet weder
einen HID-Sender noch einen Hardwareworker. Der reale Thread-/Condition-
Handshake wird separat durch die vorhandenen Controller-/Transporttests geprüft.
Qt-Konvertierung, Smooth-Scaling und Widget-Setter werden gemessen; vollständige
Desktop-Compositor-Repaints, Kernel-USB-I/O, JSONL-Dateischreiben und reale
Thread-/Timerlatenzen gehören nicht zu diesem Mikrobenchmark. Es gibt keine
Umrechnung seiner Ergebnisse in reale CPU-Prozente.

```sh
python3 research/benchmark_gif_rendering.py --frames 600 --repeats 3 --output /tmp/tuf-render.json
python3 research/benchmark_gif_rendering.py --frames 600 --repeats 3 --overlay off --output /tmp/tuf-render-no-overlay.json
python3 research/benchmark_gif_rendering.py --frames 600 --repeats 3 --scenarios combined --preview-offset 1 --output /tmp/tuf-render-offset.json
```

Für einen erneuten Baselinevergleich lässt sich der alte Quellstand ohne
Worktreeänderung in einen temporären Ordner extrahieren. Derselbe aktuelle
Benchmark wird auf die alten Runtimemodule gerichtet:

```sh
baseline_dir=$(mktemp -d /tmp/tuf-render-baseline.XXXXXX)
git archive 4941d3c src tests/fixtures | tar -x -C "$baseline_dir"
TUF_BENCH_SOURCE_ROOT="$baseline_dir" python3 research/benchmark_gif_rendering.py --frames 600 --repeats 3 --output /tmp/tuf-render-baseline.json
```

Einzelmessungen, Komponenten, Callcounts, dominante Profileinträge und
Quellhashes liegen in `gif-rendering-benchmarks.json`. Die Fontcache-
Zwischenmessung entstand ausschließlich mit `@lru_cache(maxsize=32)` auf
`_overlay_font`; alle weiteren Renderänderungen folgten danach.

## Baseline, Ursache und Optimierungen

Der kombinierte Baselinepfad benötigt 26,339 ms pro Schritt mit je einem
Preview- und LCD-Frame. Rund 91,8 % des separat instrumentierten Laufs liegen
bei Font-Suche/Layout/Zeichnen (24,394 ms/Schritt). Für 600 Schritte entstehen
1.220 Renderings: 600 Preview, 600 LCD und 20 zusätzliche Telemetrierenderings.
Das Profil zählt 48.800 `ImageFont.truetype()`-Aufrufe und 976.000 Aufrufe von
`os.walk()` einschließlich rekursiver Generatorfortsetzungen. Pillows Suche
nach dem ersten Fontnamen wiederholt die Verzeichnissuche bei jedem Laden.
Die Messung belegt damit einen erheblichen wiederholten Dateisystem-/Fontpfad,
keine vermeintliche USB-Ursache.

Umgesetzt wurden:

1. Ein Font-LRU mit maximal 32 Einträgen. Dieser isolierte Schritt senkt
   Preview auf 5,134 ms, LCD auf 5,081 ms und kombiniert auf 10,189 ms.
2. Acht gecachte Slotlayouts und maximal 128 gecachte Paare aus Stroke-/Fill-
   Masken. Masken sind auf ihre tatsächlichen Textgrenzen zugeschnitten;
   Layout, Fontwahl, Position, Randprüfung, Farbe und Strichstärke bleiben
   erhalten. Zwei L-Masken erhalten die ursprüngliche Reihenfolge
   „schwarzer Stroke, danach farbige Füllung“. Die Tests vergleichen das
   Ergebnis pixelgenau mit direktem Zeichnen auf dem RGB-Basisbild, einschließlich
   aller vier Rotationen, Weiß/Schwarz/Farbe und verschiedener/fehlender Werte.
3. GUI-eigene fertige `PreparedImage`-Kompositionen: Preview fordert einmalig
   immutable RGB-Bytes an, `QImage(..., Format_RGB888)` übergibt sie synchron an
   `QPixmap.fromImage()`. Kein JPEG-Encoding, Validator, JPEG-Decode oder
   `QByteArray` für Preview. Der Pixmap besitzt anschließend seine Qt-Pixel.
4. JPEG wird beim ersten tatsächlichen LCD-Bedarf aus genau derselben fertigen
   Pillow-Komposition erzeugt, validiert und im Objekt gehalten. Wiederholte
   Zugriffe auf `jpeg_bytes`/`jpeg_info` encoden nicht erneut. Ein kleiner
   Zwei-Einträge-LRU pro Fenster teilt identische Kompositionen zwischen den
   weiterhin unabhängigen Preview-/LCD-Schedulern. Cache-Misses werden regulär
   gerendert; sie überspringen keinen Frame.
5. GUI-GIF-Laden erzeugt nur vorbereitete RGB-Basisframes und kein unbenutztes
   JPEG je GIF-Frame. Die bestehenden allgemeinen Pipelineaufrufe verwenden
   standardmäßig weiterhin sofortige JPEG-Erzeugung und Validierung;
   ausschließlich der bedarfsgesteuerte GUI-Pfad übergibt `encode=False`.
6. Die frische, intern besessene RGB-Komposition wird direkt mit Masken
   beschrieben. `convert("RGB").copy()` und die 0°-Zusatzkopie entfallen dort.
   Öffentliche Overlayhelfer behalten ihre Nicht-Mutation des Eingabebilds.
7. Slotmodelle werden bei Snapshot-/Auswahlwechsel aufgebaut. Versteckte GIFs
   rendern beim Sensorupdate keine Preview; beim Öffnen wird deren aktueller
   Zustand einmal nachgezogen. Metadaten-Widgets laufen nicht mehr je
   Animationsframe. Gestoppt steht bei JPEG-Metadaten „—“ und die Prüfung beim
   LCD-Start; laufend werden die Werte des letzten erzeugten LCD-Frames gezeigt.

JPEG selbst bleibt 320×320, Qualität 60, 4:2:0, SOF0/Baseline,
`progressive=False`, `optimize=False`. Ein frisches `BytesIO` je tatsächlich
benötigtem Encode bleibt bestehen: Der gemessene Encodeaufwand rechtfertigt
keine zusätzliche Pool-/Mutable-Buffer-Komplexität. Keine native/neue
Dependency und kein Hardwareencoder wurden ergänzt.

## Vorher/Nachher

Für GIF ist ein Schritt ein Frame je aktivem Ausgabepfad; kombiniert also ein
Framepaar. „Verarbeitung/s“ ist lediglich der Kehrwert der Offline-Arbeitszeit,
keine tatsächliche Display-FPS-Angabe.

| Szenario, Overlay an | Baseline ms/Schritt | Optimiert ms/Schritt | Ersparnis ms | Ersparnis |
| --- | ---: | ---: | ---: | ---: |
| A: sichtbare GIF-Preview, LCD gestoppt | 13,211 | 0,457 | 12,754 | 96,54 % |
| B: GIF-LCD, GUI verborgen, Memory-Sender | 13,471 | 1,047 | 12,425 | 92,23 % |
| C: sichtbare GIF-Preview + LCD | 26,339 | 1,313 | 25,026 | 95,02 % |
| D: statisches Bild, Telemetrieupdate und Memory-Sender bei 1 Hz | 13,203 | 2,462 | 10,741 | 81,35 % |

| Szenario | Zeit für 600 Schritte, vorher → nachher | Verarbeitung/s, vorher → nachher |
| --- | --- | --- |
| A | 7.926,8 → 274,1 ms | 75,7 → 2.188,9 |
| B | 8.082,7 → 627,9 ms | 74,2 → 955,5 |
| C | 15.803,1 → 787,6 ms | 38,0 → 761,8 |
| D | 7.921,7 → 1.477,1 ms | 75,7 → 406,2 |

Bei D entstehen 600 tatsächliche Render-/Sendeschritte über 600 simulierte
Sekunden; bei GIF sind es 600 Animationsschritte über 20 simulierte Sekunden.
Die CPU-Kosten pro realer Sekunde sind deshalb aus diesen Framekosten allein
nicht gleichzusetzen. Ohne Overlay rendert D nach dem Laden gar nicht mehr:
600 Memory-Re-Sends benötigen vorher 0,0668 und nachher 0,0666 ms je Schritt,
also praktisch unverändert.

Der isoliert gemessene Fontcache erklärt beim kombinierten Pfad 16,150 ms
Einsparung, also 61,32 % der ursprünglichen Gesamtzeit. Die übrigen Änderungen
zusammen sparen weitere 8,876 ms beziehungsweise 33,70 Prozentpunkte. Für
Masken, Kopien, Cache-Sharing und JPEG-Entkopplung wurden keine voneinander
isolierten Zeitgewinne erfunden. Der Komponentenvergleich zeigt ihre Effekte:

| Kombinierter Pfad, separat instrumentiert | Baseline ms/Schritt | Optimiert ms/Schritt | Optimierter Anteil |
| --- | ---: | ---: | ---: |
| Fontsuche/Layout/Glyphen | 24,394 | 0,041 | 3,1 % |
| JPEG-Validierung | 0,945 | 0,672 | 50,3 % |
| JPEG-Encoding | 0,334 | 0,142 | 10,6 % |
| Qt-Pixmap inkl. bisherigem JPEG-Decode | 0,180 | 0,017 | 1,3 % |
| Qt-Skalierung/Widget | 0,191 | 0,175 | 13,1 % |
| Bildkopien/Konvertierung/RGB-Bytes | 0,121 | 0,077 | 5,8 % |
| Rotation | 0,075 | 0,037 | 2,8 % |
| Overlay-Komposition ohne gemessene Kinder | 0,125 | 0,106 | 7,9 % |
| Buffer-Publish ohne Validator | 0,006 | 0,004 | 0,3 % |

Rest sind Lookup-/GUI-/Sensor-Snapshotarbeit, Memory-Reportbau und Messrahmen.
Die 600 GIF-Schritte erzeugen nun exakt 600 LCD-Encodes und 600 Publikationen;
in Preview allein jeweils null. Kombiniert fallen 620 statt 1.220
Kompositionen an. Die zusätzlichen 20 gehören zur unmittelbaren sichtbaren
1-Hz-Telemetrieaktualisierung. GIF-Decoding und Resize zählen in sämtlichen
Steady-State-Profilen null. Hidden+LCD aktiv hat null Qt-Konvertierungen und
keine Preview-/Metadatenupdates. Neue LCD-Bytes durchlaufen weiterhin alle drei
Prüfgrenzen: Renderer, Framebuffer und Sender.

Ohne Overlay sinkt die Preview von 0,736 auf 0,295 ms, kombiniert von 1,124
auf 0,697 ms. LCD allein bleibt ungefähr gleich (0,461 → 0,452 ms): Dort
existierte in diesem Kontrollfall kein dominanter Textpfad. Die Optimierung
beruht damit nicht auf einer Änderung der JPEG-Qualität oder des Senders.

Bei einer um einen Frame vorlaufenden Preview ergibt der kombinierte Test
26,308 → 1,513 ms pro Schritt, entsprechend 94,25 % Einsparung. Das bestätigt,
dass der Gewinn auch bei verschiedenen Frameindizes besteht und nicht von
künstlich synchronisierten Timelines abhängt.

## Speicher, Ownership und verbleibende Kosten

Die vorbereiteten GIF-Basisbytes bleiben bei 307.200 Byte pro Frame. Die
unveränderten Grenzen sind 500 Frames und 64 Millionen Quellpixel insgesamt;
die absolute Basisbytegrenze beträgt damit 153.600.000 Byte (146,48 MiB).
Das zwölfteilige Benchmark-GIF braucht 3.686.400 Byte (3,52 MiB) Basisdaten.
Die GUI speichert keine zusätzlichen vorberechneten JPEGs für alle GIF-Frames.
Ein vorrotierter Cache für alle Frames wurde wegen der bereits kleinen
Transpose-Kosten und der notwendigen Rotation der vollständigen Overlays
nicht angelegt.

Der Fenster-LRU hält höchstens zwei fertige Kompositionen. Letzte sichtbare
Preview und letzter LCD-Frame können zusätzlich jeweils ein inzwischen
verdrängtes Objekt halten: höchstens vier verschiedene dauerhaft referenzierte
Kompositionen, unabhängig von Laufzeit/Loopzahl. RGB-Bytes entstehen nur bei
Previewbedarf; das sind höchstens weitere 4 × 307.200 Byte. Pillow-/Qt-
Pixelstorage und JPEG-Bytes kommen hinzu, jeweils mit diesen festen
Objektzahlen; dies ist keine Messung des vollständigen Prozess-RSS.

Fontcache: maximal 32 Faces; Layoutcache: acht Schlüssel; Maskencache:
128 Paare. Ein separater Durchlauf der 20 Benchmark-Snapshots belegte acht
Fontfaces und 84 Maskenpaare mit insgesamt 314.060 Byte Maskenpixeln, größtes
Paar 4.320 Byte. Python-/Font-Metadaten sind darin nicht enthalten.
Die Masken sind zugeschnittene L-Bilder; selbst ohne Zuschneidegewinn ist
ihre harte Pixelobergrenze 128 × 2 × 320 × 320 = 25 MiB. Im gemessenen
4-Slot-Fall beträgt der Pixelbestand rund 307 KiB.

Private Pillow-Kompositionen und Textmasken bleiben im Renderer/GUI-Kontext und
werden nach Fertigstellung nicht verändert. Weder ein Pillow-Bild noch ein
mutable Speicherbereich wandert zum Worker. Der Sender erhält ausschließlich
immutable JPEG-Bytes. `LatestFrameBuffer`, Locks, Conditions und
Snapshotsemantik bleiben unverändert. Qt-Pixelbesitz nach Cache-Eviction ist
explizit getestet.

Verbleibende Kosten sind bei sichtbarer Preview vor allem Smooth-Scaling,
Masken-Pastes und RGB-Pixelübergabe, beim LCD vor allem die unveränderte
JPEG-Scanvalidierung und ein notwendiger Encode. Der Validator wird trotz
seines jetzt hohen relativen Anteils nicht abgeschwächt. Ein Rendercache-Miss
führt zu normalem Rendering, niemals zu Frame-Skipping. Die GIF-Flüssigkeit
wird durch unveränderte Sequenz und Dauern geschützt; die reale Bestätigung
bleibt Teil des folgenden manuellen Tests.

## Regressionen und Safety

Neue strukturelle Tests prüfen jeweils bis zu 300 Frames ohne fragile
Zeitlimits: Preview ohne Encode/Decode/Publish, sichtbare/verborgene Zustände,
beide Timelines mit und ohne Versatz, höchstens ein Encode je benötigtem
LCD-Frame, Cachegrenzen, unveränderte Basisbytes, keine erneute Quelldekodierung
oder Resize/Fontsuche/Textzeichnung bei warmem unverändertem Zustand,
1-Hz-Sensorentkopplung, aktuelle Werte beim Tray-Show und Qt-Pixelbesitz.
Zusätzlich geprüft: GIF-Disposal/Transparenz, alle Rotationen, pixel- und
JPEG-bytegleiche Overlays, statisch↔GIF sowie fehlgeschlagenes Encoding vor
Sessionstart und beim laufenden Bildwechsel. Ungültige JPEGs ersetzen keinen
gültigen Snapshot und erreichen keinen neu gestarteten Controller.

Die vollständige Suite umfasst darüber hinaus die bestehenden Tests für
sequenziellen echten Offline-Worker-Handshake, keine Queue/Parallelität,
persistenten HID-Transport mit Memory-/Mock-I/O, Stop, Quit, Signal-Shutdown,
Autostart, Single-Instance und isolierte Installation. Es wurden keine
Gerätekommunikation, HID-/USB-Writes, neuen Opcodes, Interface-0-Zugriffe,
OpenRGB-/19af-Zugriffe, Live-Tests, Installation, Commits oder Pushes ausgeführt.

### Vollständiges Abschlussergebnis

Am 2026-09-06 ausgeführt:

| Prüfung | Ergebnis |
| --- | --- |
| `python3 -B -m unittest discover -s tests -q` | 260 Tests, 2,769 s, OK |
| `python3 -B -m unittest discover -s tests -p test_gif_rendering_efficiency.py -v` | alle 14 neuen Tests, 1,127 s, OK |
| `python -m compileall -q src tests` | Exit 0, keine Fehler |
| `git diff --check` | Exit 0, keine Fehler |
| Diff von Scheduler, Refresh/Transport, Factory, Runtime-Safety, Sensoren, Telemetriemodell und Packaging | unverändert |
| `git status --short` | ausschließlich die beschriebenen Code-, Test-, Benchmark- und Dokumentationsänderungen |

Testlaufzeiten sind beobachtete Ausführungszeiten, keine Testgrenzen.

## Ergebnis des manuellen CPU-/Sichttests

Der Test wurde mit unveränderter GIF-Datei, Geschwindigkeit,
Overlaybelegung, Farbe, Rotation und Fenstergröße gegenüber der Ausgangsmessung
ausgeführt. Die sichtbare Preview und das physische LCD blieben flüssig; die
Frameorder, vier Rotationen, aktuellen Slotwerte, Tray hide/show und der
Wechsel GIF↔PNG blieben korrekt. Die oben dokumentierten CPU-Werte sind das
finale Ergebnis dieses Tests. Der Efficiency-Block ist damit für V1
live-validiert.
