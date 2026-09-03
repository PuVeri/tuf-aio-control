# Erster begrenzter LCD-Refresh-Test

## Status und Umfang

`src/test_lcd_refresh.py` ist ausschließlich für den bereits statisch
freigegebenen ersten Fünfframe-Test vorgesehen. Die Implementierung und ihre
Tests entstanden ohne Gerätekommunikation, hidraw-Open oder HID-Write. Ein
realer Refresh-Lauf ist weiterhin nur als gesondert autorisierter Schritt
zulässig.

Der Einstieg unterstützt keine freie Bilddatei, kein frei wählbares Intervall,
keine freie Framezahl und keine frei wählbare Laufzeit. Er kann weder GIF noch
Interface 0, IN-Reads, andere Opcodes, Retry oder Recovery auslösen.

## Aufrufe

Standardmäßig wird nur eine Preview erzeugt:

```bash
python3 -B src/test_lcd_refresh.py
```

Der ausdrückliche Dry-Run ist funktional identisch:

```bash
python3 -B src/test_lcd_refresh.py --dry-run
```

Beide Varianten validieren die lokale Referenz und dürfen rein lesende sysfs-
und `/proc`-Prüfungen ausführen. Sie öffnen keinen hidraw-Knoten und senden
nichts.

Nur nach gesonderter Autorisierung ist der Livepfad syntaktisch erreichbar:

```bash
python3 -B src/test_lcd_refresh.py --i-understand-the-risk
```

Der Schalter ist nicht abkürzbar. Er darf nicht mit `--dry-run` kombiniert
werden. Es gibt keine weiteren Laufzeitparameter.

## Festes Profil

| Grenze | Fester Wert |
| --- | ---: |
| Datei | `tests/fixtures/lcd-0x08-reference.jpg` |
| SHA-256 | `5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866` |
| JPEG-Länge | 2236 Byte |
| Segmente pro Frame | exakt 3 |
| Frames | exakt 5, sofern kein früher Fehler eintritt |
| maximale Writes | 15 |
| hidraw-Puffer je Write | exakt 1025 Byte |
| Abstand der Frame-Startzeitpunkte | 1,0 s |
| maximale Sessiondauer | 6,0 s |

Die Startzeit des nächsten Frames basiert auf dem tatsächlichen Start des
vorherigen. Dauert ein Transfer länger als eine Sekunde, beginnt der nächste
erst nach dessen Rückkehr. Es gibt weder Überlappung noch Nachholburst.

## Preflight und Revalidierung

Vor dem Sessionstart werden vollständig geprüft:

- genau ein dynamisch gefundenes `0b05:1c7b`, ausschließlich Interface 1;
- Hersteller `ASUS Tek`, falls aus sysfs verfügbar, und Produkt
  `TUF GAMING LC III 360 ARGB LCD`, falls verfügbar;
- `bcdDevice` numerisch exakt `0x0049`; sowohl der sysfs-Rohtext `0049` als
  auch die menschenlesbare Darstellung `0.49` werden darauf normalisiert;
- HID Usage Page `0xff06`, Usage `0x01`, keine Report-ID, 16 Byte IN und
  1024 Byte OUT;
- USB-Interface `bAlternateSetting=0`, Klasse/Subklasse/Protokoll `03/00/00`
  und zwei Interruptendpoints: `0x03` OUT mit 1024 Byte sowie `0x84` IN mit
  16 Byte; das von sysfs formatierte Intervall muss vorhanden und positiv
  sein;
- exakter Referenzhash, konservativer JPEG-Vertrag und `N=3`;
- fünf vollständige, jeweils lokal validierte Dreireportfolgen im RAM;
- keine fremde schreibfähige FD auf genau demselben Character Device, soweit
  dies über das lokale `/proc` sichtbar ist.

Vor jedem der höchstens 15 Writes wird der aktuelle hidraw-Knoten erneut über
sysfs entdeckt und gegen Interface, Gerätenummer, Descriptor, USB-Metadaten
und Endpointprofil geprüft. Zusätzlich werden Referenzhash, JPEG, `N`, alle
fünf vorbereiteten Reportfolgen und die Konkurrenzprüfung wiederholt. Ein
fehlgeschlagenes Gate liegt vor der Write-Stelle und beendet die Session.

Die Konkurrenzprüfung vergleicht die konkrete Character-Device-Nummer. Das
getrennte OpenRGB-Gerät `0b05:19af` wird dadurch weder als Ziel gewählt noch
gestört. Fremde Prozesse werden niemals beendet. Für Prozesse, deren
FD-Verzeichnis dem aufrufenden Benutzer nicht zugänglich ist, ist die Prüfung
technisch nur best effort; außerdem bleibt zwischen Prüfung und Write ein
kleines unvermeidbares Race. Deshalb müssen konkurrierende LCD-Anwendungen
vorher zusätzlich organisatorisch ausgeschlossen werden.

## Schreibrechte

Das Programm verändert keine Rechte. Für einen später autorisierten Lauf darf
nur der dynamisch gefundene Interface-1-Knoten temporär schreibbar gemacht
werden. Ursprünglicher Mode beziehungsweise ACL muss vorher festgehalten und
unmittelbar nach dem Lauf auch bei einem Fehler wiederhergestellt werden. Eine
persistente udev-Regel, Gruppenänderung oder Schreibfreigabe ist für diesen
Test unzulässig.

## Laufzeit und Protokoll

Jeder Frame protokolliert:

- Index 1 bis 5;
- Startzeit relativ zum Senderstart;
- synchrone Transferdauer;
- vollständige Writeanzahl `3/3` oder den ersten Fehler;
- das Transportergebnis.

Beim ersten Fehler endet der Controller ohne Retry, Recovery, Folgeframe oder
Intervalländerung. `send_frame_once()` öffnet den dynamisch validierten Knoten
pro Frame mit `O_WRONLY | O_NONBLOCK` und schließt den Descriptor im `finally`.
Nach Frame 5 ist kein weiterer Senderaufruf möglich.

## Erfolgskriterien

**Transporterfolg** bedeutet ausschließlich:

```text
5 Frames / 15 vollständige Writes zu je 1025 Byte
```

Das Programm darf danach Transporterfolg melden. Es kennt keinen Decoder-Done-
oder Sichtbarkeitssensor.

**Sichtbarer Erfolg** muss der Benutzer selbst beobachten:

> Das eigene Referenzbild bleibt während der aktiven Refreshsession sichtbar,
> ohne dass das ASUS-Defaultbild dazwischen erscheint.

Das Programm behauptet diesen sichtbaren Erfolg ausdrücklich nicht. Ein
Defaultbild, Artefakte, Freeze oder Reenumeration während der aktiven Session
ist auch bei 15 vollständigen Hostwrites ein Fehlschlag.

## Offline-Test

```bash
python3 -B -m unittest discover -s tests -v
```

Der aktuelle Stand umfasst 109 erfolgreiche Offline-Tests. Sämtliche
Geräteoperationen des neuen Einstiegs sind dabei gemockt.
