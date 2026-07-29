# Rein lesende udev-Regel

Stand: 2026-07-29.

## Zweck

Die Regel gibt Mitgliedern der bestehenden Gruppe `input` ausschließlich
Leserechte auf den dynamisch erzeugten hidraw-Knoten der ASUS TUF Gaming LC III
360 ARGB LCD mit USB-ID `0b05:1c7b`.

Sie gilt nur, wenn gleichzeitig

- das Subsystem `hidraw` ist,
- der Kernelname `hidraw*` entspricht,
- ein USB-Elterngerät Vendor-ID `0b05` und Product-ID `1c7b` besitzt.

Andere HID-Geräte werden nicht erfasst. Die dynamischen Namen wie
`/dev/hidraw7` oder `/dev/hidraw8` stehen nicht in der Regel.

## Systemprüfung

Auf dem untersuchten System existiert keine Gruppe `plugdev`. Die Gruppe
`input` existiert:

```text
input:x:104:l
```

Der Benutzer `l` ist in der Gruppendatenbank als Mitglied eingetragen. Die
aktuelle Sitzung führte GID 104 bei der Prüfung jedoch noch nicht als
Supplementärgruppe. Nach einer neuen Anmeldung ist daher mit `id` zu prüfen,
ob `input` tatsächlich in der laufenden Sitzung aktiv ist. Es werden keine
Gruppenänderungen automatisiert.

Die udev-Datenbank meldete:

| Knoten | Interface | Subsystem | VID:PID | Tags |
| --- | ---: | --- | --- | --- |
| `/dev/hidraw7` | 0 | `hidraw` | `0b05:1c7b` | `seat` |
| `/dev/hidraw8` | 1 | `hidraw` | `0b05:1c7b` | `seat` |

In der aktuellen isolierten Ausführungsumgebung waren die sysfs-Einträge und
udev-Datensätze vorhanden, die `/dev/hidraw7`- und `/dev/hidraw8`-Knoten selbst
aber nicht sichtbar. Deshalb konnten aktuelle Eigentümer, Modusbits und ACLs
nicht direkt mit `stat` beziehungsweise `getfacl` festgestellt werden.

Es war kein `uaccess`-Tag vorhanden, nur `seat`. Ob logind außerhalb dieser
Ausführungsumgebung eine ACL setzt, muss am realen Geräteknoten geprüft werden.
Die vorgeschlagene Regel verwendet bewusst kein `TAG+="uaccess"`, weil damit
keine klar auf Leserechte begrenzte Freigabe dokumentiert wäre.

## Genaue Regel

Datei im Repository: `udev/99-tuf-aio-control.rules`

```udev
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="0b05", ATTRS{idProduct}=="1c7b", GROUP="input", MODE="0640"
```

`MODE="0640"` bedeutet:

- Eigentümer: lesen und schreiben,
- Gruppe `input`: nur lesen,
- andere Benutzer: keine Rechte.

Die Regel erweitert die Rechte des normalen Benutzers damit ausschließlich um
Lesen. Sie verwendet weder `0666` noch Gruppen-Schreibrechte. Root bleibt
Eigentümer des vom Kernel/udev verwalteten Knotens; die Regel kann und soll
Root-Rechte nicht beschränken.

Wichtig: Die Unix-Modusbits verhindern Schreibzugriffe für Mitglieder der
Gruppe `input`. Sie ersetzen nicht die Sicherheitsinvariante der Anwendung,
den Geräteknoten ausschließlich mit `O_RDONLY` zu öffnen.

## Manuelle Installation

Die folgenden Befehle sind für eine bewusste Ausführung durch einen
Administrator dokumentiert. Sie wurden nicht ausgeführt:

```text
sudo install -o root -g root -m 0644 \
  udev/99-tuf-aio-control.rules \
  /etc/udev/rules.d/99-tuf-aio-control.rules
```

Vorhandene Zieldateien dürfen nicht still überschrieben werden. Vorher prüfen:

```text
sudo test ! -e /etc/udev/rules.d/99-tuf-aio-control.rules
```

Falls dieser Test fehlschlägt, muss die vorhandene Datei manuell geprüft
werden; nicht mit `install` ersetzen.

## Regeln neu laden

```text
sudo udevadm control --reload-rules
```

Das Neuladen allein ändert normalerweise keinen bereits existierenden
Geräteknoten. Bevorzugt das Gerät anschließend physisch trennen und wieder
anschließen.

Alternativ kann ein Administrator die Regeln für hidraw-Geräte erneut
auswerten:

```text
sudo udevadm trigger --subsystem-match=hidraw --action=add
sudo udevadm settle
```

Der Trigger betrifft die erneute udev-Auswertung aller hidraw-Knoten, die Regel
selbst passt aber nur auf `0b05:1c7b`. Physisches Neuanschließen ist leichter
nachvollziehbar und wird bevorzugt.

## Prüfung

Nach Neuanschluss die aktuellen dynamischen Pfade erneut ermitteln:

```text
python3 -B src/discover_device.py
```

Anschließend die tatsächlich ausgegebenen Pfade verwenden, beispielsweise:

```text
ls -l /dev/hidraw7 /dev/hidraw8
getfacl /dev/hidraw7 /dev/hidraw8
udevadm info --query=property --name=/dev/hidraw7
udevadm info --query=property --name=/dev/hidraw8
id
```

Erwartet wird für passende Knoten Eigentümer `root`, Gruppe `input` und
`crw-r-----` (`0640`). `ID_VENDOR_ID=0b05`, `ID_MODEL_ID=1c7b` und die
Interface-Nummern `00` beziehungsweise `01` müssen weiterhin stimmen.

Wenn `id` die Gruppe `input` nicht nennt, ist eine vollständige Ab- und
Neuanmeldung erforderlich. Es sollen weder `chmod` noch `setfacl` auf den
Geräteknoten angewendet werden.

Erst wenn das Discovery-Skript `lesbar: ja` meldet, kann der separat
dokumentierte Reader bewusst gestartet werden. Die Installation der udev-Regel
startet selbst keinen Reader und sendet keine Daten.

## Vollständige Entfernung

Durch einen Administrator:

```text
sudo rm -- /etc/udev/rules.d/99-tuf-aio-control.rules
sudo udevadm control --reload-rules
```

Danach das Gerät trennen und wieder anschließen. Alternativ:

```text
sudo udevadm trigger --subsystem-match=hidraw --action=add
sudo udevadm settle
```

Vor dem Entfernen ist zu bestätigen, dass exakt die genannte Datei die zuvor
installierte Projektregel ist. Das Repositoryexemplar wird dabei nicht
gelöscht.

## Auswirkungen eines Neuanschlusses

Beim Neuanschluss werden hidraw-Knoten neu erzeugt. Ihre Nummern können sich
ändern; ein bisheriges `/dev/hidraw7` kann beispielsweise zu einem anderen
Pfad werden. Laufende Reader verlieren ihren Dateideskriptor oder erhalten ein
Ende-/Fehlerereignis und müssen nach erneuter dynamischer Erkennung neu
gestartet werden.

Ein Neuanschluss kann außerdem einen kurzfristigen Geräte-Reset und eine
Neubindung des `usbhid`-Treibers verursachen. Die udev-Regel selbst öffnet das
Gerät nicht, liest keine Reports und sendet keine Daten.

## Alternative ohne bestehende geeignete Gruppe

Auf Systemen ohne `input` oder `plugdev` ist eine dedizierte Gruppe wie
`tuf-aio-readers` sicherer als eine pauschale Freigabe. Gruppe, Mitgliedschaft
und eine entsprechend angepasste `GROUP="tuf-aio-readers"`-Regel müssten durch
einen Administrator bewusst eingerichtet werden. `MODE="0640"` bleibt
unverändert. Es darf nicht auf `0666`, `0660` oder ein `uaccess`-Tag
ausgewichen werden.

