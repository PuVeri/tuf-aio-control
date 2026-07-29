# Rein lesender Linux-Prototyp

Stand: 2026-07-29.

Der Prototyp erkennt die ASUS TUF Gaming LC III 360 ARGB LCD dynamisch anhand
der USB-ID `0b05:1c7b`. Er sendet keine Output- oder Feature-Reports und führt
keine USB-Control-Transfers aus.

## Dateien

- `src/discover_device.py`: Erkennung über `/sys/class/hidraw`, USB-sysfs-
  Attribute und ergänzende `udevadm`-Eigenschaften.
- `src/read_input.py`: optionaler, zeitbegrenzter und ausschließlich lesender
  Beobachter für ein anhand seiner USB-Interface-Nummer ausgewähltes Interface.

Beide Programme verwenden nur die Python-Standardbibliothek.

## Geräteerkennung

```text
python3 src/discover_device.py
python3 src/discover_device.py --json
```

Die Erkennung:

1. läuft über alle Einträge unter `/sys/class/hidraw`,
2. folgt deren sysfs-Eltern bis zum USB-Gerät,
3. vergleicht dort `idVendor` und `idProduct`,
4. liest `bInterfaceNumber` am USB-Interface,
5. wertet den bereits vom Kernel bereitgestellten HID-Reportdeskriptor aus,
6. zeigt dynamischen Geräteknoten, sysfs-Pfad, Hersteller, Produkt,
   Seriennummer, Reportgrößen und aktuelle Leseberechtigung.

`udevadm info` wird ergänzend und mit kurzem Zeitlimit abgefragt. Die
Identifikation bleibt auch ohne `udevadm` über sysfs möglich:

```text
python3 src/discover_device.py --no-udev
```

Die berechneten Reportgrößen stammen aus Report Size und Report Count des
HID-Deskriptors. Falls Report-IDs deklariert sind, wird deren zusätzliches Byte
berücksichtigt. Nicht lesbare oder unvollständige Deskriptoren werden als
unbekannt gemeldet und nicht geraten.

## Passive Eingangsbeobachtung

Der Reader wird ausdrücklich über die stabile Interface-Nummer ausgewählt,
nicht über eine fest codierte hidraw-Nummer:

```text
python3 src/read_input.py --interface 0
python3 src/read_input.py --interface 1 --duration 5
```

Standardlaufzeit sind drei Sekunden; maximal akzeptiert das Programm 300
Sekunden. Es verwendet:

- `os.open(..., O_RDONLY | O_NONBLOCK)`,
- `select` mit der verbleibenden Laufzeit,
- ausschließlich `os.read` am hidraw-Dateideskriptor.

Es existiert kein Schreib- oder ioctl-Aufruf gegen den Geräteknoten. Bei
fehlenden Leserechten endet das Programm mit einer verständlichen Meldung,
ohne `sudo`, udev-Regeln, Gruppen oder Dateirechte zu verändern. Wenn während
des Zeitlimits keine Daten eintreffen, wird sauber mit null beobachteten
Reports beendet.

Jede empfangene Zeile enthält lokalen ISO-8601-Zeitstempel, Interface,
Byteanzahl und Hexdump.

## Optionale Rohdatensicherung

```text
python3 src/read_input.py --interface 1 --capture
python3 src/read_input.py --interface 1 --capture captures/meine-neue-datei.bin
```

Ohne Dateinamen wird ein zeitgestempelter Name unter `captures/` erzeugt.
Manuell angegebene Dateien müssen direkt dort liegen. Dateien werden mit
`O_EXCL` neu angelegt; ein vorhandener Name führt zum Abbruch. Die Datei
enthält die empfangenen Reports unmittelbar hintereinander. Zeitstempel,
Interface und Einzellängen stehen in der Konsolenausgabe und sollten bei einer
referenzierten Aufnahme separat protokolliert werden.

Bei null empfangenen Reports kann eine leere Capture-Datei entstehen. Auch sie
wird nicht nachträglich überschrieben.

## Sicherheitsgrenzen

- Keine dynamisch vergebenen `/dev/hidrawX`-Pfade im Code oder in dauerhafter
  Konfiguration.
- Keine Öffnung mit Schreibrechten.
- Keine Output- oder Feature-Reports.
- Keine HID-ioctls und keine USB-Control-Transfers.
- Keine Rechteänderung und keine Root-Anforderung.
- Keine automatische Interpretation unbekannter Eingangsdaten.
- Eine vorhandene Leseberechtigung ist keine Erlaubnis für Schreibzugriffe.
- Die Funktionszuordnung der beiden Interfaces bleibt unbestätigt.

Die bekannten Größen 440/440 Byte für Interface 0 und 16/1024 Byte für
Interface 1 dienen nur zum Vergleich mit den dynamisch ausgelesenen
Deskriptoren. Der Reader leitet daraus keine Paketbedeutung ab.

## Lokaler Erkennungstest 2026-07-29

`python3 -B src/discover_device.py` fand zwei passende Interfaces:

| Interface | dynamischer Pfad | Input | Output | Benutzer-lesbar |
| --- | --- | ---: | ---: | --- |
| 0 | `/dev/hidraw7` | 440 Byte | 440 Byte | nein |
| 1 | `/dev/hidraw8` | 16 Byte | 1024 Byte | nein |

Hersteller wurde als `ASUS Tek`, Produkt als
`TUF GAMING LC III 360 ARGB LCD` und Seriennummer als
`A247392SS000000` gelesen. Die udev-Eigenschaften bestätigten für beide
Knoten `ID_VENDOR_ID=0b05` und `ID_MODEL_ID=1c7b` sowie die
Interface-Nummern `00` und `01`.

Wegen fehlender Leseberechtigung wurde der Reader nicht gegen einen
Geräteknoten gestartet. Es wurden keine Berechtigungen verändert und keine
Capture-Dateien angelegt.
