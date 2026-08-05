# Temporäre udev-Regel für einen `0x87`-Einmaltest

## Zweck und Freigabegrenze

Diese Anleitung bereitet einen zeitlich eng begrenzten Schreibzugriff für
genau einen manuell autorisierten `0x87`-Test vor. Die Regel darf erst
unmittelbar vor diesem Test installiert und muss unabhängig vom Testergebnis
sofort danach entfernt werden.

Die Datei im Repository wird durch diese Dokumentation nicht installiert oder
aktiviert. Die vorhandene dauerhafte Leseregel
`/etc/udev/rules.d/99-tuf-aio-control.rules` bleibt unverändert.

## Bestätigte Geräteeigenschaften

Am 2026-08-05 wurden die Eigenschaften erneut rein lesend über sysfs und
`udevadm info` geprüft:

| Merkmal | Interface 0 | Interface 1 |
| --- | --- | --- |
| USB-ID | `0b05:1c7b` | `0b05:1c7b` |
| `SUBSYSTEM` | `hidraw` | `hidraw` |
| `ID_USB_INTERFACE_NUM` | `00` | `01` |
| Inputreport | 440 Byte | 16 Byte |
| Outputreport | 440 Byte | 1024 Byte |

Damit ist `ENV{ID_USB_INTERFACE_NUM}=="00"` als udev-Selektor für Interface 0
bestätigt. Die Regel kombiniert ihn mit Subsystem, Kernelname sowie
Vendor-/Product-ID. Interface 1 mit dem bestätigten Wert `01` passt nicht.

Die aktuelle Zuordnung lautete bei der Prüfung `/dev/hidraw7` für Interface 0
und `/dev/hidraw8` für Interface 1. Diese Nummern sind nur eine Momentaufnahme
und werden weder in der Regel noch in dauerhafter Konfiguration verwendet.

## Exakte temporäre Regel

Repositorydatei:
`udev/99-tuf-aio-control-temporary-write-test.rules`

```udev
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="0b05", ATTRS{idProduct}=="1c7b", ENV{ID_USB_INTERFACE_NUM}=="00", GROUP:="input", MODE:="0660"
```

`0660` gibt Eigentümer und Gruppe Lese-/Schreibrecht; andere Benutzer erhalten
keinen Zugriff. Die Gruppe ist ausschließlich `input`. Es gibt kein `0666`, kein
`uaccess`-Tag und keine Regel für andere Geräte oder Interface 1.

Der finale Zuweisungsoperator `:=` ist erforderlich: Der vorgegebene temporäre
Dateiname wird lexikografisch vor `99-tuf-aio-control.rules` verarbeitet. Ohne
finale Zuweisung würde die später gelesene Dauerregel den Modus für Interface 0
wieder auf `0640` setzen. `GROUP:="input"` und `MODE:="0660"` verhindern nur
für den exakt passenden temporären Datensatz eine spätere Überschreibung.
Interface 1 trifft die temporäre Regel nicht und erhält weiterhin `0640` aus
der dauerhaften Leseregel.

## 1. Offline-Validierung

Ohne Root-Rechte und vor jeder Installation:

```text
udevadm verify udev/99-tuf-aio-control-temporary-write-test.rules
```

Erwartet werden Exit-Code 0 und keine Fehlermeldung. Bei Warnung oder Fehler
darf die Regel nicht installiert werden.

Die aktuelle Gerätezuordnung und die bestätigten Interfacewerte erneut anzeigen:

```text
python3 -B src/discover_device.py --json
```

Die Ausgabe muss genau einen Treffer mit Interface 0, `0b05:1c7b`, 440 Byte
Input, 440 Byte Output und ohne Report-ID sowie Interface 1 mit
`ID_USB_INTERFACE_NUM=01` zeigen. Bei Abweichung wird abgebrochen.

## 2. Manuelle Installation

Diese Befehle sind nur für einen Administrator nach ausdrücklicher Freigabe
dokumentiert. Sie wurden bei Erstellung dieser Datei nicht ausgeführt.

Zuerst sicherstellen, dass keine gleichnamige temporäre Systemregel existiert:

```text
sudo test ! -e /etc/udev/rules.d/99-tuf-aio-control-temporary-write-test.rules
```

Wenn der Test fehlschlägt, nichts überschreiben. Die vorhandene Datei muss
zuerst manuell geklärt und gegebenenfalls nach ihrem eigenen Rückbauverfahren
entfernt werden.

Danach die geprüfte Datei installieren:

```text
sudo install -o root -g root -m 0644 \
  udev/99-tuf-aio-control-temporary-write-test.rules \
  /etc/udev/rules.d/99-tuf-aio-control-temporary-write-test.rules
```

Die dauerhafte Datei `/etc/udev/rules.d/99-tuf-aio-control.rules` darf dabei
weder ersetzt noch bearbeitet werden.

## 3. Regeln laden und ausschließlich Interface 0 triggern

```text
sudo udevadm control --reload-rules
sudo udevadm trigger --action=add --subsystem-match=hidraw \
  --property-match=ID_VENDOR_ID=0b05 \
  --property-match=ID_MODEL_ID=1c7b \
  --property-match=ID_USB_INTERFACE_NUM=00 \
  --settle
```

Der Trigger ist auf die bereits bestätigten Eigenschaften von Interface 0
begrenzt. Interface 1 wird in diesem Schritt nicht erneut ausgelöst. Ein
physisches Neuanschließen ist für diesen Ablauf nicht vorgesehen, weil es beide
Interfaces neu erzeugen und die Expositionszeit unnötig vergrößern würde.

## 4. Modus und Interfacebegrenzung prüfen

Die dynamischen Knoten unmittelbar nach dem Trigger erneut ermitteln:

```text
python3 -B src/discover_device.py --json
```

Die dort ausgegebenen aktuellen Pfade für die folgenden Platzhalter verwenden:

```text
udevadm info --query=property --name=<interface-0-node>
udevadm info --query=property --name=<interface-1-node>
stat -c '%a %G %n' <interface-0-node> <interface-1-node>
```

Zwingende Erwartung:

```text
Interface 0: ID_USB_INTERFACE_NUM=00, Gruppe input, Modus 660
Interface 1: ID_USB_INTERFACE_NUM=01, Gruppe input, Modus 640
```

Zusätzlich muss `id` die Gruppe `input` in der aktuellen Sitzung nennen:

```text
id
```

Wenn irgendein weiteres Gerät oder Interface Schreibrecht erhalten hat, wenn
Interface 1 nicht `0640` besitzt oder wenn Interface 0 nicht eindeutig ist,
darf kein Test stattfinden. Dann sofort mit dem Rückbau beginnen.

## 5. Einmaliger manueller Test

Zuerst noch einmal den nicht schreibenden Dry-Run ausführen:

```text
python3 -B src/test_command_0x87.py --dry-run
```

Nur wenn alle vorherigen Prüfungen erfolgreich waren und eine gesonderte
menschliche Ausführungsfreigabe für genau diesen Lauf vorliegt:

```text
python3 -B src/test_command_0x87.py --i-understand-the-risk
```

Dieser Befehl darf innerhalb der temporären Freigabe **genau einmal** gestartet
werden. Bei Erfolg, Fehler, partiellem Write, Timeout, Disconnect oder
unerwarteter Antwort ist jeder zweite Versuch verboten. Es darf weder derselbe
Befehl wiederholt noch ein anderes Paket als Recovery gesendet werden.

Unmittelbar nach der ersten Programmrückgabe beginnt der Rückbau, unabhängig vom
Exit-Code. Wenn das Programm nicht gestartet wird, beginnt der Rückbau ebenfalls
sofort nach der Entscheidung zum Abbruch.

## 6. Sofortiger Rückbau

Vor dem Entfernen prüfen, dass exakt die installierte temporäre Datei mit dem
Repositoryexemplar übereinstimmt:

```text
sudo cmp --silent \
  udev/99-tuf-aio-control-temporary-write-test.rules \
  /etc/udev/rules.d/99-tuf-aio-control-temporary-write-test.rules
```

Wenn `cmp` fehlschlägt, nicht blind löschen. Inhalt und Herkunft der Systemdatei
müssen manuell geklärt werden. Bei erfolgreichem Vergleich:

```text
sudo rm -- /etc/udev/rules.d/99-tuf-aio-control-temporary-write-test.rules
sudo udevadm control --reload-rules
```

Danach die unveränderte dauerhafte Leseregel auf beide Zielinterfaces erneut
anwenden:

```text
sudo udevadm trigger --action=add --subsystem-match=hidraw \
  --property-match=ID_VENDOR_ID=0b05 \
  --property-match=ID_MODEL_ID=1c7b \
  --settle
```

Damit wird keine Datei neu installiert. `udevadm` wertet die weiterhin
vorhandene ursprüngliche Leseregel lediglich erneut aus.

## 7. Rückbau prüfen

```text
sudo test ! -e /etc/udev/rules.d/99-tuf-aio-control-temporary-write-test.rules
python3 -B src/discover_device.py --json
udevadm info --query=property --name=<interface-0-node>
udevadm info --query=property --name=<interface-1-node>
stat -c '%a %G %n' <interface-0-node> <interface-1-node>
```

Abschließend müssen beide Interfaces wieder Gruppe `input` und Modus `0640`
besitzen:

```text
Interface 0: ID_USB_INTERFACE_NUM=00, Gruppe input, Modus 640
Interface 1: ID_USB_INTERFACE_NUM=01, Gruppe input, Modus 640
```

Wenn Interface 0 weiterhin schreibbar ist, gilt der Rückbau als fehlgeschlagen.
Es darf kein weiterer HID-Test stattfinden; Regelstatus und aktueller
Geräteknoten müssen administrativ geklärt werden.
