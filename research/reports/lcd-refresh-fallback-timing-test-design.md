# Design des begrenzten LCD-Fallback-Zeitmesstests

Stand: 2026-09-03

## Zweck und Evidenzgrenze

Der zweite Refresh-Live-Test soll ausschließlich messen, wann nach dem letzten
vollständig übertragenen Referenzframe das ASUS-Defaultbild wieder sichtbar
wird. Dieses Ticket bereitet den Test offline vor. Es fand keine
Gerätekommunikation, kein hidraw-Open und kein HID-Write statt.

Der Test automatisiert nur Transportprotokoll und Zeitbasis. Sichtbarkeit,
Default-Unterdrückung und der Moment des Fallbacks bleiben menschliche
Beobachtungen und werden nicht aus erfolgreichen Writes abgeleitet.

## Unverändertes Transportprofil

`src/test_lcd_refresh_fallback.py` verwendet den vorhandenen Preflight und den
bereits real bewährten Transportpfad aus `src/test_lcd_refresh.py`. Es gibt
keine frei konfigurierbaren Transportparameter.

| Grenze | Fester Wert |
| --- | ---: |
| Referenz-JPEG | eingefrorene, per SHA-256 gebundene 2236-Byte-Datei |
| Segmente je Frame | `N=3` |
| vollständige Frames | exakt 5 |
| Writes | maximal 15, jeweils exakt 1025 Byte |
| Frame-Startabstand | 1,0 s |
| maximale Transportdauer | 6,0 s |
| Retry / Catch-up / Recovery | keiner / keiner / keine |
| USB-Pfad | ausschließlich Interface 1, Opcode `0x08` |
| Interface 0 / Interface-1-IN | keine Kommunikation / kein Read |

Alle bestehenden Gates bleiben zwingend: dynamisch gefundenes
`0b05:1c7b`, Interface 1, `bcdDevice == 0x0049`, Usage `ff06/01`, bekanntes
Report- und Endpointprofil, Referenzhash, `N=3`, vollständig vorgebaute und
validierte 5×3 Reports sowie Ausschluss eines lokal erkennbaren
konkurrierenden Writers. Im gesamten erreichbaren Refreshpfad bleibt genau
eine `os.write()`-Quelltextstelle in `lcd_transport.py`.

## Messmethode

Der Live-Einstieg besitzt weiterhin standardmäßig nur eine Preview. Erst der
nicht abkürzbare Schalter `--i-understand-the-risk` kann nach bestandenem
Preflight den festen Transport starten. Vorher weist die Ausgabe darauf hin,
während der fünf Frames manuell auf ein kurz dazwischen erscheinendes
Defaultbild zu achten. Dieses Zwischenframe-Ergebnis wird nicht automatisch
erkannt.

Der Ablauf ist fest:

1. Unmittelbar vor Start des Controllers wird `t_start` mit
   `time.monotonic()` erfasst.
2. Der bestehende synchrone Sender überträgt genau fünf vollständige Frames.
   Nach jedem Frame schließt `send_frame_once()` sein Handle im `finally`.
3. `t_last` wird erst nach erfolgreicher Rückkehr des fünften
   `send_frame_once()` erfasst. Zu diesem Zeitpunkt ist dessen Devicehandle
   bereits geschlossen.
4. Der Controller wird vollständig beendet und gejoint. Erst danach beginnt
   die passive Beobachtungsfunktion.
5. Sie wartet höchstens 20,0 Sekunden ausschließlich auf Enter über stdin.
   Ein Tastendruck erfasst wieder `time.monotonic()` und gibt sowohl die Zeit
   seit `t_start` als auch seit `t_last` aus.
6. Ohne Meldung lautet das Ergebnis ausdrücklich
   `Kein beobachteter Fallback innerhalb 20 s.` Nach Frame 5 gibt es unabhängig
   vom Beobachtungsergebnis keine weiteren Writes.

Die Beobachtungsfunktion importiert oder öffnet keinen Gerätepfad. Sie führt
keine Discovery, keinen sysfs-, USB- oder hidraw-Zugriff und weder Read noch
Write auf dem LCD aus. stdin dient nur der manuellen Zeitmarke.

## Strikte Ergebnistrennung

Die spätere Dokumentation muss vier Aussagen unabhängig behandeln:

- **Transporterfolg:** fünf vollständige Frames und 15 vollständige Writes;
- **Referenzbild sichtbar:** manuell ja/nein beobachtet;
- **Default-Unterdrückung während der aktiven Phase:** manuell ja/nein, ohne
  automatische Erkennung;
- **Fallback nach Frame 5:** gemessene Zeit seit `t_last`, oder lediglich
  kein beobachteter Fallback innerhalb des 20-s-Fensters.

Ein Transporterfolg bestätigt keine der drei visuellen Aussagen. Keine
Fallbackmeldung innerhalb von 20 Sekunden beweist außerdem keine dauerhafte
Unterdrückung nach Ende des Fensters.

## Offline-Prüfung

Sieben neue Tests decken den Zeitmessteil ab:

- die Beobachtung beginnt erst, nachdem das fünfte Handle geschlossen wurde;
- vor und während der Beobachtung sind bereits genau 15 Writes abgeschlossen,
  danach bleibt der Zähler unverändert;
- der Beobachtungspfad ruft weder HID-/USB-/Discoveryfunktionen noch
  `os.open()`, `os.read()` oder `os.write()` auf;
- eine Enter-Meldung liefert die korrekten monotonen Differenzen zu `t_start`
  und `t_last`;
- der Timeoutwert ist exakt 20,0 Sekunden und die Negativmeldung eindeutig;
- 1,0 s, 6,0 s, fünf Frames, 15 Reports und ausschließlich `0x08` bleiben
  unverändert;
- der Standardaufruf bleibt ohne hidraw-Open.

Zusammen mit den bestehenden Transport-, Preflight-, Fehler- und
Callsite-Tests läuft die vollständige Offline-Suite erfolgreich. Der neue
Einstieg erweitert weder Paketformat noch Gerätezugriff; er fügt nach der
beendeten Session nur eine passive Zeitmessung hinzu.

## Restrisiken und Freigabegrenze

Unverändert bleiben die bereits bekannten flüchtigen Risiken des realen
Fünfframe-Transports: USB-/hidraw-Fehler, stille Queueverwerfung,
Decoder-/Displayfehler, Artefakt, Disconnect oder ein eventuell nötiger
Replug/Reboot. Die fehlende v49-Binärdatei lässt die formale
Persistenz-Reachability unbekannt; kein bisheriger Befund stützt einen
persistenten Schadenspfad für den normalen `0x08`-JPEG-Pfad.

Die manuelle Reaktionszeit begrenzt die Genauigkeit des gemessenen
Fallbackzeitpunkts. Ein kurzzeitiges Defaultbild zwischen Frames kann nur
beobachtet, nicht automatisch zeitgestempelt werden. Das 20-s-Fenster kann
einen späteren Fallback nicht ausschließen.

**Readiness: JA**, aber ausschließlich für einen später gesondert
autorisierten Lauf dieses unveränderten festen Profils. Dieses Ticket selbst
enthält keine Autorisierung und führte keinen Live-Test aus.
