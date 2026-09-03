# GO/NO-GO-Review: erster kurzer LCD-Refresh-Live-Test

Stand: 2026-09-03

## Umfang und Entscheidung

Dieser Review bewertet ausschließlich eine kurze Folge byteidentischer,
vollständiger Interface-1-`0x08`-Transfers des bereits real erfolgreichen
Referenz-JPEGs. Es gab in diesem Ticket keine Gerätekommunikation, keinen
HID-Write und keinen Live-Test.

**Entscheidung: GO** für einen gesondert autorisierten Test nach der normativen
Sequenz in Abschnitt 6. Das GO gilt weder für GIF, andere JPEGs, andere
Intervalle noch für einen dauerhaft laufenden Refreshsender.

## 1. Einzeltransfer gegenüber Wiederholung

Der bekannte Einzeltransfer und jeder einzelne Refreshdurchlauf besitzen
identische Bytes und denselben Gerätepfad. Neu ist nur, dass ein späterer
vollständiger Queueeintrag eintreffen kann, bevor Decode, Ringcommit oder
Freigabe des vorherigen vollständig beobachtet werden konnten.

| Aspekt | Statischer Befund | Zusatzrisiko durch Wiederholung |
| --- | --- | --- |
| USB-/hidraw-Serialisierung | `send_frame_once()` führt pro Frame drei synchrone 1025-Byte-Writes aus. Der Refreshcontroller wartet auf seine Rückkehr; Prozesslocks verhindern einen zweiten eigenen Sender. | Keine Überlappung auf Hostseite. Ein erfolgreicher `write()` belegt nur die Annahme durch Kernel/Transport, nicht Decoderende oder sichtbaren Commit. Externe Writer müssen deshalb operativ ausgeschlossen werden. |
| Queuefreigabe | v51 hält den konsumierten Eintrag bis Decoderende oder Lease-Ablauf. Der Consumer startet nur bei `bulk_active == 0` und freiem nächsten Ringknoten. | Weitere vollständig assemblierte Frames können warten. Ist die Queue voll, scheitert die Geräteallokation still; vollständige Hostwrites allein erkennen das nicht. |
| Queueakkumulation | Die Queue hat `0x32000` Byte. Das Referenz-JPEG erzeugt `N=3`, also 3060 Payloadbyte plus vier Byte internes Längenwort: 3064 Byte je Eintrag. | Fünf vollständig wartende Referenzeinträge belegen 15.320 Byte, weniger als 7,5 Prozent der Backing-Kapazität. Selbst ohne eine einzige Freigabe erreicht dieser Test die reine Kapazitätsgrenze nicht. Die exakte Queue-Wrap-/Metadatenreserve wird daraus nicht verallgemeinert. |
| Decoder-Lease | Jeder vollständige `0x08`-Transfer lädt `config+0x108` in den globalen Countdown. Während `active != 0` schützt ein Wert ungleich null die aktuelle Queuequelle; bei Ablauf wird sie ohne Ready-Markierung freigegeben. Die Tick-Wandzeit ist unbekannt. | Ein neuer vollständiger Transfer kann den globalen Countdown erneut laden. Ein exakter Mindestabstand bis zur Freigabe ist statisch nicht ableitbar. Der gefährlichste flüchtige Sonderfall bliebe ein hängender Decoder nach Lease-Ablauf und spätere Wiederverwendung seiner Quelle; dafür gibt es im bestätigten Referenzfall keinen positiven Befund. |
| Neuer Frame während Decode/Commit | Der Consumer beginnt keinen zweiten Decode, solange `bulk_active` gesetzt ist, und verlangt einen freien nächsten Ringknoten. Queuefreigabe erfolgt nach Decoderende, sichtbarer Commit später. | Firmwareseitig keine parallelen Decodes; ein neuer Frame wartet. Zwischen Queuefreigabe und Displaycommit kann bereits ein weiterer Eintrag vorhanden sein, startet aber nur mit freiem Zielknoten. |
| Framebuffer-Ring | Decodeziel ist der nächste freie Ringknoten; der Displaycallback schaltet später auf einen Ready-Knoten und gibt den vorher sichtbaren frei. Knotenzahl und Wandzeit bis zum Commit sind offen. | Zu schneller Nachschub kann warten, aber der rekonstruierte v51-Pfad überschreibt keinen als belegt markierten Zielknoten. Sichtbare Artefakte bleiben als Laufzeitfehlerkriterium erhalten. |
| Herstellervergleich | InfoHub ruft denselben vollständigen Sender in einem synchronen Worker wiederholt auf, liest kein `08 81` und wartet nicht auf einen Decoder-Done-Status. Seine Zielperiode ist 12 ms, mindestens aber die Callback-/Transferdauer. | Wiederholung vollständiger Transfers ist Herstellerbetriebsart. Das belegt keine maximale sichere Rate auf v49, stützt aber die strukturelle Verträglichkeit einer sehr viel langsameren, kurzen Folge. |

Eine **maximale sichere Wiederholrate** lässt sich weder aus dem unbekannten
Lease-Tick noch aus Host-Write-Rückgaben bestimmen. `12 ms` ist ausdrücklich
keine solche Grenze. Das erste Intervall wird deshalb nicht als ermittelte
Maximalrate, sondern als konservativer Prüfpunkt festgelegt.

## 2. Konservatives Intervall

Normativer erster Abstand zwischen den **Startzeitpunkten** zweier Frames:

```text
1,0 s
```

Das ist mehr als das 83-Fache der 12-ms-InfoHub-Zielperiode. Es lässt auch
gegenüber einer typischen synchronen Übertragung von nur drei Reports eine
große Ruhezeit, ohne zu behaupten, Decode oder Commit seien nach exakt einer
Sekunde garantiert abgeschlossen. Dauert ein Transfer länger als eine
Sekunde, startet der Controller den nächsten erst nach dessen Rückkehr und
erzeugt keinen Catch-up-Burst.

Ein noch kürzeres Intervall ist für den ersten Nachweis unnötig. Ein längeres
Intervall könnte sicherer wirken, würde aber eher zulassen, dass der interne
Default-Produzent zwischen zwei Refreshes sichtbar gewinnt. Wenn dies bei
1,0 s geschieht, ist das ein sauber definierter sichtbarer Fehlschlag und kein
Grund, während derselben Session die Rate automatisch zu erhöhen.

## 3. Harte Testgrenzen

Das in `lcd_refresh.py` ergänzte Offline-Profil fixiert:

| Parameter | Normativer Wert |
| --- | ---: |
| Referenz | `tests/fixtures/lcd-0x08-reference.jpg` |
| SHA-256 | `5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866` |
| JPEG-Länge / Segmente | 2236 Byte / `N=3` |
| Frames | genau ein unveränderlicher statischer Frame im RAM |
| Transportintervall | 1,0 s zwischen Frame-Startzeitpunkten |
| maximale Sessiondauer | 6,0 s |
| maximale vollständige Frames | 5 |
| maximale Writes | 15, je exakt 1025 Byte |

`build_first_refresh_live_test_plan()` validiert das JPEG offline und lehnt
jeden anderen Hash ab. Es öffnet kein Gerät und startet keinen Worker. Bei
normal kurzen Transfers beginnen die fünf Frames nominell bei 0, 1, 2, 3 und
4 Sekunden; anschließend beendet die Framegrenze die Session. Die
Sechs-Sekunden-Grenze ist ein zusätzlicher Abbruch vor einem weiteren Frame.
Sie kann einen bereits laufenden synchronen Systemaufruf nicht gewaltsam
abbrechen; der Transport verwendet deshalb weiterhin `O_NONBLOCK` und beendet
jeden Short Write beziehungsweise jede Exception sofort.

Zusätzlich gelten zwingend:

1. kein GIF, kein Framewechsel und keine JPEG-Erzeugung während der Session;
2. ausschließlich dynamisch erneut validiertes Interface 1 von
   `0b05:1c7b`; kein Interface 0, kein IN-Read und kein anderer Opcode;
3. kein Retry, keine Recovery, kein Neuöffnen nach Fehler und keine zweite
   Session;
4. vor Start alle InfoHub-/Armoury-/GUI-/sonstigen LCD-Writer beenden und
   durch rein lesende Prozess-/Handleprüfung ausschließen;
5. nur für den aktuellen Interface-1-hidraw-Knoten temporär Schreibrecht
   geben, ursprünglichen Mode/ACL vorher festhalten und unmittelbar nach
   Handle-Close auch im Fehlerfall exakt wiederherstellen; keine udev-Regel,
   Gruppenänderung oder andere persistente Rechteänderung;
6. JPEG, Plan, Reports, Identität und Reportdescriptor vollständig vor dem
   ersten Write prüfen; danach genau einen Controller explizit starten;
7. beim ersten Transport-, Sender- oder Strukturfehler sofort stoppen und
   keine Parameter innerhalb dieser Session verändern.

## 4. Erfolg und Fehlschlag

### Transporterfolg

Transporterfolg liegt nur vor, wenn der Controller mit `MAX_FRAMES` endet,
fünf vollständige Frameaufrufe meldet und alle 15 `os.write()`-Aufrufe exakt
1025 Byte zurückgeben. Das beweist Host-/Kernel-Transportvollständigkeit. Es
beweist wegen der stillen Gerätequeue und des fehlenden Done-Status weder fünf
Decodererfolge noch fünf sichtbare Commits.

### Sichtbarer Erfolg

Sichtbarer Erfolg liegt getrennt nur durch unmittelbare menschliche/passive
Beobachtung vor: Das bekannte Referenzbild erscheint und bleibt vom ersten
sichtbaren Commit bis zum Ende der aktiven Refreshsession ohne sichtbare
Default-Unterbrechung stabil. Der Code darf dieses Ergebnis nicht automatisch
behaupten. Ein Default-Fallback erst **nach** Sessionende ist für diesen Test
erwartbar und kein Fehlschlag.

### Fehlschlag

Die Session ist fehlgeschlagen bei:

- ASUS-Defaultbild während die Refreshsession noch aktiv ist;
- USB-/hidraw-Exception, Short Write, falscher Writecount oder internem
  Senderfehler;
- sichtbaren Artefakten, Müllbild oder Freeze;
- Disconnect oder Reenumeration des Geräts;
- weniger als fünf vollständigen Frames, sofern nicht der Bediener bewusst
  vorher gestoppt hat.

Ein sichtbarer Fehlschlag bei vollständigem Transport ist als Queue-/Timing-/
Decoder-/Ownership-Befund zu protokollieren. Er autorisiert weder Retry noch
ein schnelleres Intervall in derselben Session.

## 5. Code-Readiness und verbleibendes Risiko

Der bestehende Pfad erfüllt die technische Sequenz:

- `RefreshController` sendet synchron, ohne Framequeue, Überlappung oder
  Catch-up; Prozesslocks verhindern zwei eigene Sender;
- `HidrawFrameSender` delegiert jeden vollständigen Frame an die unveränderte
  `send_frame_once()`-Semantik;
- `send_frame_once()` validiert Ziel und 1024-Byte-OUT-Descriptor vor jedem
  Segment, schreibt ausschließlich `0x08`, liest nicht, retried nicht und
  schließt das Handle in `finally`;
- der erste Fehler beendet die Session; GUI und CLI starten weiterhin keinen
  Refresh automatisch.

Eine minimale technische Ergänzung war erforderlich: Das erste Liveprofil ist
nun durch Referenzhash, 1,0 s, 6,0 s und fünf Frames offline fest verdrahtet
und mit zwei zusätzlichen Tests abgedeckt. Die gesamte ausschließlich offline
laufende Suite endet mit 82 erfolgreichen Tests. Es wurde kein Live-Einstieg
ergänzt. Ausschluss externer Writer, temporäre Rechte und sichtbare Beurteilung
bleiben bewusst operative Gates.

Persistenzbewertung:

- Im analysierten v51-`0x08`-Pfad sind SPI-/Flashwrite, Firmwareupdate,
  Bootloader/Reset, persistente Konfiguration und hostgewählte persistente
  Zieladresse **nicht erreichbar**.
- Wiederholung desselben gültigen `0x08` erweitert den Kontrollfluss nicht;
  sie erhöht nur flüchtige Queue-, Decoder- und Displaylast.
- Für die nicht vorliegende v49-Binärdatei bleibt die formale statische
  Reachability unbekannt. Der reale Erfolg exakt dieses Transfers stützt aber
  den normalen JPEG-/Displaypfad. Persistenter Schaden erforderte eine
  zusätzliche, bislang unbelegte v49-Kante vom normalen `0x08`-Pfad zu einem
  persistenten Writer oder persistent adressierbaren Ziel; Wiederholung allein
  erzeugt sie nicht.

Das verbleibende reale Risiko des normierten Fünfframe-Tests ist daher
vorwiegend flüchtig: stille Queueverwerfung, ausbleibender Commit,
Displayartefakt, USB-Stall/-Disconnect oder im ungünstigen Fall Replug/Reboot.
Ein persistenter Schaden ist theoretisch wegen der fehlenden v49-Binäranalyse
nicht absolut ausschließbar, aber durch keinen bisherigen Befund gestützt und
wird durch die Wiederholung nicht strukturell wahrscheinlicher.

## 6. Normative Live-Sequenz für ein Folgeticket

1. Alle konkurrierenden LCD-Writer beenden und rein lesend verifizieren, dass
   niemand den Zielknoten offen hält.
2. `0b05:1c7b` dynamisch finden; ausschließlich Interface 1 sowie VID, PID,
   hidraw/sysfs-Zuordnung, 1024-Byte-OUT-Report und fehlende Report-ID prüfen.
3. Ursprüngliche Rechte des einen Interface-1-Knotens erfassen; nur dort
   temporäres Schreibrecht setzen.
4. Die eingefrorene Referenzdatei laden, SHA-256 und JPEG-Vertrag prüfen und
   mit `build_first_refresh_live_test_plan()` exakt den fixierten Plan bauen.
5. Alle drei Reports des Frames vorab im RAM bauen und lokal validieren. Keine
   Geräteöffnung vor Abschluss sämtlicher Preflightprüfungen.
6. Genau einen Controller mit `HidrawFrameSender` explizit starten: 1,0 s,
   höchstens 6,0 s, höchstens fünf vollständige Frames/15 Writes.
7. Bei erstem Fehler stoppen; kein Retry, keine Recovery, kein Interface 0,
   kein IN-Read, kein zweiter Versuch und keine Intervalländerung.
8. Transportresultat und sichtbare Beobachtung strikt getrennt protokollieren;
   Reenumeration, Artefakte oder Default während der Session sind Fehler.
9. Devicehandle schließen, Controller joinen und die ursprünglichen Rechte im
   `finally` wiederherstellen. Danach nur passiv beobachten.
