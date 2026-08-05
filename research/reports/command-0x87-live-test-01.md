# Realer Einmaltest von Befehl `0x87` – Test 01

Datum: 2026-08-05  
Exakte Uhrzeit: nicht protokolliert

## Rahmenbedingungen

Dieser Bericht dokumentiert den ersten und einzigen realen `0x87`-Test anhand
des vom Bediener gemeldeten Ergebnisses. Der Test verwendete das abgesicherte
Programm `src/test_command_0x87.py` und die zuvor dokumentierte temporäre
Schreibfreigabe ausschließlich für ASUS `0b05:1c7b`, Interface 0.

Das Ziel wurde dynamisch als Interface 0 und zum Testzeitpunkt als
`/dev/hidraw7` erkannt. Die hidraw-Nummer ist nur Teil dieser Beobachtung und
keine dauerhafte Gerätekennung.

## Gesendetes Paket

Es wurde genau ein `hidraw.write()` mit exakt 441 Byte ausgeführt:

```text
Offset 0:       00
Offset 1..4:    87 01 00 80
Offset 5..440:  436-mal 00
```

Das erste Byte war das Linux-HID-API-Reportnummernfeld für den unnummerierten
Report. Der an das Gerät gerichtete 440-Byte-Nutzreport war damit:

```text
87 01 00 80 | 436-mal 00
```

Es gab keinen zweiten Write und keinen Retry.

## Tatsächlich beobachtetes Ergebnis

Innerhalb des vorgesehenen Antwortpfads wurde genau eine Antwort mit exakt
440 Byte empfangen. Ihr Inhalt wich von der erwarteten Bytefolge ab:

```text
87 01 00 80 51 00 | 434-mal 00
```

Die tatsächlichen 440 Antwortbytes wurden vom damaligen Programm weder als
vollständiger Hexdump ausgegeben noch dauerhaft gespeichert. Sie können deshalb
nicht nachträglich rekonstruiert, zitiert oder byteweise ausgewertet werden.
Dieser Bericht erfindet keine fehlenden Bytes. Belegt sind nur Antwortlänge und
die festgestellte Abweichung von der erwarteten Gesamtfolge.

Das Ergebnis widerlegt die statisch erwartete Bytefolge für diesen konkreten
Lauf als Laufzeitbeobachtung. Ohne die Antwortbytes ist nicht bestimmbar, ob
Header, Nutzwert, Nullbereich oder mehrere Bereiche abwichen. Ebenso lässt sich
aus diesem einzelnen Ergebnis keine neue Befehlssemantik ableiten.

## Abbruchverhalten

Das Programm behandelte die Antwort als unerwartet, schloss den
Gerätedeskriptor sofort und sendete nichts nach. Es gab:

- keinen zweiten `0x87`-Request,
- keinen anderen HID-Befehl,
- keinen Retry,
- keinen Reset-, Boot- oder Konfigurationsbefehl,
- keine automatische Recovery.

## Gerätezustand nach dem Test

Nach dem Abbruch wurde die AIO weiterhin normal erkannt. Im anschließend
geprüften Kernelprotokoll erschienen keine testbedingten USB-Fehler, Resets oder
Disconnects. Das ist eine positive unmittelbare Nachbeobachtung, aber kein
Beweis dafür, dass der Befehl in jedem Firmwarezustand ohne Nebenwirkung ist.

## Rückbau der temporären Schreibrechte

Die temporäre Schreibregel wurde nach dem Test entfernt. Die dauerhafte
Leseregel wurde erneut wirksam; anschließend besaßen beide Interfaces wieder
Modus `0640`. Interface 0 und Interface 1 waren damit für die Gruppe `input`
wieder ausschließlich lesbar.

Es bestehen aus diesem Test keine fortdauernden temporären Schreibrechte.

## Wiederholungsverbot

Der Test darf **nicht allein deshalb wiederholt werden**, um die beim ersten
Lauf nicht gespeicherten Antwortbytes nachträglich zu erhalten. Ein weiterer
realer HID-Write wäre ein neuer Test mit eigenem Risiko und benötigte eine neue,
gesonderte Begründung, Sicherheitsbewertung und ausdrückliche menschliche
Freigabe. Das vorliegende unerwartete Ergebnis ist keine automatische
Wiederholungsfreigabe.
