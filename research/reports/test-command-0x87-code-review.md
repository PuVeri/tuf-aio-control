# Code-Review des Einmaltests für Befehl `0x87`

Stand: 2026-09-01

## Auftrag und Umfang

Geprüft wurden `src/test_command_0x87.py` und die von ihm verwendete dynamische
Geräteerkennung in `src/discover_device.py`. Das Review war zunächst rein
statisch. Anschließend wurden ausschließlich eine Syntaxprüfung, `--help` und
`--dry-run` ausgeführt. Der echte Pfad mit `--i-understand-the-risk` wurde nicht
aufgerufen. Kein hidraw-Knoten wurde geöffnet und es wurden keine Daten an das
Gerät gesendet.

## Review-Ergebnis

Der Kontrollfluss wurde um zwei Pre-Write-Abbruchschranken ergänzt. Im
statischen Review wurde danach **kein Pfad gefunden, auf dem ein vor dem Write
gelesener Report den einzigen `os.write()`-Aufruf noch erreichen kann**.

Der Code ist aus statischer Code-Review-Sicht für eine erneute menschliche
Sicherheitsbewertung vorbereitet. Das ist keine Freigabe zur Ausführung und
kein Nachweis, dass Firmware oder Hardware in jedem Laufzeitzustand ohne
unerwartete Nebenwirkung reagieren.

## Prüfmatrix

| Anforderung | Ergebnis | Statische Evidenz |
| --- | --- | --- |
| VID `0b05`, PID `1c7b`, Interface 0 dynamisch auswählen | erfüllt | Feste Zielwerte in Zeilen 16–18; `discover()` filtert sysfs-Eltern nach VID/PID; `_select_target()` akzeptiert genau einen Treffer mit Interface 0. |
| Keine feste `/dev/hidrawX`-Nummer | erfüllt | `discover_device.py` bildet den aktuellen sysfs-Namen dynamisch auf `/dev/<hidraw-Name>` ab; der Test enthält keine hidraw-Nummer. |
| Ziel vor dem Senden erneut prüfen | erfüllt | `_validate_open_target()` vergleicht Zeichengerät, Major/Minor, sysfs-Pfad, VID/PID-Filter, Interface und Reportstruktur nach dem Öffnen. |
| Lese- und Schreibmodus | erfüllt | Einziger `os.open()`-Aufruf mit `O_RDWR | O_NONBLOCK`, ergänzt um `O_CLOEXEC` und `O_NOFOLLOW`. |
| Genau 441 Byte schreiben | erfüllt | `HIDRAW_REQUEST` besteht aus einem API-Byte und 440 Reportbytes; Länge wird als Invariante auf 441 geprüft. Es gibt genau eine `os.write()`-Quelltextstelle. |
| Byte 0 ist `00` | erfüllt | `HIDRAW_REQUEST = b"\x00" + WIRE_REQUEST`; vollständiger Vergleich gegen die feste Bytefolge vor jedem Lauf. |
| Nutzreport beginnt mit `87 01 00 80` | erfüllt | `WIRE_REQUEST` wird fest aus `0x87, 0x01, 0x00, 0x80` aufgebaut und gegen ein unabhängiges Byte-Literal geprüft. |
| Danach 436 Nullbytes | erfüllt | Ausschließlich `bytes(436)` wird angehängt; die Gesamtfolge wird bytegenau validiert. |
| Keine Schreibwiederholung oder Retry | erfüllt | Genau eine statische `os.write()`-Stelle; kein Write in einer Schleife und kein zweiter Schreibpfad. Partieller Write beendet den Lauf. |
| Feste rein lesende Ruhephase | erfüllt | `_read_report_if_ready(fd, 5.0)` verwendet ausschließlich `select()` und gegebenenfalls `os.read()`; die Dauer wird als Sicherheitsinvariante auf fünf Sekunden geprüft. |
| Unmittelbare Queueprüfung | erfüllt | Direkt vor `os.write()` folgt `_read_report_if_ready(fd, 0.0)`; dazwischen liegt keine andere Operation. |
| Report vor Write verhindert Write | erfüllt | Beide Nicht-`None`-Zweige werfen `PreWriteReportError`; Stack-Unwinding führt zuerst durch den `finally`-Close, danach gibt `main()` den vollständigen Hexdump aus und beendet sich mit Exit-Code 7. |
| Maximal drei Sekunden Antwortwartezeit | erfüllt als programmierte Deadline | Nach dem Write wird einmalig `monotonic() + 3.0` berechnet; `select()` erhält höchstens die verbleibende Zeit und wird nicht wiederholt. |
| Genau eine Antwort nach dem Write lesen | erfüllt | Nach dem Write existiert genau ein `os.read(fd, 440)`; die zusätzlichen Reads liegen ausschließlich davor und führen bei Daten zum Abbruch. Kürzere oder leere Ergebnisse werden abgewiesen. |
| Antwortstruktur prüfen | erfüllt | `_response_version_value()` verlangt exakt 440 Byte, Header `87 01 00 80` und 434 Nullbytes ab Offset 6; Offset 4/5 wird als Little-Endian-16-Bit-Versionswert akzeptiert. |
| Bei Fehlern sofort schließen | erfüllt | Alle Pfade nach erfolgreichem `os.open()` liegen in einem `try/finally`; partieller Write, Timeout, Disconnect, falsche Länge und Inhaltsabweichung kehren durch diesen Close-Pfad zurück. |
| Kein Nachsenden und keine automatische Recovery | erfüllt | Nach dem einzigen Write existiert kein weiterer Schreibaufruf. Fehlerpfade schließen nur den Dateideskriptor und senden kein Recovery-Kommando. |
| `--dry-run` öffnet das Gerät nicht | erfüllt | Der Dry-Run kehrt in `main()` vor dem einzigen Aufruf von `_run_once()` und damit vor `os.open()` zurück. |
| Ohne Risikoflag nichts senden | erfüllt | Ohne `--i-understand-the-risk` kehrt `main()` vor `_run_once()` zurück. Die vorherige Erkennung liest nur sysfs/udev-Metadaten. |
| Keine anderen oder frei wählbaren Pakete | erfüllt | Keine Opcode-/Payload-CLI-Option. `COMMAND` und Request sind fest; die Antwortstruktur ist fest, nur das empirisch versionsabhängige Halbwort an Offset 4/5 ist variabel. Die explizit verbotenen Opcodes sind zusätzlich aufgeführt. |
| Keine Rechteänderung oder Paketinstallation | erfüllt | Keine entsprechenden Systemaufrufe oder Kommandos. Bei fehlendem R/W-Zugriff erfolgt Exit-Code 2. |
| Keine dauerhafte Rohdatenspeicherung | erfüllt | Kein Datei-, Capture- oder Logging-Schreibpfad; Antworten existieren nur im Arbeitsspeicher. |

## Exakte statische Sicherheitsgarantien

Unter der Voraussetzung, dass exakt der geprüfte Quellstand ausgeführt wird,
garantiert der Kontrollfluss:

1. Vor dem Risikoflag beziehungsweise im Dry-Run wird der einzige echte
   I/O-Pfad nicht erreicht.
2. Nach `open()` und Zielvalidierung führt der Code fünf Sekunden lang nur
   `select()` und gegebenenfalls `os.read()` aus und prüft die Queue direkt vor
   dem Write ein zweites Mal ohne Wartezeit.
3. Jeder bei einer der beiden Prüfungen gelesene Report erzeugt eine Ausnahme,
   schließt den Deskriptor im `finally`-Block und beendet den Lauf, ohne die
   spätere `os.write()`-Stelle zu erreichen.
4. Der einzige Geräte-Write erhält unveränderlich 441 Byte:
   `00 | 87 01 00 80 | 436 × 00`.
5. Es gibt pro Prozesslauf höchstens einen Aufruf von `os.write()` und danach
   keinen weiteren Schreib- oder Recoverypfad.
6. Nach erfolgreichem Write gibt es höchstens einen `select()`- und einen
   `os.read()`-Aufruf. Die an `select()` übergebene Wartezeit ist nie größer als
   die verbleibende Drei-Sekunden-Deadline.
7. Nur `87 01 00 80 VV VV | 434 × 00` mit exakt 440 Byte gilt als struktureller
   Erfolg; `VV VV` wird ausschließlich als Versionswert gelesen und verändert
   keinen Kontroll- oder Schreibpfad.
8. Pre-Write-Reports und unerwartete Post-Write-Antworten werden erst nach dem
   Close vollständig im Terminal ausgegeben; letztere zusätzlich als
   Byte-Diff.
9. Nach jedem Rückgabepfad hinter einem erfolgreichen `os.open()` wird
   `os.close()` im `finally`-Block aufgerufen.
10. Der Code verändert weder Zugriffsrechte noch Systemkonfiguration und legt
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
- Die Queueprüfungen schließen das Race-Fenster zwischen der letzten
  Nullzeitprüfung und `os.write()` nicht. Ein unabhängiger Report kann auch
  erst nach dem Write eintreffen und bleibt dann kausal mehrdeutig.
- Bei einem Pre-Write-Report liest und dokumentiert der Code genau den ersten
  Report und bricht ab; weitere möglicherweise eingereihte Reports werden
  nicht geleert.
- Ein seltener Fehler von `os.close()` wird gemeldet und nicht durch einen
  unsicheren Close-Retry kaschiert. Der Prozess sendet danach nichts mehr.
- Der Transaktionspfad wurde in Live-Test 02 einmal gesondert autorisiert
  durchlaufen und lieferte `0x0049`. Die nachträglich angepasste strukturelle
  Antwortklassifizierung wird in dieser Arbeit nur offline geprüft; es erfolgt
  kein weiterer HID-Test.

## Freigabebewertung

**Aus Codesicht bereit für eine erneute menschliche Sicherheitsbewertung, aber
nicht zur Ausführung freigegeben.** Vor einem echten Lauf müssten die
gesonderte menschliche Autorisierung, Firmware-/Betriebszustand, vorhandener
Lese-/Schreibzugriff und die in `docs/COMMAND_0X87_TEST.md` beschriebenen
manuellen Recoverybedingungen bewusst bestätigt werden.

## Offline-Prüfung am 2026-09-01

Nach der Härtung wurden ausschließlich folgende nicht sendenden Prüfungen
ausgeführt:

| Prüfung | Ergebnis |
| --- | --- |
| Syntax über Python-`compile()` mit `-B` | Exit-Code 0; keine Bytecode-Datei |
| `python3 -B src/test_command_0x87.py --help` | Exit-Code 0; kein Gerätezugriff |
| `python3 -B src/test_command_0x87.py --dry-run` | Exit-Code 0; Ziel und neue Ruhephase angezeigt, hidraw nicht geöffnet |
| statische Suche nach `os.write(` | genau eine Fundstelle in `_run_once()` |
| reine Funktionsprüfung `_response_version_value()` | `0x0051` und `0x0049` akzeptiert; falsche Länge, Header und Padding abgewiesen |

Der Pfad mit `--i-understand-the-risk` wurde nicht aufgerufen. Es wurden keine
Zugriffsrechte verändert und keine Daten an die AIO gesendet.

Nach der späteren Antwortklassifizierungsänderung wurden Syntax, `--help` und
die reine Funktionsprüfung erneut mit Exit-Code 0 ausgeführt. Auf einen
erneuten `--dry-run` wurde dabei verzichtet, damit in diesem
Dokumentationsschritt auch die dynamische Geräteerkennung unterblieb.

## Codeänderungen

- feste fünfsekündige Pre-Write-Ruhephase,
- unmittelbare zweite Queueprüfung mit Timeout null,
- eigener Exit-Code 7 und vollständiger Hexdump bei Pre-Write-Report,
- gemeinsamer vollständiger Hexdumphelfer,
- vollständiger Hexdump plus Byte-Diff bei strukturell ungültiger Antwort,
- strukturelle Akzeptanz eines beliebigen 16-Bit-Versionswerts an Offset 4/5;
  v51 bleibt Referenz `0x0051`, Live-Test 02 bestätigt `0x0049`.
