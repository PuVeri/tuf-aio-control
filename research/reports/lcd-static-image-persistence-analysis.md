# Statische Analyse der Einzelbild-Persistenz

Stand: 2026-09-02

## Zweck und Sicherheitsgrenze

Diese Untersuchung dokumentiert den erfolgreichen realen Live-Test der
automatischen Bildpipeline und ordnet statisch ein, warum das sichtbar
committed Einzelbild kurz danach wieder ersetzt wurde. Verwendet wurden nur
die vorhandenen Projektquellen, Berichte sowie die bereits analysierten
v51-Firmware- und ASUS-InfoHub-1.0.0.15-Artefakte. Die vorhandenen
Ghidra-Projekte wurden ausschließlich read-only und ohne Neuanalyse geöffnet.

Es gab keine Gerätekommunikation, keinen HID-Write, keine Freigabe von
Schreibrechten, keinen weiteren Live-Test und keine Ausführung der
Windows-Herstellersoftware.

## Ergebnis in Kürze

Die automatische Pipeline ist auf dem realen Gerät mit Versionswert `0x0049`
nun ebenfalls praktisch bestätigt: Ein beliebiges unterstütztes Eingabebild
wurde von `image_pipeline.py` zu einem gültigen 320×320-Baseline-JPEG
aufbereitet, über die GUI und `lcd_transport.py` genau einmal übertragen und
sichtbar dargestellt. Das Bild wurde nach kurzer Zeit durch einen anderen
Displayinhalt ersetzt.

Der `0x08`-Pfad besitzt in der analysierten v51-Firmware keinen eigenen
Verfallstimer und keinen Callback, der einen erfolgreich committed Frame
allein wegen seiner Herkunft wieder entfernt. Er schreibt in den nächsten
Framebuffer-Ringknoten; der Displaycallback macht diesen sichtbar. Der Frame
bleibt ausgewählt, bis ein anderer Grafikproduzent einen weiteren Ringknoten
bereitstellt und der gemeinsame Displaycallback diesen committed.

Ein solcher konkurrierender Produzent ist statisch belegt: Der interne
Boot-/Objektpfad lädt gespeicherte Records, rendert sie in den Ring und kann
seine Folge abhängig von `config+0x111` wiederholen. Der Defaultwert ist `1`,
bei dem die Bootfolge nach dem letzten Record wieder bei Index null beginnt.
`0x08` ändert weder dieses Byte noch registrierte Display-/Bootcallbacks.
Damit ist die engste technisch belegte Erklärung, dass das eigene Bild
korrekt committed und anschließend regulär durch den noch aktiven internen
Anzeigeablauf überschrieben wurde. Für v49 ist die genaue interne Kante mangels
v49-Binärdatei nicht bytegenau bewiesen; das reale zeitweilige Erscheinen und
spätere Ersetzen ist jedoch mit diesem v51-Mechanismus konsistent.

ASUS InfoHub 1.0.0.15 setzt vor einem erfolgreichen statischen Bildtransfer
keinen separat belegten Hold-/Static-Displaymodus. Stattdessen ruft sein
Leerlauf-Worker den JPEG-Sender wiederholt auf. `GetLEDData()` kopiert den
aktuellen JPEG-Puffer bei jedem Aufruf erneut und verbraucht oder löscht ihn
nicht. InfoHub hält die Anzeige daher hostseitig durch weitere `0x08`-Frames
aktuell; dies ist keine Geräte-„Hold“-Semantik und noch keine Freigabe, dieses
Verhalten im Projekt nachzubauen.

## 1. Neu empirisch bestätigter Pipelinepfad

Für den neuen Live-Lauf gilt nach Bedienerbeobachtung:

- Ein von der Pipeline unterstütztes normales Eingabebild wurde offline
  geöffnet, orientiert, in RGB überführt und als konservatives 320×320-
  Baseline-JPEG erzeugt.
- Das Ergebnis bestand die bestehende ASUS-JPEG-Validierung.
- Die GUI übergab genau diesen vorbereiteten Frame an den unveränderten
  einmaligen Transferpfad aus `lcd_transport.py`.
- Das erwartete Bild erschien sichtbar auf dem realen AIO-LCD mit gemeldetem
  Versionswert `0x0049`.
- Der sichtbare Erfolg bestätigt für diesen Lauf gemeinsam Bildvorbereitung,
  GUI-Übergabe, erneute JPEG-Validierung, Segmentierung, Interface-1-Transfer,
  Hardwaredekodierung und Displaycommit.
- Das Bild blieb nur kurz sichtbar und wurde danach ersetzt.

Dieser Test bestätigt keine Animation, keinen Mehrfachframebetrieb, keine
stabile Besitzübernahme des Displays und kein Fehler- oder Dauerverhalten.

## 2. Framebuffer-Ring und Displaycommit

Der v51-`0x08`-Lebenszyklus ist statisch rekonstruiert:

```text
vollständiger Interface-1-0x08-Transfer
  -> Queueeintrag mit JPEG-Quelle
  -> Hardwaredecoder, Ziel = current->next->framebuffer_base
  -> Decoderende
  -> next->ready_state = -1
  -> späterer Displaycallback 0x00129cf0
       current->ready_state = 0
       current = next
       Displayregister b1002050 = next->framebuffer_base
```

`0x00129cf0` schaltet nur dann weiter, wenn der Folgeknoten einen von null
verschiedenen Bereitzustand besitzt. Nach dem `0x08`-Commit existiert kein
belegter Countdown, der den nun aktuellen Knoten automatisch ungültig macht,
und der `0x08`-Pfad merkt sich keinen vorherigen Framebuffer für einen späteren
Rollback.

Der bekannte Countdown `0x001315c4` ist eine Lease für Decoderquelle und
Queueeintrag. Er schützt während des Decodes vor vorzeitiger Queuefreigabe;
er wählt weder den sichtbaren Ringknoten noch löst sein Ablauf nach einem
erfolgreichen Commit eine Rückschaltung aus. Der beobachtete kurze Bildbestand
ist daher nicht mit einem belegten `0x08`-Frame-Timeout zu erklären.

## 3. Pfade, die später einen anderen Framebuffer aktivieren

Der interne Bootcallback `0x001268d0` verarbeitet beim periodischen Ereignis
`0x15` gespeicherte 16-Byte-Records. Wenn der Grafikblock frei ist, lädt er
den nächsten Record, markiert beziehungsweise beschreibt den nächsten
Framebuffer-Ringknoten und startet den gemeinsamen Grafikrouter. Derselbe
Displaycallback `0x00129cf0` kann diesen Knoten anschließend sichtbar machen.

Nach dem letzten Record gilt:

- `config+0x111 == 0` oder `2`: Der Bootablauf beendet sich.
- jeder andere Nichtnullwert: Der Recordindex wird auf null gesetzt und die
  Bootfolge beginnt erneut.

Der Bootdefault von `config+0x111` ist `1`. Solange dieser Zustand und der
Callback aktiv bleiben, existiert also ein statisch konkreter Produzent, der
nach einem fremden `0x08`-Commit den nächsten Ringknoten wieder mit einem
internen Bild füllen kann. Daneben existiert der normale gespeicherte
Objekt-/JPEG-Callback `0x001279e8`; er ist bei `+0x111 == 0` aktiv und bei
Nichtnullwerten gesperrt. Auch dieser Pfad benutzt den gemeinsamen
Grafik-/Ringunterbau.

Der direkte `0x08`-Consumer setzt nur Grafikmodus `0x6021`, Ziel, Quelle und
Completion-Callback für genau den laufenden Decode. Er deaktiviert weder den
Bootcallback noch den Objektcallback und ändert `config+0x111` nicht. Das
Protokollkommando `0x08` bedeutet daher „einen Frame dekodieren und in den
Ring committen“, nicht nachweislich „dem Host das Display dauerhaft
überlassen“.

## 4. Bewertung von `+0x110`, `+0x111`, `0x1a` und `0x1f`

### `+0x110` / Befehl `0x1a`

`0x1a` schreibt genau ein Byte nach `config+0x110`. Dieses Byte wählt im
normalen Displaycallback zwischen zwei Zeit-/Skalenberechnungen. Es gibt
keine belegte Kante von `+0x110` zur Registrierung oder Abschaltung der
Framebuffer-, Boot- oder Objektproduzenten. `0x1a` ist deshalb kein
belegbarer Hold-Befehl.

ASUS InfoHub 1.0.0.15 besitzt in seinem rekonstruierten HID-Writer-Callgraph
keine Sendestelle für `0x1a`.

### `+0x111` / Befehl `0x1f`

`0x1f` ersetzt `config+0x111` durch sein erstes Payloadbyte und kann bei einem
Nichtnullwert den Bootcallback registrieren. Die belegten Wertklassen sind:

| Wert | Statisch beobachtete Wirkung |
| ---: | --- |
| `0` | Bootfolge endet nach dem letzten Record; normaler gespeicherter Objekt-/JPEG-Pfad wird aktiv. |
| `1` | Bootdefault; normaler Objektpfad ist gesperrt, Bootfolge wiederholt sich. |
| `2` | Bootfolge endet; normaler Objektpfad bleibt gesperrt, zusätzlich existiert ein 51-Intervall-Sonder-/Resetablauf. |
| andere Nichtnullwerte | normaler Objektpfad ist gesperrt, Bootfolge wiederholt sich. |

Keiner dieser Befunde belegt einen stabilen „externes Einzelbild halten“-Wert:
`0` aktiviert einen anderen gespeicherten Produzenten; `1` und andere
Nichtnullwerte wiederholen die Bootfolge; `2` besitzt zusätzlichen
Übergangs-/Resetzustand und ist nicht als Dauer-Hold typisiert.

InfoHub sendet `1F 01 00 80` mit Payloadwert `1` oder `2` ausschließlich aus
einer separaten Sleep-UI-Aktion. Dieser Aufruf ist nicht als Vor- oder
Nachsequenz des erfolgreichen JPEG-Senders gekoppelt. `0x1f` ist damit direkt
relevant für den internen Ablauf, aber aus den vorhandenen Belegen kein sicher
verwendbarer Static-Hold-Befehl.

## 5. Tatsächliches InfoHub-Verhalten bei einem eigenen Bild

Alle statisch gefundenen Writer des InfoHub-HID-Stacks sind begrenzt auf:

- HID1: `0x10`, `0x12`, separate Sleep-Aktion `0x1f` und die
  Fehlerbenachrichtigung `0xff`;
- HID2: den JPEG-Transfer `0x08`.

Der Worker `ASUS InfoHub.exe:0x00414ff0` ruft im Leerlaufzweig unmittelbar
`0x00416bc0`, den Interface-1-JPEG-Sender, auf. Nur wenn stattdessen ein
Workerereignis ansteht, wird eine der getrennten Aktionen bearbeitet.
`XYUI::LEDModeCtrl::GetLEDData()` nullt zwar den Zielpuffer, kopiert aber bei
jeder Abfrage erneut den unverändert gespeicherten JPEG-Puffer samt Länge und
setzt die gespeicherte Länge danach nicht zurück. Es existiert auch kein
Vergleich „Frame bereits gesendet“.

Damit erzeugt InfoHub auch für ein statisches Nutzerbild nicht nur einen
einmaligen Transfer. Der aktuelle Frame bleibt abrufbar und wird bei weiteren
Leerlaufdurchläufen erneut übertragen. `XYUI::LEDModeCtrl::OnControlTimer()`
aktualisiert bei GIF-/Video-/Overlaymodi zusätzlich den gerenderten Frame; für
ein statisches Bild bleibt die Quelle gleich, der Hostsender bleibt dennoch
wiederholt aufrufbar.

Für genau einen erfolgreichen `0x08`-Aufruf gibt es weiterhin keinen
Interface-0-Begleitbefehl davor oder danach. Der Hostcode belegt daher keine
ASUS-Sequenz nach dem Muster „Displaymodus setzen, einmal Bild senden, Modus
hält Bild“. Er belegt stattdessen eine laufende hostseitige Bildversorgung.

## 6. Ursache und Konsequenz für das Projekt

Die Evidenzebenen sind sauber zu trennen:

- **Empirisch bestätigt auf dem realen v49-Gerät:** Das automatisch erzeugte
  JPEG wird korrekt decodiert und committed; der sichtbare Frame wird nach
  kurzer Zeit ersetzt.
- **Statisch bestätigt in v51:** Ein `0x08`-Commit verfällt nicht selbst. Ein
  aktiver Boot-/Objektproduzent kann später einen weiteren Ringknoten bereit
  machen; der gemeinsame Displaycallback committed ihn. Default `+0x111=1`
  wiederholt die Bootrecordfolge.
- **Statisch bestätigt in InfoHub 1.0.0.15:** Vor oder nach dem erfolgreichen
  Bildtransfer wird kein separater Holdmodus gesetzt. Der Hostworker kann
  denselben JPEG-Frame wiederholt senden.
- **Weiterhin offen:** Die bytegenaue Gleichheit dieses internen Ablaufs in
  v49, die reale Wiederholrate von InfoHub und ob v49 einen bislang nicht
  belegten sicheren Holdzustand besitzt.

Periodisches erneutes Senden ist für den initialen Decode und Commit nicht
erforderlich. Es ist die belegte Strategie von InfoHub, um gegenüber den
internen Anzeigeabläufen die Bildquelle fortlaufend zu behaupten. Daraus folgt
nicht, dass das Projekt diese Strategie bereits sicher übernehmen darf:
Mehrfachframes, Taktung, Queue-/Decoder-Lease, Überlappung und Abbruchverhalten
sind dafür noch nicht freigegeben oder real charakterisiert.

## 7. Nächster sicherer Test

Der nächste Schritt sollte kein eigener `0x1a`-/`0x1f`-Write und kein
periodisches Resenden sein. Die risikoärmste neue Evidenz ist ein passiver
USB-Mitschnitt einer ohnehin durch ASUS InfoHub 1.0.0.15 ausgeführten Aktion
„statisches eigenes Bild“ auf dem realen Gerät:

1. beide HID-Interfaces bereits vor dem Moduswechsel mitschneiden;
2. alle Interface-0-Commands und alle Interface-1-`0x08`-Transfers mit
   Zeitstempeln erfassen;
3. über einen ausreichenden Nachlauf zählen, ob und in welchem Abstand
   identische JPEG-Frames erneut gesendet werden;
4. insbesondere prüfen, ob runtime-seitig doch ein `0x1a` oder `0x1f` zeitlich
   benachbart erscheint;
5. sichtbaren Displayverlauf zeitlich mit dem Capture korrelieren.

Dieser passive Herstellercapture prüft die statische Hostrekonstruktion auf
dem realen v49-Gerät, ohne einen eigenen unbekannten Modusbefehl einzuführen.
Erst danach wäre ein getrenntes Safety-Review für eine begrenzte
Mehrfachframe- oder Modusstrategie sinnvoll.

## Schlussfolgerung

Ein separates ASUS-Static-Hold vor dem Bildtransfer ist im analysierten
InfoHub-1.0.0.15-Hostcode **nicht vorhanden**. Der kurze Bildbestand ist am
besten durch einen
späteren regulären Commit des weiterhin aktiven internen Boot-/Objektpfads
erklärt, nicht durch ein Verfallen des `0x08`-Frames. `0x1a` ist nur ein
Zeit-/Skalenselektor; `0x1f` beeinflusst Abläufe, liefert aber keinen sicher
belegten Holdwert. InfoHub kompensiert diese Besitzkonkurrenz durch wiederholte
`0x08`-Transfers. Eine solche Wiederholung bleibt für dieses Projekt bis zu
einer eigenen Sicherheitsbewertung ausdrücklich unimplementiert und
unfreigegeben.
