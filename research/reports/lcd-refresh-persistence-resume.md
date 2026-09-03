# Wiederaufnahme der LCD-Refresh- und Persistenzanalyse

Datum: 2026-09-03

## Ausgangslage und Grenze

Der kanonische reale Stand ist geschlossen: `0x87` lieferte `0x0049`; ein
eigener `0x08`-JPEG-Transfer wurde vom realen v49-Gerät angenommen, decodiert
und sichtbar committed. Linux-hidraw-Framing, Segmentierung und Nullpadding
sind damit ebenso empirisch bestätigt wie der Einzelbildpfad über UI und
Bildpipeline. Auch ein GIF wurde erfolgreich verarbeitet, wobei ausschließlich
Frame 0 als Standbild sichtbar wurde. Später stellte die AIO wieder ihr
ASUS-Standardbild dar. Eine echte GIF-Animation existiert noch nicht.

Diese Untersuchung wertet ausschließlich den aktuellen Projektstand, die
vorhandene statische Persistenzanalyse, die vorhandene InfoHub-Senderanalyse
und `ExportInfoHubRefreshTriage.java` aus. Es gab keine Gerätekommunikation,
keinen HID-Write, keinen neuen Test und keine neue Binär- oder Firmwareanalyse.

## 1. Technischer Blocker

Der einzelne Transfer ist nicht mehr der Blocker: Er funktioniert auf v49 bis
zum sichtbaren Displaycommit. Offen ist die **dauerhafte Besitzbehauptung des
Displays gegenüber weiteren Frameproduzenten**.

Der analysierte v51-`0x08`-Pfad enthält keinen belegten Ablauf, der einen
erfolgreich sichtbaren Frame nach einer Frist verwirft oder zu einem gemerkten
Vorgänger zurückrollt. Er decodiert in den nächsten Framebuffer-Ringknoten und
der gemeinsame Displaycallback schaltet auf diesen Knoten. Sichtbar bleibt er,
bis ein anderer Produzent einen weiteren bereiten Ringknoten liefert.

Ein solcher Produzent ist statisch konkret belegt: Der interne
Boot-/Objektpfad rendert gespeicherte Records in denselben Ring. Beim
Bootdefault `config+0x111 = 1` beginnt die Bootrecordfolge nach ihrem letzten
Eintrag wieder bei Index null. `0x08` ändert weder `+0x111` noch die
registrierten Boot-/Displaycallbacks. Das beobachtete ASUS-Standardbild ist
daher am engsten durch einen späteren regulären Commit dieses weiterhin
aktiven internen Produzenten erklärt.

ASUS InfoHub setzt keinen belegten dauerhaften Holdmodus. Sein Leerlauf-Worker
ruft stattdessen den JPEG-Sender wiederholt auf; `GetLEDData()` hält den
aktuellen JPEG-Puffer abrufbar. Die Herstellerlösung ist somit laufende
hostseitige Bildversorgung. Für das Projekt fehlen jedoch noch die reale
Refreshrate, die v49-Queue-/Lease-Grenzen und ein sicherer Mehrfachframe-
Abbruchvertrag. Deshalb kann aus dem erfolgreichen Einzelbild noch keine
sichere periodische Refresh- oder Animationsstrategie abgeleitet werden.

## 2. Trennung der möglichen Mechanismen

### Interner Boot-/Objektproduzent

**Wahrscheinlichste unmittelbare Ursache.** In v51 ist der periodische
Bootcallback `0x001268d0` belegt. Er verarbeitet gespeicherte 16-Byte-Records,
befüllt einen weiteren Framebuffer-Ringknoten und lässt ihn über den gemeinsamen
Displaycallback `0x00129cf0` sichtbar werden. Der normale gespeicherte
Objekt-/JPEG-Callback `0x001279e8` ist ein weiterer Produzent desselben
Ringunterbaus. Welche Kante auf dem realen v49-Gerät bytegenau identisch ist,
bleibt ohne v49-Binärdatei offen; Beobachtung und v51-Mechanismus passen aber
direkt zusammen.

### Hostseitiges periodisches InfoHub-Refresh

**Belegte ASUS-Gegenstrategie, nicht belegte Fallback-Ursache des eigenen
Laufs.** In InfoHub 1.0.0.15 ruft `0x00414ff0` im Leerlaufzweig unmittelbar
den Interface-1-JPEG-Sender `0x00416bc0` auf. `GetLEDData()` gibt dasselbe
gespeicherte statische JPEG bei späteren Aufrufen erneut aus; es gibt kein
„bereits gesendet“-Flag. Bei GIF-/Video-/Overlaymodi kann
`LEDModeCtrl::OnControlTimer()` zusätzlich den gerenderten Frame aktualisieren.

Wenn InfoHub selbst parallel aktiv wäre, könnte ein von ihm gesendeter Frame
ebenfalls einen späteren Ringcommit verursachen. Aus den vorliegenden Fakten
ist für den eigenen Linux-Lauf aber kein solcher konkurrierender Hostwriter
belegt. Das interne ASUS-Standardbild spricht vorrangig für den
geräteinternen Produzenten. Die noch unbekannte InfoHub-Wiederholungsrate ist
vor allem für die Rekonstruktion der Herstellerstrategie relevant.

### `config+0x111`-Zustandsautomat

**Steuerung der internen Produzenten, aber kein belegter Holdschalter.** Die
statisch bekannten Wertklassen sind:

| Wert | Belegte v51-Wirkung |
| ---: | --- |
| `0` | Bootfolge endet; der normale gespeicherte Objekt-/JPEG-Pfad wird aktiv. |
| `1` | Bootdefault; Objektpfad gesperrt, Bootrecordfolge wiederholt sich. |
| `2` | Bootfolge endet; Objektpfad gesperrt, zusätzlicher 51-Intervall-Sonder-/Resetablauf. |
| andere Nichtnullwerte | Objektpfad gesperrt, Bootrecordfolge wiederholt sich. |

`0x1f` kann `+0x111` verändern, doch keiner dieser Zustände ist als sicherer
„externen Frame dauerhaft halten“-Modus belegt. `0x08` selbst verändert das
Byte nicht. `config+0x110` beziehungsweise `0x1a` wählt nur zwischen zwei
Zeit-/Skalenberechnungen und besitzt keine belegte Abschaltkante zu Boot-,
Objekt- oder Framebufferproduzenten.

### Decoder-Lease und Timeout

**Keine belegte Ursache des späteren Fallbacks.** Die Funktion
`0x001315c4` verwaltet in v51 die Lease der Decoderquelle und des Queueeintrags
während des Decodes. Sie verhindert vorzeitige Queuefreigabe. Nach einem
erfolgreichen sichtbaren Commit wählt ihr Ablauf keinen älteren Ringknoten und
löst keinen Displayrollback aus. Lease und Queue bleiben für die sichere
Taktung wiederholter Transfers wichtig, erklären aber das beobachtete
Standardbild nicht.

### Framebuffer-Ring

**Commitmechanismus, nicht eigenständiger Produzent.** Der Ring erklärt, wie
ein später bereitgestellter interner oder externer Frame den eigenen Frame
ersetzt. Es ist kein autonomer Ring-Timer oder gespeicherter Rücksprung auf den
ASUS-Frame belegt. Die eigentliche Ursache muss ein Produzent sein, der einen
neuen Ringknoten bereitstellt.

### Sonstige belegte Ursachen

Ein `0x08`-eigener Frame-Verfall, ein automatischer EOI-/JPEG-Timeout nach
sichtbarem Commit, ein zwingender `08 81`-Read oder ein separat von InfoHub
gesetzter Static-/Holdmodus sind nicht belegt. Ebenso ist das Zurückfallen
nicht das Ende einer GIF-Animation: Die Projektpipeline sendete
definitionsgemäß nur GIF-Frame 0 als einzelnes JPEG-Standbild.

## 3. Rolle von `ExportInfoHubRefreshTriage.java`

Das Skript ist ein kleiner read-only Ghidra-Export für vier harte Adressanker
in `ASUS InfoHub.exe`:

```text
0040b103
00414ff0
00416bc0
00425c10
```

Für jeden Anker bestimmt es mit `getFunctionContaining()` die umschließende
Funktion, exportiert Referenzen auf deren Entry Point und dekompiliert die
Funktion mit einem Timeout von 180 Sekunden. Es verlangt genau einen
Ausgabepfad und verweigert das Überschreiben einer vorhandenen Datei. Sein
beabsichtigter Umfang ist damit die begrenzte Aufruferkette vom
InfoHub-Refresh-/Workerrahmen zum JPEG-Sender, nicht eine neue Vollanalyse.

Zwei zentrale Teile dieses Pfads sind bereits analysiert:

- `0x00414ff0`: Worker; der Leerlaufzweig gelangt zum Bildsender;
- `0x00416bc0`: vollständiger HID2-`0x08`-JPEG-Sender.

Zum wiederholten Senden sind außerdem die bereits dokumentierten Daten- und
XYUI-Kanten relevant:

- `DeviceMainDlg+0x8b8`: 409.600-Byte-Ausgabepuffer;
- `0x0040a7e0`: Konstruktor, der diesen Puffer anlegt;
- `XYUI.dll:0x10052030`: `LEDModeCtrl::GetLEDData()`, das Puffer und Länge bei
  jeder Abfrage erneut liefert;
- `LEDModeCtrl+0x1bc`: gespeicherte aktuelle JPEG-Länge;
- `XYUI.dll:0x10052930`: `DrawHideControl()` für den neu gerenderten Frame;
- `LEDModeCtrl::OnControlTimer()`: Aktualisierung bei GIF-, Video- und
  Overlaymodi; seine Adresse ist im vorhandenen Bericht nicht festgehalten.

Die Rollen der beiden zusätzlichen Anker `0x0040b103` und `0x00425c10` sind in
den vorhandenen Berichten nicht benannt. Aus dem Skript allein darf ihnen
keine konkrete Scheduler-, Timer- oder Threadfunktion zugeschrieben werden.
Gerade ihre Auflösung und die Caller von `0x00414ff0` waren offenbar der noch
offene Zweck dieses Triage-Exports.

Das Skript ist weiterhin **nützlich**, weil es genau die fehlende obere
Worker-/Refreshkante kompakt exportieren kann. Als dauerhaft reproduzierbares
Analyseartefakt ist es aber noch unvollständig:

- die absoluten Adressen setzen das identische InfoHub-1.0.0.15-Image und den
  erwarteten Image-Base voraus;
- Programmname, Binärhash und Image-Base werden nicht validiert;
- die vier Anker sind nicht im Skript kommentiert;
- bei einem Anker außerhalb einer definierten Funktion fehlt eine Nullprüfung;
- es gibt noch keinen dokumentierten Aufruf und keinen eingecheckten Export,
  der die aufgelösten Funktionen und Ergebnisse festhält.

Es sollte daher **behalten**, vor einer erneuten Verwendung jedoch mit
Programmgates, Bedeutungsannotation der aufgelösten Targets und einem
dokumentierten read-only Aufruf reproduzierbar gemacht werden. Das Skript
wurde in diesem Ticket nicht verändert und nicht ausgeführt.

## 4. Nächster konkreter Analysepfad

Als nächster rein statischer Schritt ist der obere InfoHub-Refreshpfad zu
schließen:

1. im exakt identifizierten InfoHub-1.0.0.15-Ghidra-Projekt die Funktionen zu
   `0x0040b103` und `0x00425c10` auflösen und ihre erwarteten Rollen im Skript
   dokumentieren;
2. Caller, Schleifenrückkante, Wait-/Event-Bedingung, Suppression-Gates und
   Beendigungsbedingung von `0x00414ff0` rekonstruieren;
3. die statische Wiederholungsperiode beziehungsweise ihre Taktquelle bestimmen
   und getrennt zur `OnControlTimer()`-Taktung für GIF-/Videoframes halten;
4. dokumentieren, ob aufeinanderfolgende Leerlaufdurchläufe zwingend erneut
   `0x00416bc0` erreichen oder durch Zustandsfelder gedrosselt werden.

Danach bleibt als realer, nicht schreibender Abgleich ein passiver USB-Mitschnitt
einer ohnehin von ASUS InfoHub ausgeführten statischen Bildauswahl mit
ausreichendem Nachlauf: Zeitabstände identischer `0x08`-Frames sowie etwaige
benachbarte Interface-0-Kommandos erfassen und mit dem sichtbaren Verlauf
korrelieren. Erst diese Kombination liefert eine belastbare Grundlage für ein
eigenes Safety-Review zu periodischem Refresh oder echter GIF-Animation.

## Schlussfolgerung

Der aktuelle Blocker ist nicht JPEG-Erzeugung oder Einzelbildtransport,
sondern ungeklärte und noch nicht sicher nachgebildete Display-Ownership über
die Zeit. Der eigene Frame wurde korrekt committed und danach höchstwahrscheinlich
durch den aktiven internen Boot-/Objektproduzenten regulär überschrieben.
Framebuffer-Ring und Displaycallback vermitteln diesen Wechsel; Decoder-Lease
und ein angeblicher Frame-Timeout erklären ihn nicht. InfoHub behauptet die
Hostanzeige durch wiederholte `0x08`-Transfers. Vor einer Umsetzung müssen
deren Scheduler, Frequenz und v49-Laufzeitgrenzen geschlossen werden.
