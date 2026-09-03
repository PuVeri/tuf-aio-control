# Code-Review des ersten begrenzten LCD-Refresh-Tests

Stand: 2026-09-03

## Ergebnis und Evidenzgrenze

Der fest begrenzte Einstieg `src/test_lcd_refresh.py` erfüllt das in
`lcd-first-refresh-live-readiness.md` freigegebene Profil. Der Review und alle
Tests waren offline; es gab keine Gerätekommunikation, keinen hidraw-Open und
keinen HID-Write. Der reale Test wurde noch nicht ausgeführt.

**Review-Ergebnis: PASS.** Der Code ist für genau einen späteren, gesondert
autorisierten Lauf bereit. Das gilt nicht für andere JPEGs, Raten,
Framezahlen, GIF, Dauerbetrieb oder Fehlerprovokation.

## 1. Expliziter Einstieg und feste Grenzen

Der Standardaufruf und `--dry-run` enden nach Preview ohne Geräteöffnung.
Nur der nicht abkürzbare Schalter `--i-understand-the-risk` erreicht
`prepare_test()` und `run_live()`. Die Kommandozeile bietet weder Bildpfad noch
Intervall-, Dauer- oder Frameparameter.

Die Werte stammen ausschließlich aus dem zuvor geprüften Offline-Profil:

```text
Referenz-SHA-256  5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866
JPEG              2236 Byte, N=3
Frames            5
Writes maximal    15
Startintervall    1,0 s
Sessiongrenze     6,0 s
```

`RefreshController` plant nach tatsächlichen Frame-Startzeitpunkten. Ein
langsamer synchroner Transfer verzögert den nächsten Start; er löst keinen
Paralleltransfer und keinen Catch-up aus. Prozessweite Nonblocking-Locks
schließen einen zweiten projektierten Sender aus.

## 2. Vollständiger Preflight

`discover_device.py` wurde read-only um die bereits bekannten sysfs-Felder
erweitert. Neben Reportgrößen und Report-IDs liefert es nun:

- HID Usage Page und erste Usage aus dem Reportdescriptor;
- `bcdDevice`;
- Alternate Setting sowie Interfaceklasse, -subklasse und -protokoll;
- deklarierte Endpointzahl;
- Endpointadresse, Attribute, maximale Paketgröße und Intervall.

`strict_device_error()` verlangt exakt VID/PID `0b05:1c7b`, Interface 1,
den numerischen `bcdDevice`-Wert `0x0049`, Usage `ff06/01`, HID `03/00/00`,
unnummerierte Reports mit
16 Byte IN und 1024 Byte OUT sowie die Endpointfolge `03 OUT/1024` und
`84 IN/16`. Hersteller und Produkt werden geprüft, wenn sysfs sie liefert;
abweichende vorhandene Werte werden abgelehnt.

Der ursprüngliche Stringvergleich erwartete `0.49`, während sysfs auf dem
realen Gerät korrekt `0049` liefert. `parse_bcd_device()` normalisiert jetzt
beide Darstellungen sowie die explizite Form `0x0049` auf denselben
16-Bit-Wert und vergleicht ihn ausschließlich mit `0x0049`. `0051`, andere
Werte und syntaktisch ungültige Angaben werden abgelehnt. Die Preview darf den
Sollwert weiterhin als `0.49` darstellen.

Vor Sessionstart lädt der Code nur die feste reguläre Referenzdatei, prüft
Hash und JPEG-Profil, verlangt `N=3` und erzeugt fünf vollständige
Dreireportfolgen im RAM. `validate_prepared_profile()` prüft die daraus
resultierenden 15 Reports einschließlich Controlword, Reihenfolge,
1025-Byte-Framing und Nullpadding.

Der Transport besitzt nun zwei optionale zusätzliche Gates, ohne sein
Standardverhalten für Einzelbilder zu verändern:

1. `extra_validator` prüft das jeweils frisch wiederentdeckte Device vor jedem
   Write;
2. `extra_transfer_validator` prüft vor dem Open und vor jedem Write erneut
   Hash, JPEG, `N`, fixes Timingprofil und alle 5×3 vorbereiteten Reports.

Jeder Gatefehler liegt vor `os.write()` und bricht ohne Retry ab.

## 3. Konkurrenzprüfung

`find_competing_writers()` vergleicht über `/proc/<pid>/fd` die tatsächliche
Character-Device-Nummer des dynamisch ausgewählten LCD-hidraw-Knotens. Nur
write-fähige oder hinsichtlich des Open-Modus nicht sicher lesbare fremde FDs
werden als Konkurrenz behandelt. Read-only-FDs werden nicht als Writer
klassifiziert. Der eigene Prozess wird übersprungen, weil sein aktueller
per-Frame-Descriptor andernfalls die Vor-Write-Revalidierung selbst sperren
würde.

Die Prüfung beendet keine Prozesse und ist exakt auf das Ziel-`st_rdev`
begrenzt. OpenRGBs getrenntes `0b05:19af` wird nicht berührt. Nicht einsehbare
fremde `/proc`-Verzeichnisse und das Race zwischen Prüfung und Write bleiben
Grenzen des rein lokalen Verfahrens und müssen operativ berücksichtigt werden.

## 4. Write-, Fehler- und Closepfad

Im gesamten neuen Refreshpfad
`test_lcd_refresh.py -> lcd_refresh.py -> lcd_transport.py` existiert genau
**eine** `os.write()`-Quelltextstelle, unverändert in `lcd_transport.py`. Der
neue Einstieg selbst besitzt keine Write- und keine Read-Callsite. Über alle
`src/*.py` existieren drei `os.write()`-Stellen: zusätzlich der getrennte
`0x87`-Test und der allgemeine Input-/Diagnosehelfer. Keiner dieser beiden
Pfade ist aus dem Refresh-Einstieg erreichbar.

Die einzige erreichbare Stelle erhält ausschließlich die vorab erzeugten
`0x08`-Reports. Bei Write-Exception oder Rückgabewert ungleich 1025 endet
`send_frame_once()` sofort. Der Controller wertet außerdem eine Writezahl
ungleich `N` als ersten Fehler. Es gibt keinen Retry, keine Recovery, keinen
IN-Read und keinen Interface-0-Aufruf.

Der hidraw-Descriptor liegt innerhalb eines `finally` und wird im Erfolgs- und
Fehlerfall geschlossen. Pro vollständig abgeschlossenem Frame gibt es genau
ein Open/Close-Paar. Der vorbereitete Sender verweigert jeden sechsten
Frameaufruf unabhängig vom Controllerlimit.

## 5. Laufzeitprotokoll und Erfolgsaussage

`LoggedPreparedSender` protokolliert für jeden Frame Index, relative Startzeit,
Transferdauer, vollständige Writezahl und Ergebnis. Nach fünf erfolgreichen
Frameaufrufen akzeptiert `run_live()` nur `MAX_FRAMES` mit fünf gemessenen
Transfers als Transporterfolg und gibt aus:

```text
TRANSPORTERFOLG: 5 Frames / 15 vollständige Writes.
```

Unmittelbar danach weist es darauf hin, dass sichtbarer Erfolg nicht
automatisch behauptet wird. Der Benutzer muss separat beobachten, ob das
Referenzbild während der aktiven Session ohne zwischenzeitliches ASUS-
Defaultbild sichtbar bleibt.

## 6. Offline-Testabdeckung

27 neue Offline-Tests prüfen:

- Standardpreview, expliziten Dry-Run und fehlende/abgekürzte Bestätigung;
- falsches VID/PID, Interface, `bcdDevice`, Outputreport, Usage und
  Endpointprofil einschließlich sysfs-Parser;
- Referenzhash und `N`;
- konkurrierenden Writer;
- fünf Frames, 15 vorbereitete und 15 ausgeführte Writes;
- Startzeiten `0, 1, 2, 3, 4` s bei schnellen Transfers;
- langsamen ersten Transfer ohne Überlappung oder Catch-up;
- Stop beim ersten Writefehler ohne Retry;
- Close im Erfolg und Fehler;
- Vor-Open-/Vor-Write-Aufrufe beider Zusatzgates;
- ausschließlich `0x08` in sämtlichen vorbereiteten Reports;
- genau eine `os.write()`- und keine `os.read()`-Callsite im Refreshpfad.

Wegen der gewünschten Datei `src/test_lcd_refresh.py` wurde die gleichnamige
bisherige Controller-Testdatei ohne Inhaltsänderung nach
`tests/test_lcd_refresh_controller.py` verschoben. Dadurch bleibt
`unittest discover -s tests` eindeutig.

Die vollständige Suite meldet:

```text
Ran 109 tests
OK
```

## 7. Verbleibende Risiken

- Ein erfolgreicher Hostwrite belegt keine geräteseitige Queueannahme,
  Decoderfertigstellung oder Sichtbarkeit.
- Die maximale sichere v49-Rate, Lease-Wandzeiteinheit und Ringgröße bleiben
  unbekannt; das feste 1-s-Profil ist ein konservativer Testpunkt, keine
  ermittelte Grenzrate.
- Die `/proc`-Prüfung kann nicht einsehbare Prozesse nicht ausschließen und
  besitzt ein kleines TOCTOU-Race.
- Die Sechs-Sekunden-Grenze verhindert einen weiteren Frame, kann aber einen
  bereits laufenden Kernelaufruf nicht gewaltsam beenden. Der Knoten wird
  `O_NONBLOCK` geöffnet.
- Rechteentzug nach dem Test ist absichtlich kein Programmfeature und muss
  als äußerer `finally`-Schritt der autorisierten Bediensequenz erfolgen.
- Persistente Pfade sind im analysierten v51-`0x08`-Unterbaum nicht
  erreichbar. Die v49-Binärdatei fehlt weiterhin; eine zusätzliche
  persistente Kante ist theoretisch unbekannt, aber durch keinen Befund
  gestützt und wird durch fünf byteidentische Transfers nicht neu erzeugt.
