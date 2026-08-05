# Code-Review des Einmaltests für Befehl `0x87`

Stand: 2026-08-05

## Auftrag und Umfang

Geprüft wurden `src/test_command_0x87.py` und die von ihm verwendete dynamische
Geräteerkennung in `src/discover_device.py`. Das Review war zunächst rein
statisch. Anschließend wurden ausschließlich eine Syntaxprüfung, `--help` und
`--dry-run` ausgeführt. Der echte Pfad mit `--i-understand-the-risk` wurde nicht
aufgerufen. Kein hidraw-Knoten wurde geöffnet und es wurden keine Daten an das
Gerät gesendet.

## Review-Ergebnis

Im geprüften Programm wurde **kein konkreter Sicherheitsfehler gefunden**. Der
Programmcode wurde deshalb im Rahmen dieses Reviews nicht geändert.

Der Code ist aus statischer Code-Review-Sicht für einen einzelnen, manuell und
gesondert autorisierten `0x87`-Test freigabefähig. Diese Aussage ist keine
Freigabe zur Ausführung und kein Nachweis, dass Firmware oder Hardware in jedem
Laufzeitzustand ohne unerwartete Nebenwirkung reagieren.

## Prüfmatrix

| Anforderung | Ergebnis | Statische Evidenz |
| --- | --- | --- |
| VID `0b05`, PID `1c7b`, Interface 0 dynamisch auswählen | erfüllt | Feste Zielwerte in Zeilen 16–18; `discover()` filtert sysfs-Eltern nach VID/PID; `_select_target()` akzeptiert genau einen Treffer mit Interface 0. |
| Keine feste `/dev/hidrawX`-Nummer | erfüllt | `discover_device.py` bildet den aktuellen sysfs-Namen dynamisch auf `/dev/<hidraw-Name>` ab; der Test enthält keine hidraw-Nummer. |
| Ziel vor dem Senden erneut prüfen | erfüllt | `_validate_open_target()` vergleicht Zeichengerät, Major/Minor, sysfs-Pfad, VID/PID-Filter, Interface und Reportstruktur nach dem Öffnen. |
| Lese- und Schreibmodus | erfüllt | Einziger `os.open()`-Aufruf mit `O_RDWR | O_NONBLOCK`, ergänzt um `O_CLOEXEC` und `O_NOFOLLOW`. |
| Genau 441 Byte schreiben | erfüllt | `HIDRAW_REQUEST` besteht aus einem API-Byte und 440 Reportbytes; Länge wird als Invariante auf 441 geprüft. Einziger `os.write()`-Aufruf in Zeile 167. |
| Byte 0 ist `00` | erfüllt | `HIDRAW_REQUEST = b"\x00" + WIRE_REQUEST`; vollständiger Vergleich gegen die feste Bytefolge vor jedem Lauf. |
| Nutzreport beginnt mit `87 01 00 80` | erfüllt | `WIRE_REQUEST` wird fest aus `0x87, 0x01, 0x00, 0x80` aufgebaut und gegen ein unabhängiges Byte-Literal geprüft. |
| Danach 436 Nullbytes | erfüllt | Ausschließlich `bytes(436)` wird angehängt; die Gesamtfolge wird bytegenau validiert. |
| Keine Schreibwiederholung oder Retry | erfüllt | Genau eine statische `os.write()`-Stelle; kein Write in einer Schleife und kein zweiter Schreibpfad. Partieller Write beendet den Lauf. |
| Maximal drei Sekunden Antwortwartezeit | erfüllt als programmierte Deadline | Nach dem Write wird einmalig `monotonic() + 3.0` berechnet; `select()` erhält höchstens die verbleibende Zeit und wird nicht wiederholt. |
| Genau eine 440-Byte-Antwort lesen | erfüllt | Genau ein `os.read(fd, 440)`; es existiert keine Leseschleife. Kürzere oder leere Ergebnisse werden abgewiesen. |
| Antwort bytegenau prüfen | erfüllt | Vergleich gegen `87 01 00 80 51 00` plus exakt 434 Nullbytes, insgesamt 440 Byte. |
| Bei Fehlern sofort schließen | erfüllt | Alle Pfade nach erfolgreichem `os.open()` liegen in einem `try/finally`; partieller Write, Timeout, Disconnect, falsche Länge und Inhaltsabweichung kehren durch diesen Close-Pfad zurück. |
| Kein Nachsenden und keine automatische Recovery | erfüllt | Nach dem einzigen Write existiert kein weiterer Schreibaufruf. Fehlerpfade schließen nur den Dateideskriptor und senden kein Recovery-Kommando. |
| `--dry-run` öffnet das Gerät nicht | erfüllt | Der Dry-Run kehrt in `main()` vor dem einzigen Aufruf von `_run_once()` und damit vor `os.open()` zurück. |
| Ohne Risikoflag nichts senden | erfüllt | Ohne `--i-understand-the-risk` kehrt `main()` vor `_run_once()` zurück. Die vorherige Erkennung liest nur sysfs/udev-Metadaten. |
| Keine anderen oder frei wählbaren Pakete | erfüllt | Keine Opcode-/Payload-CLI-Option. `COMMAND` muss `0x87` sein; die vollständigen Anfrage- und Antwortbytes sind feste Invarianten. Die explizit verbotenen Opcodes sind zusätzlich aufgeführt. |
| Keine Rechteänderung oder Paketinstallation | erfüllt | Keine entsprechenden Systemaufrufe oder Kommandos. Bei fehlendem R/W-Zugriff erfolgt Exit-Code 2. |
| Keine dauerhafte Rohdatenspeicherung | erfüllt | Kein Datei-, Capture- oder Logging-Schreibpfad; Antworten existieren nur im Arbeitsspeicher. |

## Exakte statische Sicherheitsgarantien

Unter der Voraussetzung, dass exakt der geprüfte Quellstand ausgeführt wird,
garantiert der Kontrollfluss:

1. Vor dem Risikoflag beziehungsweise im Dry-Run wird der einzige echte
   I/O-Pfad nicht erreicht.
2. Der einzige Geräte-Write erhält unveränderlich 441 Byte:
   `00 | 87 01 00 80 | 436 × 00`.
3. Es gibt pro Prozesslauf höchstens einen Aufruf von `os.write()` und danach
   keinen weiteren Schreib- oder Recoverypfad.
4. Nach erfolgreichem Write gibt es höchstens einen `select()`- und einen
   `os.read()`-Aufruf. Die an `select()` übergebene Wartezeit ist nie größer als
   die verbleibende Drei-Sekunden-Deadline.
5. Nur `87 01 00 80 51 00 | 434 × 00` mit exakt 440 Byte gilt als Erfolg.
6. Nach jedem Rückgabepfad hinter einem erfolgreichen `os.open()` wird
   `os.close()` im `finally`-Block aufgerufen.
7. Der Code verändert weder Zugriffsrechte noch Systemkonfiguration und legt
   keine Rohdaten- oder Capture-Datei an.

Diese Garantien beziehen sich auf den Python-Kontrollfluss. Ein erfolgreicher
Write-Rückgabewert beweist nur die Annahme des Reports durch die Hostschnittstelle,
nicht seine schadensfreie Verarbeitung durch die Firmware.

## Verbleibende Risiken und Grenzen

- Der `0x87`-Handler ist statisch nur als wahrscheinlich rein lesend bewertet.
  Sein gemeinsamer Prolog kann flüchtige RAM- und Peripheriezustände verändern.
- Die Bewertung gilt für die untersuchte Firmware 51 und den normalen
  Betriebsmodus. Das Programm kann Firmwareversion oder Betriebsmodus vor dem
  Write nicht sicher verifizieren.
- Ein partieller Write oder ein I/O-Fehler kann auftreten, nachdem der Kernel
  bereits Daten angenommen hat. Der Code sendet dann nichts nach, kann die
  Gerätewirkung aber nicht rückgängig machen.
- `select()` verwendet eine maximale programmierte Wartezeit von drei Sekunden;
  Linux ist jedoch kein Echtzeitsystem, sodass Prozessplanung die beobachtete
  Wandzeit geringfügig verlängern kann.
- Eine bereits vor dem Write eingereihte Antwort würde gelesen und bei
  Abweichung verworfen; der Code leert keine Queue, weil dies weitere Reads und
  zusätzliche Protokollannahmen erfordern würde.
- Ein seltener Fehler von `os.close()` wird gemeldet und nicht durch einen
  unsicheren Close-Retry kaschiert. Der Prozess sendet danach nichts mehr.
- Der echte I/O-Pfad wurde entsprechend dem Auftrag nicht praktisch getestet.
  Hardware-, Treiber- und Firmwareverhalten bleiben daher unvalidiert.

## Freigabebewertung

**Aus Codesicht freigabefähig für genau einen manuellen Test, aber nicht durch
dieses Review zur Ausführung freigegeben.** Vor einem echten Lauf müssen die
gesonderte menschliche Autorisierung, Firmware-/Betriebszustand, vorhandener
Lese-/Schreibzugriff und die in `docs/COMMAND_0X87_TEST.md` beschriebenen
manuellen Recoverybedingungen bewusst bestätigt werden.

## Codeänderungen

Keine. Im Programmcode wurde kein konkreter Sicherheitsfehler gefunden.
