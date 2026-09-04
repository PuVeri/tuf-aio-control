# hidraw-Transportleistung und persistente Produktionssession

Stand: 2026-09-04

## Ergebnis und Sicherheitsgrenze

Der bisherige Produktionspfad öffnete und schloss `/dev/hidraw*` für jeden
vollständigen JPEG-Frame und wiederholte innerhalb jedes Segmentdurchlaufs
umfangreiche read-only Geräteprüfungen. Der neue Produktionspfad hält genau
einen validierten FD für die Lebensdauer genau einer Refreshsession offen.
`send_frame_once()` bleibt in Verhalten und Lifecycle unverändert als
Legacy-/Einzelbildpfad verfügbar. Segmentierung, Controlbytes,
Reportreihenfolge, 1025-Byte-hidraw-
Framing und JPEG-Payload werden von beiden Lifecycles gemeinsam benutzt.

Dieses Ticket enthielt keinen realen HID-/USB-Write und keinen Live-Test. Es
führt keine neuen Opcodes, kein Interface 0, kein `0b05:19af`, keinen Retry,
Reconnect, Nonblocking-Versuch, Paralleltransfer oder Write-Queue ein.

## Read-only-Auswertung des realen Ausgangslogs

Quelle:
`~/.local/state/tuf-aio-control/gui-refresh-20260904-165355-c912e06c.jsonl`
(507.456 Byte, ausschließlich gelesen).

Das Log enthält 329 vollständige `send_frame_once_returned`-Ereignisse. Zu
jedem davon existieren genau ein `send_frame_once_called`, ein
`handle_closed` und ein erfolgreiches Frameereignis. Zeiten sind die im alten
`HidrawFrameSender` gemessenen Intervalle einschließlich JPEG-Prüfung,
Segmentbau, Geräte-/FD-Prüfungen, `open`, aller Writes, `close` und des vor dem
Aufruf geschriebenen Diagnoseereignisses.

| Segmente | Frames | Minimum | Median | Mean | Maximum | Mean/Segment |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 16 | 216,212 ms | 224,001 ms | 224,599 ms | 236,942 ms | 28,075 ms |
| 9 | 74 | 234,033 ms | 244,693 ms | 245,694 ms | 272,615 ms | 27,299 ms |
| 10 | 32 | 257,826 ms | 263,618 ms | 264,486 ms | 280,896 ms | 26,449 ms |
| 11 | 27 | 272,471 ms | 282,736 ms | 283,549 ms | 303,246 ms | 25,777 ms |
| 12 | 12 | 293,734 ms | 299,396 ms | 301,345 ms | 317,035 ms | 25,112 ms |
| 13 | 25 | 314,330 ms | 320,245 ms | 321,608 ms | 338,988 ms | 24,739 ms |
| 14 | 85 | 192,265 ms | 341,071 ms | 339,966 ms | 363,328 ms | 24,283 ms |
| 15 | 58 | 348,749 ms | 360,024 ms | 360,101 ms | 386,912 ms | 24,007 ms |

Das 14-Segment-Minimum gehört zum letzten Frame, dessen Transfer den
`stop_requested`-Zeitpunkt überlappt. Die robuste Regression über die 328 vor
diesem Stop abgeschlossenen Frames lautet:

```text
Transferzeit ≈ 72,430 ms + 19,201 ms × Segmentzahl
R² ≈ 0,9805
```

Unter Einschluss des letzten Frames ergeben sich 73,816 ms Fixanteil plus
19,048 ms pro Segment bei R²≈0,9513. Der Regressionsachsenabschnitt ist nur der
statistische gemeinsame Fixanteil des gesamten alten Codepfads; er beweist
nicht, dass `open`/`close` allein so lange dauern.

Die Session sendete 329 Frames in 106,3383 s, entsprechend 3,0939 FPS. Die
329 zugehörigen JPEGs liegen zwischen 8.091 und 14.709 Byte (7,90–14,36 KiB).
Ihr effektiver End-to-End-Nutzdatendurchsatz beträgt 36.161 Byte/s bzw.
35,31 KiB/s. Zwischen erfolgreichem Transferereignis und nächster
Framepublikation lagen im Median 19,968 ms, im Mittel 20,646 ms
(12,766–27,254 ms). Rendering und Producer sind damit im beobachteten Lauf
kleiner als die alte Transportzeit; welcher Anteil in `open`, Prüfung oder
`write` liegt, konnte das alte Log nicht trennen.

## Audit des bisherigen Codepfads

Der alte Produktionsaufruf war:

```text
ProductionControllerFactory
→ Discovery Interface 1
→ runtime_device_error() einschließlich Konkurrenzwriterprüfung
→ HidrawFrameSender.__call__() pro Frame
→ send_frame_once()
```

`send_frame_once()` führte pro Frame aus:

1. globalen nichtblockierenden Sender-Lock erwerben;
2. JPEG validieren, Segmente bauen und alle Transferinvarianten prüfen;
3. Device-Metadaten, zusätzlichen Production-Validator und Schreibrecht
   prüfen;
4. `os.open(O_WRONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW)`;
5. vor jedem Segment `validate_open_target()` und erneut alle
   Transferinvarianten ausführen;
6. genau einen `os.write(fd, 1025-Byte-Puffer)` pro Segment ausführen;
7. im inneren `finally` stets `os.close(fd)`, danach Sender-Lock freigeben.

`validate_open_target()` führte vor jedem alten Segment unter anderem
`fstat`, Lesen der sysfs-Gerätenummer, erneute USB-/hidraw-Discovery und den
zusätzlichen `runtime_device_error()` aus. Letzterer prüfte wieder das strikte
Profil und suchte über `/proc/*/fd` nach konkurrierenden Writern. Damit lagen
im gemessenen alten `send_frame_once()` nicht nur Open, Writes und Close,
sondern auch wiederholte sysfs-/Discovery-/proc-Arbeit.

Zwischen Segmentwrites gibt es im Code keine Sleeps, Timer-Waits, Polls,
Reads, Retrypausen oder Queueoperationen. Die Writes werden strikt seriell
aufgerufen: der nächste beginnt erst, nachdem der vorherige `os.write()`-
Systemaufruf zurückgegeben hat. Wegen `O_NONBLOCK` und fehlender Kernel-/USB-
Tracingdaten beweist diese Rückkehr jedoch nicht den Zeitpunkt der physischen
Busübertragung.

## Neuer persistenter Lifecycle

`PersistentHidrawSession` besitzt ausschließlich Transportverantwortung:

```text
Refreshworker startet
→ vollständige Production-Gates
→ globalen Sender-Lock erwerben
→ Device prüfen und einmal öffnen
→ offenen FD gegen sysfs/Discovery erneut validieren
→ Frame N: gemeinsamer Segmentbau, serielle gemeinsame Write-Callsite
→ Frame N+1: derselbe FD, dieselbe Reihenfolge
→ Stop, Quit oder erster Fehler
→ FD einmal schließen und Sender-Lock freigeben
```

Der `RefreshController` erkennt den optionalen `open()`/`close()`-Lifecycle
des neuen `PersistentHidrawFrameSender`, öffnet vor der Sendeschleife und
schließt im Worker-`finally`. Ein Write-/Disconnect-/Short-Write-Fehler beendet
den vorhandenen Refreshpfad beim ersten Fehler. Es gibt weder Wiederöffnung
noch Pfadwechsel noch Retry. Der Session-Lock bleibt über alle Frames
erworben; ein zweiter persistenter oder Legacy-Sender wird abgewiesen. Ein
separater nichtblockierender Frame-Lock weist auch einen parallelen Aufruf auf
derselben Session ab.

Die Production-Gates bleiben vor dem einzigen Open erhalten: exakt
`0b05:1c7b`, Interface 1, bcdDevice `0x0049`, Usage `ff06/01`, bekannte
Input-/Outputreportgrößen, keine Feature-Reports, HID-Klasse und bekanntes
Endpointprofil, dynamischer `/dev/hidraw*`-Pfad sowie kein konkurrierender
Writer. Direkt nach Open wird der FD einmal per `fstat`, sysfs-Gerätenummer und
erneuter zielgebundener Discovery revalidiert. Danach gehört er exklusiv der
Session; diese Dateisystemprüfungen werden nicht zwischen Segmentwrites
wiederholt.

Der Legacypfad bleibt `open → ein Frame → close`. Beide Pfade rufen dieselbe
`_write_segment()`-Funktion auf. Im erreichbaren JPEG-Transport existiert
weiterhin nur eine `os.write()`-Quelltextstelle. Offline sind die Reportbytes
und ihre Reihenfolge zwischen beiden Lifecycles byteidentisch bestätigt.

## Feingranulare Diagnostik für den nächsten Lauf

Der Produktionssender schreibt künftig payloadfreie JSONL-Ereignisse:

- einmal `persistent_session_opened` mit
  `session_open_duration_seconds` und reiner `open_duration_seconds`;
- pro Frame `persistent_frame_send_returned` beziehungsweise `...failed` mit
  Segmentzahl, Segmentindizes, einer geordneten Liste aller einzelnen
  `segment_write_durations_seconds`, `write_total_duration_seconds` und
  `send_frame_duration_seconds`;
- einmal `persistent_session_closed` mit
  `session_close_duration_seconds` und reiner `close_duration_seconds`.

Die Segmentzeiten werden während des Transfers nur im Speicher gesammelt und
erst nach dem kompletten Frame als ein JSONL-Ereignis geschrieben. Es gibt
daher weder Log-I/O noch `fsync()` zwischen Segmentwrites. Bestehende
Logrotation und Retention bleiben unverändert. Payload- und Reportbytes werden
nicht protokolliert.

Damit lassen sich erster, mittlerer und letzter Write direkt vergleichen. Die
Differenz zwischen `send_frame_duration` und `write_total_duration` zeigt den
verbleibenden reinen Frame-Overhead; einmalige Open-/Closewerte sind separat.

## JPEG-Encoder und reine Offline-Größenstichprobe

Der Defaultencoder bleibt unverändert bei Pillow/libjpeg-turbo, Qualität 60,
Subsamplingwert 2 (YCbCr 4:2:0), `progressive=False`, `optimize=False` und
Baseline SOF0. Typisch beobachtete reale GIF-Frames benötigten im Ausgangslog
8–15 Segmente; der vom Nutzer hervorgehobene Bereich lag bei 10–14.

InfoHub setzt für diesen Modus GDI+-JPEG-Qualität 60. SOF-Typ und Subsampling
werden dort nicht explizit als Encoderparameter gesetzt. Deshalb ist nur die
Qualität direkt vergleichbar, nicht Bytegleichheit des JPEG-Encoders.

Für fünf deterministisch ausgewählte Frames (0, 13, 27, 40, 53) des aktuell
lokal konfigurierten 54-Frame-GIFs wurden 320×320-JPEGs rein offline mit
4:2:0, non-progressive und `optimize=False` erzeugt:

| Qualität | Framegrößen in Byte | Segmentzahlen | Größenbereich | Mittel |
|---:|---|---|---:|---:|
| 60 | 10.309 / 11.229 / 6.011 / 4.466 / 10.226 | 11 / 12 / 6 / 5 / 11 | 4.466–11.229 | 8.448,2 |
| 50 | 8.976 / 9.837 / 5.303 / 4.022 / 8.894 | 9 / 10 / 6 / 4 / 9 | 4.022–9.837 | 7.406,4 |
| 40 | 7.753 / 8.541 / 4.702 / 3.638 / 7.687 | 8 / 9 / 5 / 4 / 8 | 3.638–8.541 | 6.464,2 |

Die Stichprobe zeigt nur den möglichen Größen-/Segmenttradeoff. Default 60
wurde bewusst nicht geändert, damit der nächste Transportvergleich nicht
gleichzeitig die Bildkompression verändert.

## Read-only USB-Descriptorbefund

Der aktuelle sysfs-Baum meldet das Zielgerät unter `/sys/bus/usb/devices/1-8`
mit `speed=480` (USB High Speed) und bcdDevice `0049`. Für Interface 1
(`/sys/bus/usb/devices/1-8:1.1`) wurden ausschließlich sysfs-Dateien gelesen:

- HID `03/00/00`, Alternate Setting 0, zwei Endpoints;
- EP `0x03` OUT, `bmAttributes=0x03` (Interrupt),
  `wMaxPacketSize=0x0400` = 1024 Byte, sysfs-Intervall 125 µs;
- EP `0x84` IN, Interrupt, 16 Byte, ebenfalls 125 µs.

Ein 1024-Byte-OUT-Serviceintervall von 125 µs entspräche rein rechnerisch
8,192 MB/s vor Protokoll-/Host-/Treiber-Overhead. Das ist nur eine
Descriptorobergrenze, keine Messung des hidraw-, Kernel- oder realen
Geräteverhaltens. Aus `speed=480` folgt ausdrücklich nicht, dass USB High
Speed selbst der beobachtete Engpass ist. Es wurden weder `lsusb -v` noch
Control Transfers oder HID-Writes ausgeführt.

## Offene Fragen für den nächsten manuellen Live-Test

Ein normal manuell gestarteter GUI-GIF-Lauf wird ohne separates
Benchmarkprotokoll beantworten:

1. Dauer des einmaligen Session-Open und des abschließenden Close;
2. Dauer jedes einzelnen Segmentwrites und Lage eines First-/Last-Write-
   Effekts;
3. vollständige Framezeiten insbesondere für 10, 12 und 14 Segmente;
4. Differenz zu den oben dokumentierten alten per-Frame-Zeiten;
5. reale persistente End-to-End-FPS und Nutzdatendurchsatz;
6. Verhältnis `write_total_duration` zu kompletter Framezeit und damit, ob
   der verbleibende Engpass überwiegend in `os.write()` oder außerhalb liegt.

Bis diese Werte real vorliegen, gibt es keine Aussage über den tatsächlichen
Gewinn und keine Grundlage für Async-USB, Pipelining, Batching oder niedrigere
JPEG-Qualität.
