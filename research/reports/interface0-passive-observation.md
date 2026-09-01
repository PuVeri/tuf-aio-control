# Passive Beobachtung von Interface 0

Stand: 2026-09-01, Europe/Berlin

## Kurzfazit

Interface 0 wurde in zwei getrennten, ausschließlich lesenden Läufen insgesamt
120 Sekunden beobachtet. Es traf kein Report ein. In einem der beiden Läufe
wurde Interface 1 für 60 Sekunden parallel als Vergleich beobachtet; auch dort
traf kein Report ein.

Damit wurde im beobachteten normalen Desktop-/Ruhezustand kein spontaner
440-Byte-Report nachgewiesen. Das macht einen gewöhnlichen unabhängigen Report
als Ursache des früheren `0x87`-Ergebnisses weniger wahrscheinlich, schließt
seltene, zustandsabhängige oder genau nach dem Öffnen eintreffende Reports aber
nicht aus.

## Sicherheitsgrenzen

- Verwendet wurde ausschließlich der vorhandene Beobachter
  `src/read_input.py`.
- Der Geräteknoten wird im Code ausschließlich mit
  `os.O_RDONLY | os.O_NONBLOCK` geöffnet.
- Der Beobachter enthält für den hidraw-Deskriptor nur `select()` und
  `os.read()`, keine Write- oder ioctl-Operation.
- Es wurde kein `--capture` angegeben. Es entstanden keine dauerhaften
  Rohcaptures.
- Die Geräteknoten blieben unverändert bei `0640`, Eigentümer `root`, Gruppe
  `input`. Für die Benutzergruppe bestand damit Lese-, aber kein Schreibrecht.
- Es wurde keine udev-Regel geändert, keine Schreibberechtigung aktiviert,
  nichts an die AIO gesendet und keine Firmwareaktion ausgeführt.
- Es wurde keine OpenRGB-Änderung ausgelöst, weil dies technisch eine
  USB-Schreiboperation an einem RGB-Gerät wäre und das ausdrückliche
  Schreibverbot Vorrang hat.

## Gerätezuordnung

Die vorhandene dynamische Erkennung bestätigte unmittelbar nach den Läufen:

| Merkmal | Interface 0 | Interface 1 |
| --- | --- | --- |
| USB-ID | `0b05:1c7b` | `0b05:1c7b` |
| aktueller hidraw-Knoten | `/dev/hidraw7` | `/dev/hidraw8` |
| `ID_USB_INTERFACE_NUM` | `00` | `01` |
| Inputreportgröße | 440 Byte | 16 Byte |
| Outputreportgröße | 440 Byte | 1024 Byte |
| Report-IDs | keine | keine |
| Modus | `0640` | `0640` |

Die hidraw-Nummern sind nur Teil dieser Beobachtung und keine dauerhaften
Gerätekennungen.

## Beobachtungsablauf

### Lauf A: Interface 0 im Ruhezustand

```text
python3 src/read_input.py --interface 0 --duration 60
```

Der Lauf öffnete ausschließlich Interface 0 und endete regulär mit:

```text
Beobachtung beendet: interface=0, reports=0, duration=60s
```

### Lauf B: normaler Desktopbetrieb mit Interfacevergleich

Interface 0 und Interface 1 wurden mit zwei Instanzen desselben Read-only-
Beobachters gleichzeitig jeweils 60 Sekunden geöffnet:

```text
python3 src/read_input.py --interface 0 --duration 60
python3 src/read_input.py --interface 1 --duration 60
```

Beide Läufe endeten regulär:

```text
Beobachtung beendet: interface=0, reports=0, duration=60s
Beobachtung beendet: interface=1, reports=0, duration=60s
```

Der anschließende dokumentierte Hostzeitpunkt war
`2026-09-01T19:26:51+02:00`. Der Beobachter hätte für jeden eingehenden Report
einen lokalen ISO-8601-Zeitstempel mit Millisekunden, Interface, Länge und den
vollständigen Hexdump ausgegeben. Da kein Report eintraf, gibt es keine
Reportzeitstempel, Längen oder Hexdumps aufzulisten.

Ein zunächst innerhalb des Sandbox-Namensraums gestarteter Parallelversuch
brach vor jedem Geräte-Open mit „Keine Leseberechtigung“ ab und zählt nicht als
Beobachtungslauf. Für die oben ausgewerteten Läufe wurde lediglich der
Geräteknotenzugriff des vorhandenen Read-only-Beobachters freigegeben.

## OpenRGB-Zustand

Während beider ausgewerteter Beobachtungsphasen lief bereits:

```text
/usr/bin/openrgb --startminimized --profile cyber blue
```

Der Prozess war seit `2026-09-01 18:00:48+02:00` aktiv. Eine passive
Handleprüfung nach den Beobachtungen zeigte offene `/dev/hidraw9`- und
`/dev/hidraw6`-Deskriptoren, aber weder `/dev/hidraw7` noch `/dev/hidraw8`.
OpenRGB hielt die beiden LCD-HID-Interfaces somit zu diesem Zeitpunkt nicht
offen.

Bestätigt ist nur: Der laufende OpenRGB-Prozess mit dem bereits geladenen
Profil erzeugte in den 120 Sekunden keinen auf Interface 0 sichtbaren Report;
im 60-Sekunden-Vergleich erschien auch auf Interface 1 nichts. Ob eine
**aktive RGB-Farb- oder Profiländerung** einen Effekt hätte, wurde nicht
geprüft und bleibt unbekannt.

## Empfangene Reporttypen

| Prüfung | Ergebnis |
| --- | --- |
| spontane Reports auf Interface 0 | keine in 120 Sekunden |
| spontane Reports auf Interface 1 | keine in 60 Sekunden |
| 440-Byte-Reports | keine |
| Header/Befehl `0x87` | nicht beobachtet |
| Header/Befehl `0x08` | nicht beobachtet |
| andere bekannte oder unbekannte Header | nicht beobachtet |
| mehrere Reporttypen auf Interface 0 | nicht beobachtet |

Der negative Befund belegt nicht, dass die Endpunkte niemals spontan senden.
Er gilt nur für das beobachtete Gerät, den normalen verbundenen Zustand und
die genannten Zeitfenster.

## Bedeutung für den früheren `0x87`-Test

Die Linux-hidraw-Queue eines neu geöffneten Dateideskriptors beginnt leer.
Ein Report, den der Host bereits **vor** `open()` empfangen hatte, konnte daher
nicht aus einem alten per-Open-Queuebestand stammen. Offen blieb bisher, ob
das Gerät nach `open()` von selbst oder aufgrund eines noch ausstehenden
Zustands einen Report liefern könnte.

Die neue Beobachtung schwächt genau diese zweite Erklärung:

- In 120 Sekunden mit offenem Interface 0 kam kein unabhängiger Report.
- Auch die bloße Anwesenheit des laufenden OpenRGB-Prozesses führte zu keinem
  sichtbaren Report auf den LCD-HID-Interfaces.
- Ein regelmäßig oder häufig spontan erzeugter Interface-0-Report ist im
  beobachteten Zustand daher nicht zu erwarten.

Nicht widerlegt sind:

- seltene Reports mit einem Intervall über 120 Sekunden,
- Reports nach Schlaf-/Aufwach-, Reconnect-, Display- oder anderen
  Zustandswechseln,
- ein firmwareseitig ausstehender Report, der zufällig erst nach `open()`
  fertiggestellt wird,
- ein Report im kurzen Zeitfenster zwischen einer Queueprüfung und einem
  späteren Write,
- eine Reaktion auf eine aktive OpenRGB-Änderung.

Der negative Befund erhöht damit relativ die Plausibilität, dass die
abweichende 440-Byte-Antwort tatsächlich kausal auf den einmaligen `0x87`-
Request folgte und nur wegen eines anderen Firmwarestands von der
v51-Erwartung abwich. Er kann diese Erklärung ohne die verlorenen
Antwortbytes nicht bestätigen.

## Bewertung eines Pre-Write-Queue-Checks

Ein Pre-Write-Queue-Check ist für jede spätere Testspezifikation **sinnvoll**:

1. Interface 0 lesend/nonblocking öffnen und zunächst eine definierte
   Ruhephase beobachten.
2. Bei jedem eingehenden Report Zeitstempel, Länge und vollständige Bytes
   sichern, ohne zu schreiben, und den Test abbrechen.
3. Unmittelbar vor einem später autorisierten Write erneut mit
   `select()`/`poll()` prüfen und bei Lesebereitschaft abbrechen.
4. Nach genau einem Write alle bis zur Deadline eintreffenden Reports mit
   Reihenfolge und Zeitstempeln erfassen; nichts erneut senden.
5. Nur einen vollständig passenden `0x87`-Header und eine strukturell passende
   Ein-Paket-Antwort als Kandidaten behandeln. Abweichende Reports bleiben
   getrennt dokumentiert.

Der Check ist **nicht ausreichend**, um Kausalität zu garantieren. Zwischen
letzter Prüfung und Write besteht ein unvermeidbares Race-Fenster, und ein
unabhängiger Report kann auch danach eintreffen. Er macht einen späteren Test
aber sicherer und aussagekräftiger, weil ein bereits nach `open()` wartender
Report vor dem Write erkannt würde und weil keine Antwortbytes mehr verloren
gingen.

Diese Beschreibung ist keine Freigabe für einen zweiten Test. Ein weiterer
HID-Write bleibt untersagt, bis er gesondert autorisiert und neu bewertet ist.

## Offene passive Folgefragen

- Treten Reports bei längerer Beobachtung über Minuten oder Stunden auf?
- Verändert ein normaler Suspend/Resume- oder Reconnect-Zyklus den
  spontanen Reportstrom?
- Gibt es bei einer anderweitig erlaubten, vom Bediener ausgelösten
  OpenRGB-Änderung gleichzeitig Aktivität auf Interface 0 oder 1?
- Sendet das Gerät unmittelbar nach dem Start einer reinen InfoHub-Sitzung
  Statusreports, auch ohne LCD-Änderung?

Solche Zustandsvarianten dürfen nur beobachtet werden, wenn die auslösende
Aktion selbst separat zulässig ist. Für diese Untersuchung wurden keine
weiteren Zustände erzeugt.
