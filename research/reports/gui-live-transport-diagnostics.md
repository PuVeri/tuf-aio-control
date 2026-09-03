# Persistente GUI-Live-Transportdiagnostik

Datum: 2026-09-03

## Ziel und Grenze

Der zweite GUI-Live-Test ist offline durch eine sessionspezifische,
persistente JSONL-Diagnostik vorbereitet. Dieses Ticket führte keine
Gerätekommunikation, kein hidraw-Open, keinen HID-/USB-Write und keinen
Live-Test aus. `lcd_transport.py`, der bestätigte `0x08`-Transport und seine
Paketbytes wurden nicht verändert.

Ausgangspunkt war der visuell negative erste GUI-Lauf: Die GUI und ihre
Sensor-/Overlaydarstellung funktionierten, das physische LCD zeigte jedoch
durchgehend das ASUS-Defaultbild. Weil Aufruf- und Write-Zahlen nicht
persistiert wurden, ließ sich nach Prozessende nicht mehr unterscheiden, ob
der GUI-Worker den bestätigten Transport überhaupt erreicht hatte.

## Statischer Vergleich zum erfolgreichen Fünfframe-Pfad

| Aspekt | Erfolgreicher `test_lcd_refresh.py`-Pfad | GUI-Produktionspfad |
|---|---|---|
| Geräteöffnung | Dynamisch erkanntes und streng geprüftes Interface 1; `send_frame_once()` öffnet pro Frame | Dieselbe dynamische Zielerkennung und gemeinsame Runtime-Gates; `send_frame_once()` öffnet ebenfalls pro Frame |
| Sender | `LoggedPreparedSender` mit fixiertem Referenz-JPEG und vorgebauten Segmenten | bestehender generischer `HidrawFrameSender` mit dynamischem GUI-JPEG |
| FrameSource | keine dynamische `FrameSource`; genau ein unveränderliches Referenz-JPEG im Plan | sessionspezifischer `LatestFrameBuffer`; Snapshot unmittelbar vor jedem Refresh |
| RefreshPlan | 1,0 s, maximal 6,0 s, exakt 5 Frames, Referenzhash erzwungen | 1,0 s, maximal 30,0 s, maximal 30 Frames, initiales GUI-JPEG im Einframeplan |
| Framegrenzen | fünf Frames zu je exakt drei vorbereiteten Segmenten; 15 Writes vorab geprüft | Segmentzahl folgt dem jeweils validierten Snapshot; Vollständigkeit wird pro Transfer gegen dessen `JpegInfo` geprüft |
| `send_frame_once()` | explizit aus `LoggedPreparedSender`, mit `prepared_segments`, Profil-Revalidator und `write_observer` | aus `HidrawFrameSender`, mit Runtime-Gerätevalidator; nun zusätzlich mit rein beobachtendem `write_observer` |
| Handle-Lebensdauer | ein Open/Close pro Frame in `send_frame_once()`; der Sender protokollierte vorher nur auf stdout | ein Open/Close pro Frame in demselben `send_frame_once()`-`finally`; nun persistent nach Rückkehr bestätigt |

Der diagnostisch entscheidende Unterschied war nicht ein zweiter
Transportalgorithmus, sondern die Beobachtbarkeit: Der erfolgreiche
Fünfframe-Pfad zählte seine Writes lokal über `write_observer` und druckte das
Ergebnis. Der GUI-Sender gab bislang nur die Rückgabe von `send_frame_once()`
an den Controller weiter. Der Controller hielt sein Endergebnis nur im
Prozessspeicher. Nach dem Schließen der GUI waren daher weder der tatsächliche
Senderaufruf noch Teil-Writes, Generationen, Framezahl oder Laufzeit
rekonstruierbar.

Die weiteren Unterschiede sind bewusst: Das Testwerkzeug fixiert genau das
bereits erfolgreiche Referenz-JPEG und drei vorbereitete Segmente, während die
GUI aktuelle, vollständig validierte Bildpipeline-Snapshots übertragen muss.
Aus der statischen Prüfung folgt kein Beleg, dass einer dieser Unterschiede
den negativen Sichtbefund verursacht hat.

## Implementierte Diagnostik

`src/refresh_diagnostics.py` schreibt für jeden expliziten GUI-Start eine
eigene Datei nach `logs/gui-refresh-<Zeit>-<ID>.jsonl`. Jede Zeile wird unter
einem Thread-Lock geschrieben und geflusht. Sie enthält eine Session-ID, einen
mit `time.monotonic()` erfassten Zeitstempel, den Ereignisnamen und kleine
Metadaten. JPEG-Bytes, HID-Reports und sonstige Payloads werden nicht
protokolliert; die Dateien sind als lokale Laufzeitdaten von Git ausgenommen.

Die Ereigniskette umfasst:

- Startanforderung, initiale Publikation und initiale Snapshotgeneration;
- Eintritt und erfolgreichen Abschluss der `ProductionControllerFactory`;
- ausgewählten dynamischen hidraw-Pfad sowie bestandene oder fehlgeschlagene
  Safety-Gates;
- Controllererzeugung und tatsächlichen Workerstart;
- Snapshotgeneration und geplante Segmentzahl jedes Refreshs;
- Transferbeginn und tatsächlichen Aufruf von `send_frame_once()`;
- die kumulierte Anzahl vollständig zurückgekehrter Segment-Writes je
  erfolgreichem oder fehlgeschlagenem Senderaufruf;
- Rückkehr oder Fehler von `send_frame_once()`, validierten Frameerfolg,
  Transferdauer und fortgeschriebenen Framezähler;
- Stopanforderung und terminalen Grund `user`, `30 s`, `30 Frames`,
  `transport error` oder `sonstiger Fehler`;
- Renderfehler als gesondertes `render error`-Ereignis, ohne die bestehende
  Regel zu ändern, dass der alte gültige Snapshot weiterläuft;
- Workerende und nach erfolgreicher Sender-Rückkehr den durch das bestehende
  `send_frame_once()`-`finally` bestätigten Handle-Close.

Bei einem Senderfehler nach mindestens einem beobachteten Write ist der Close
ebenfalls durch den unveränderten `finally`-Pfad bestätigt. Tritt der Fehler
vor dem ersten beobachteten Write auf, protokolliert die Diagnostik den
Close-Status bewusst als nicht unterscheidbar: Der Fehler kann vor dem Open
oder nach dem Open beim ersten Write entstanden sein. Diese Unterscheidung
wäre ohne Änderung des Transportcodes nicht seriös möglich.

Exceptions aus Discovery/Safety-Gates, Factory-/Controlleraufbau,
`send_frame_once()`, Worker, GUI-Start, Stopanforderung und Rendering werden
mit Phase, Exception-Typ und auf 500 Zeichen begrenzter Meldung persistiert.
Es wurden weder Retry noch automatische Recovery ergänzt.

## Offline-End-to-End-Nachweis

Ein neuer Headless-Qt-Test benutzt ein Fake-Gerät, die echte
`ProductionControllerFactory`, den echten `RefreshController`, die echte
`LatestFrameBuffer`-`FrameSource` und den bestehenden `HidrawFrameSender`.
Nur `lcd_transport.send_frame_once()` ist an der Gerätezugriffsgrenze durch
einen Fake ersetzt. Dieser ruft den echten diagnostischen `write_observer` für
die offline gebauten Segmente auf. `os.open()` ist gleichzeitig als verbotener
Call überwacht.

Der nachgewiesene Ablauf lautet:

```text
GUI-Start
-> ProductionControllerFactory
-> RefreshController
-> 30 × FrameSource.snapshot()
-> 30 × send_frame_once()
-> 90 simulierte vollständige Segment-Writes
-> MAX_FRAMES
```

Der resultierende Framezähler ist exakt 30, der Sender wurde exakt 30-mal
aufgerufen, maximal ein Sender war gleichzeitig aktiv, und das persistierte
Terminalereignis enthält `30 Frames`. Die Zeitstempel sind in Dateireihenfolge
monoton, die Ereignisse enthalten keine JPEG-Payload. Zusätzliche Tests
belegen persistierte Factory-/Gate- und Sender-/Resultat-Exceptions sowie den
Abbruch beim ersten Transportfehler ohne Retry.

Die vollständige Offline-Suite bestand mit 171 Tests. `git diff --check` und
`compileall` waren sauber. Kein Test öffnete ein reales hidraw-Gerät.

## Gefundener Bug und Aussagegrenze

Es wurde kein klarer funktionaler Offline-Bug im GUI-Produktionspfad gefunden.
Insbesondere erreicht der vollständige Fake-Pfad den Sender, erhöht den
Framezähler und endet am 30-Frame-Hardcap. Repariert wurde daher keine
spekulative Transport- oder Protokollannahme.

Der konkrete Fehler des ersten Tickets war eine Diagnoselücke: Der nur im RAM
vorhandene `RefreshResult` und fehlende Write-Beobachtung machten den realen
Transportverlauf nach dem GUI-Ende unbelegbar. Diese Lücke ist geschlossen.

## Daten des nächsten manuellen Live-Tests

Nach genau einem erneut freigegebenen Lauf lässt sich aus der JSONL-Datei
belegen, ob und wann die Gates bestanden, welches Interface gewählt, der
Worker gestartet und welche Snapshotgeneration je Frame verwendet wurde. Für
jeden Versuch sind Aufruf von `send_frame_once()`, Soll- und vollständige
Ist-Segmente, Erfolg oder Exceptionphase, Transferdauer, Framezähler,
Stopgrund, Workerende und Handle-Close auswertbar.

Diese Transportdaten müssen weiterhin getrennt von der menschlichen
Sichtbeobachtung des LCD bewertet werden. Erst diese Kombination kann zeigen,
ob der zweite Lauf den Transport gar nicht erreicht, unvollständig schreibt,
vollständig schreibt ohne sichtbaren Commit oder trotz vollständiger Frames
vom ASUS-Defaultproduzenten überlagert wird.
