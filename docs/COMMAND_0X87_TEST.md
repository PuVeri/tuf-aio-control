# Einmaltest für Befehl `0x87`

## Zweck und Sicherheitsstatus

`src/test_command_0x87.py` implementiert ausschließlich eine einzelne,
transporttechnisch festgelegte Anfrage für Befehl `0x87`. Der Befehl ist für
Firmware 51 statisch als **wahrscheinlich rein lesend**, nicht als nachweislich
rein lesend eingestuft. Der gemeinsame Firmwareprolog kann abhängig vom
Gerätezustand flüchtige RAM- und Peripherieregister verändern.

Das Programm implementiert keine anderen Befehle. Insbesondere sind `0x08`,
`0x02`, `0x09`, `0x1f`, `0x45`, `0x86`, `0x88` und `0xff` nicht auswählbar und
werden durch eine interne Sicherheitsinvariante ausgeschlossen. Es gibt keine
automatische Wiederholung und keine automatische Recovery.

Die Erstellung und Offline-Prüfung des Programms ist keine Freigabe für einen
realen HID-Test. Dieser benötigt weiterhin einen gesonderten, ausdrücklich
freigegebenen Auftrag.

## Risiko

Das verbleibende Risiko eines exakt gerahmten Einzeltests unter der analysierten
Firmware 51 ist sehr gering, aber nicht null:

- Der gemeinsame Dispatcherprolog kann flüchtigen Peripheriezustand verändern.
- Eine volle Antwortqueue oder ein dauerhaft beschäftigter USB-Controller kann
  zu Timeout oder einem vorübergehenden Transportstillstand führen.
- Andere Firmwareversionen, Boot-/Updatemodi, Firmwarefehler oder ein falsch
  ausgewähltes Interface fallen nicht unter die statische Bewertung.
- Das Programm kann persistente Schäden nicht formal ausschließen. Es sendet
  deshalb nur das unveränderliche `0x87`-Paket und bricht bei jeder Abweichung
  ohne Folgekommando ab.

## Exaktes Paket

Das Linux-`hidraw.write()` erhält genau 441 Byte:

```text
Offset 0:       00
Offset 1..4:    87 01 00 80
Offset 5..440:  436-mal 00
```

Byte 0 ist das Host-API-Reportnummernfeld für einen unnummerierten HID-Report.
Der Linux-USB-HID-Treiber entfernt dieses Byte. Auf Endpoint `0x01` OUT werden
somit genau 440 Byte übertragen:

```text
87 01 00 80 | 436-mal 00
```

Es gibt genau einen Aufruf von `os.write()`. Ein partieller Write wird nicht
ergänzt oder wiederholt.

## Erwartete Antwort

Innerhalb von maximal drei Sekunden wird genau ein Report gelesen. Erfolg
erfordert die bytegenaue 440-Byte-Antwort:

```text
87 01 00 80 51 00 | 434-mal 00
```

Eine falsche Länge gilt ebenso wie ein abweichendes Byte als unerwartete
Antwort. Bei einer künftigen unerwarteten, nicht leeren Antwort schließt das
Programm zuerst den Gerätedeskriptor. Danach gibt es die vollständig empfangene
Antwort als Hexdump und jede abweichende Byteposition mit erwartetem und
tatsächlichem Wert im Terminal aus. Diese Diagnose löst keinen weiteren Write
aus.

Empfangene Rohdaten werden weiterhin nicht dauerhaft gespeichert. Das Programm
bietet bewusst keinen Capture-Parameter; Hexdump und Differenzliste erscheinen
nur im Terminal.

## Ergebnis des realen Einmaltests 01

Am 2026-08-05 wurde der gesondert freigegebene Test genau einmal ausgeführt.
Interface 0 wurde dynamisch als `/dev/hidraw7` erkannt, der feste 441-Byte-
Request wurde einmal gesendet und eine 440-Byte-Antwort empfangen. Die Antwort
wich von der erwarteten Gesamtfolge ab. Das Programm schloss sofort und sendete
nichts nach.

Die damalige Programmversion speicherte oder druckte die tatsächlichen
Antwortbytes nicht vollständig. Sie sind daher unbekannt und werden nicht
rekonstruiert. Der vollständige Ergebnis- und Rückbaubericht steht unter
`research/reports/command-0x87-live-test-01.md`.

Dieser Test darf nicht allein zur nachträglichen Gewinnung der fehlenden Bytes
wiederholt werden. Jeder weitere reale Write wäre ein neuer, gesondert zu
begründender und ausdrücklich zu autorisierender Test.

## Voraussetzungen

- Ausführung aus dem Repository-Root mit Python 3.
- Zielgerät ASUS TUF Gaming LC III 360 ARGB LCD mit USB-ID `0b05:1c7b`.
- Genau ein dynamisch ermitteltes Interface 0.
- Interface 0 muss laut Reportdeskriptor 440 Byte Input, 440 Byte Output und
  keine Report-IDs besitzen.
- Der Benutzer muss bereits Lese- und Schreibzugriff auf den ermittelten
  hidraw-Knoten besitzen. Das Programm verwendet kein `sudo`, verändert keine
  Gruppen, ACLs, udev-Regeln oder Modusbits und installiert keine Pakete.
- Für einen echten Test muss eine gesonderte menschliche Freigabe vorliegen.

Die vorhandene Projekt-udev-Regel gewährt der Gruppe `input` absichtlich nur
Leserechte. Das Testprogramm erweitert diese Rechte nicht und beendet sich bei
fehlender Schreibberechtigung mit Exit-Code 2.

## Dry-Run

```text
python3 -B src/test_command_0x87.py --dry-run
```

Der Dry-Run sucht das Gerät rein lesend über sysfs/udev, verlangt VID, PID,
Interface und die bekannten Reportgrößen und zeigt Ziel sowie Paketstruktur.
Er öffnet den hidraw-Knoten nicht und sendet nichts.

Auch ein Aufruf ohne Argument zeigt nur die geplante Aktion und beendet sich,
ohne das HID-Gerät zu öffnen:

```text
python3 -B src/test_command_0x87.py
```

## Echter Aufruf

Der dokumentierte Einmaltest wurde bereits durchgeführt. Der folgende Aufruf ist
nur Referenz und darf nicht ohne eine neue, gesonderte ausdrückliche Freigabe
erneut verwendet werden:

```text
python3 -B src/test_command_0x87.py --i-understand-the-risk
```

Das Argument ist die bewusste Bestätigung für genau diesen einen Lauf. Vor dem
Write prüft das Programm nach dem Öffnen erneut den Zeichengeräteknoten, seine
sysfs-Gerätenummer, VID/PID, Interface, Reportgrößen und fehlende Report-IDs.

## Abbruchbedingungen

Das Programm schließt den Deskriptor sofort und sendet nichts nach bei:

- fehlender oder mehrdeutiger Geräte-/Interfacezuordnung,
- veränderter HID-Reportstruktur oder Gerätenummer,
- fehlender Lese- oder Schreibberechtigung,
- Fehler beim Öffnen, Schreiben, Warten oder Lesen,
- partiellem Write,
- Disconnect oder Ausnahmezustand,
- Timeout nach maximal drei Sekunden,
- Antwortlänge ungleich 440 Byte,
- jeder inhaltlichen Abweichung von der erwarteten Antwort.

Exit-Codes:

| Code | Bedeutung |
| ---: | --- |
| `0` | erwartete Antwort empfangen oder sicherer Vorschau-/Dry-Run beendet |
| `1` | Zielgerät oder Interface nicht eindeutig auswählbar |
| `2` | Berechtigungsfehler |
| `3` | Timeout |
| `4` | unerwartete Antwort oder falsche Antwortlänge |
| `5` | I/O-, Disconnect- oder sonstiger Laufzeitfehler |
| `6` | interne Sicherheitsinvariante oder erneute Zielprüfung fehlgeschlagen |

## Recoverymaßnahmen

Das Programm führt keine Recovery automatisch aus. Nach einem Fehlschlag gilt:

1. Keine weiteren Protokollbefehle senden.
2. Prüfen, ob das Gerät ohne Eingriff normal weiterarbeitet.
3. Nur bei anhaltender Störung die USB-Verbindung kontrolliert neu herstellen.
4. Nur wenn das nicht genügt, die AIO kontrolliert aus- und wieder einschalten.

Kein Reset-, Boot-, Konfigurations-, Feature-Report- oder USB-Control-Transfer
darf als automatische oder improvisierte Recovery gesendet werden.
