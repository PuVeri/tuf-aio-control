# HID-Host-Framing für Interface 0

Stand: 2026-07-29

## Umfang und Methode

Diese Untersuchung klärt ausschließlich statisch die Host-/Reportgrenze des
440-Byte-Pfads. Verwendet wurden:

- die erfassten USB- und HID-Reportdeskriptoren,
- die vorhandenen Ghidra-Ergebnisse zur Gerätefirmware,
- die statische x86-Disassembly des Firmware-Updaters,
- die maßgebliche Linux-`hidraw`-Dokumentation und der zugehörige
  Linux-USB-HID-Quellpfad,
- die Microsoft-Dokumentation zu `HIDP_CAPS`.

Es wurde keine Firmware ausgeführt oder emuliert, kein HID-Gerät geöffnet und
nichts an das Gerät gesendet.

## Ergebnis

Für einen regulären `write()` auf dem Linux-`hidraw`-Knoten von Interface 0
muss der Userspace-Puffer **441 Byte** enthalten:

```text
Userspace an hidraw.write(), 441 Byte:
00 | <440 Byte HID-Outputreport>
^^
Reportnummer 0 für einen unnummerierten Report
```

Der USB-HID-Treiber entfernt diese führende Null vor dem Interrupttransfer.
Auf Endpoint `0x01` werden daher exakt **440 Byte** übertragen. Für den
statischen `0x87`-Kandidaten lautet die Trennung:

```text
Linux-hidraw-Puffer, 441 Byte:
00 87 01 00 80 00 ... 00

USB-Report auf 0x01 OUT, 440 Byte:
   87 01 00 80 00 ... 00
```

Ein 440-Byte-Argument ohne Nullpräfix ist nicht die dokumentierte
`hidraw.write()`-Form. Dass der raw Interruptpfad bestimmte abweichende
Puffer möglicherweise unverändert weiterreichen kann, macht diese Form nicht
zu einer korrekten oder belastbaren API-Spezifikation.

## Linux-`hidraw`: API-Länge und Drahtlänge

Die Linux-Kerneldokumentation legt für `hidraw.write()` fest:

- Byte 0 des Userspace-Puffers ist die Reportnummer.
- Bei Geräten ohne nummerierte Reports ist Byte 0 null.
- Die eigentlichen Reportdaten beginnen bei Byte 1.
- Besitzt das USB-Gerät einen Interrupt-OUT-Endpoint, wird darüber gesendet.

Der aktuelle Linux-Quellpfad bestätigt die API-/Drahtgrenze:

```text
hidraw_write
  -> hidraw_send_report(..., HID_OUTPUT_REPORT)
  -> __hid_hw_output_report
  -> usbhid_output_report
     -> wenn buf[0] == 0:
          buf++
          count--
     -> usb_interrupt_msg(..., buf, count, ...)
```

`usbhid_output_report` zählt das entfernte Byte nur für den Rückgabewert von
`write()` wieder hinzu. Bei einem erfolgreichen 441-Byte-Aufruf werden somit
440 Byte auf USB übertragen und 441 Byte als verarbeitet gemeldet.

Maßgebliche Quellen:

- Linux-Kerneldokumentation:
  <https://www.kernel.org/doc/html/latest/hid/hidraw.html>
- Linux `drivers/hid/hidraw.c`:
  <https://github.com/torvalds/linux/blob/master/drivers/hid/hidraw.c>
- Linux `drivers/hid/usbhid/hid-core.c`, `usbhid_output_report`:
  <https://github.com/torvalds/linux/blob/master/drivers/hid/usbhid/hid-core.c>

Das Nullbyte ist damit **nicht ausschließlich eine Windows-Konvention**.
Windows und Linux verwenden an ihren jeweiligen HID-API-Grenzen ein
Reportnummernbyte mit Wert null, wenn der Reportdeskriptor keine Report-ID
deklariert. Das Byte gehört nicht zum 440-Byte-Report auf dem USB-Endpoint.

Für normales `hidraw.read()` gilt die andere, ebenfalls dokumentierte Grenze:
Bei unnummerierten Reports beginnt die gelesene Nutzinformation direkt bei
Byte 0. Eine 440-Byte-Antwort von Interface 0 wird daher als 440 Byte gelesen,
nicht als 441 Byte mit vorangestellter Null.

## Firmware-Updater: Caps und tatsächliche `WriteFile`-Länge

Der Updater hält in seinem geöffneten HID-Objekt ab Offset `+0x28` eine
`HIDP_CAPS`-Struktur. Der statische Aufbau lautet:

```text
0x40c010
  -> Zieladresse Objekt + 0x28
  -> 0x40bf00
     -> HidD_GetPreparsedData
     -> HidP_GetCaps(preparsed, Objekt + 0x28)
```

Der Schreibpfad übergibt genau `Objekt + 0x28` an den I/O-Helfer:

```text
0x402460 oder 0x40c230
  -> erzeugt 0x401-Byte-Ablage
     Byte 0 = 00
     Byte 1..0x400 = 0x400 Byte Transportinhalt
  -> 0x40b380
     -> liest WORD [caps + 0x06]
     -> WriteFile
```

Nach dem dokumentierten Layout von `HIDP_CAPS` ist Offset `+0x06`
`OutputReportByteLength`:

```text
+0x00  Usage
+0x02  UsagePage
+0x04  InputReportByteLength
+0x06  OutputReportByteLength
+0x08  FeatureReportByteLength
```

`0x40b380` verwendet den Wert an `caps + 0x06`, wenn er ungleich null und
kleiner als `0x401` ist. Bei fehlendem Caps-Zeiger, Wert null oder einem Wert
größer/gleich `0x401` verwendet die Routine `0x401`. Da die lokale
Pufferkapazität ebenfalls `0x401` beträgt, ist dies eine Begrenzungs- und
Fallbacklogik. Die Schwesterroutine `0x40b4e0` liest entsprechend
`InputReportByteLength` an Caps-Offset `+0x04`.

Microsoft dokumentiert, dass `InputReportByteLength` und
`OutputReportByteLength` das vorangestellte Report-ID-Feld einschließen und
dass dessen Wert null ist, wenn keine Report-IDs verwendet werden:

<https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidpi/ns-hidpi-_hidp_caps>

Der Updater erfindet seine `WriteFile`-Länge folglich nicht aus der
Transportnutzlast. Er ermittelt sie beim Öffnen über `HidP_GetCaps` und
verwendet `OutputReportByteLength`, begrenzt durch den eigenen
`0x401`-Byte-Puffer. Seine Ablage `00 + 0x400 Byte` ist Windows-HID-Framing;
die Null ist keine Nutzlast der Gerätefirmware.

Der Aufzählungspfad bei `0x40be1c` ruft `HidP_GetCaps` ebenfalls auf, kopiert
aus dieser temporären Struktur aber nur `UsagePage` und `Usage` in den
Aufzählungsdatensatz. Für die I/O-Längen maßgeblich ist der spätere
vollständige Caps-Aufruf bei `0x40bf63` in das geöffnete I/O-Objekt.

## Exakte Übereinstimmung des 440-Byte-Pfads

Der Reportdeskriptor von Interface 0 enthält:

```text
75 08       Report Size  = 8 Bit
96 b8 01    Report Count = 0x01b8 = 440
91 02       Output
```

Er enthält kein Global Item `Report ID` (`0x85`). Der Outputreport besteht
daher aus exakt 440 Byte und besitzt auf dem Gerät kein Report-ID-Byte.

Diese Länge stimmt nicht nur numerisch, sondern an allen statisch sichtbaren
Grenzen exakt überein:

| Grenze | Länge |
| --- | ---: |
| HID-Outputreport laut Interface-0-Reportdeskriptor | 440 Byte |
| USB `wMaxPacketSize` von `0x01` OUT | 440 Byte |
| High-Speed-Endpointkonfiguration der Firmware | `0x1b8` = 440 Byte |
| Endpoint-1-Callback `0x0010deb8` | `0x1b8` = 440 Byte |
| Segmentempfänger | 4 Byte Steuerwort + `0x1b4` = 436 Byte |
| Antwortbauer und `0x82` IN | `0x1b8` = 440 Byte |
| Linux-Userspace-Puffer für `hidraw.write()` | 1 API-Byte + 440 Byte |

Die Gerätefirmware liest ihr vier Byte langes Steuerwort ab dem ersten
Endpointbyte. Das erste USB-Byte ist somit der Befehlswert, beispielsweise
`0x87`, und nicht Report-ID oder Padding.

## Befehl `0x08`

Statisch sind zwei transportabhängige `0x08`-Pfade sichtbar. Sie dürfen nicht
zu einer einzigen, weitergehenden Semantik zusammengezogen werden.

### Interface 0 / 440-Byte-Gerätedispatcher

```text
Interface 0, 0x01 OUT
  -> Endpoint-1-Callback 0x0010deb8
  -> interner Transporttick 0x38
  -> Transportdispatcher 0x001293f8
  -> Segmentempfänger 0x001296d8
  -> internes Ereignis 0x35
  -> Gerätedispatcher 0x00126dfc, case 0x08
```

Der Case setzt globalen Zustand zurück beziehungsweise aus der
Konfigurationsstruktur neu, ruft `0x001056a4` auf und führt mehrere Aufrufe von
`0x001065c4` mit den Werten `8`, `0`, `0x11`, `4` und `0x0c` aus. In einen
Aufruf geht der Payloadzeiger mit gesetztem Bit 31 ein. Der Zweig ruft den
gemeinsamen Antwortbauer nicht auf und endet mit `0xffffffff`.

Belastbar ist damit: `0x08` ist auf Interface 0 kein reiner Status- oder
Versionsleser, sondern stößt eine zustandsändernde Grafik-/Systemfolge an.
Eine konkretere Benennung wie „Bild anzeigen“, „Framebuffer übernehmen“ oder
„Animation starten“ ist aus den vorhandenen Symbol- und Call-Graph-Daten nicht
bestätigt.

### Interface 1 / 1024-Byte-Datenempfänger

```text
Interface 1, 0x03 OUT
  -> Endpoint-3-Callback 0x0010df9c
  -> 1024-Byte-Segmentempfänger 0x001297e8
  -> bei vollständigem Befehl 0x08:
       Übernahme in den zugehörigen Datenqueue-/Zustandspfad
```

Der Segmentempfänger verarbeitet 4 Byte Steuerwort plus 1020 Byte Daten.
`0xff` wird nach Abschluss als internes Ereignis `0x35` weitergereicht;
`0x08` wird dagegen in den gesonderten Datenqueue-/Zustandspfad übernommen.
Damit ist `0x08` auf Interface 1 ein belegter Kennwert für den großen
Datentransport. Die höhere Datenbedeutung und eine vollständige statische
Verknüpfung mit dem Interface-0-Case `0x08` bleiben offen.

## Konsequenz für einen einzelnen `0x87`-Test

Der Austausch ist **transporttechnisch vollständig gerahmt**:

```text
Ziel:       Interface 0, dynamisch anhand VID/PID und Interface 0 ermittelt
Write-API:  hidraw.write(), genau 441 Byte
Write:      00 | 87 01 00 80 00 ... 00
USB OUT:         87 01 00 80 00 ... 00  (440 Byte auf 0x01)
Read-API:   hidraw.read(), bis zu 440 Byte
Erwartung:  87 01 00 80 51 00 00 ... 00 (440 Byte von 0x82)
Wiederholung: keine
```

Damit sind Interface, Endpointroute, API-Präfix, Drahtlänge, Anfrage und
statisch erwartete Antwort festgelegt. Dies ist weiterhin **keine
Sendefreigabe**. Nicht vollständig bestätigt sind die fachliche Bedeutung von
`0x87`, das Laufzeitverhalten in jedem Gerätemodus und ein operativer
Sicherheits-/Abbruchplan. Technisch spezifiziert ist die einzelne Transaktion;
als freigegebener praktischer Test ist sie es nicht.

## Verbleibende Unsicherheiten

- `0x87` liefert sicher `0x0051`; die Bezeichnung als Versionsabfrage bleibt
  eine starke, nicht endgültig bestätigte Semantik.
- Das Verhalten des Befehls außerhalb des analysierten normalen
  Firmwaremodus ist nicht statisch belegt.
- Die höhere Bedeutung der über Interface 1 mit `0x08` übertragenen Daten und
  ihre Verbindung zum Interface-0-Case `0x08` bleiben offen.
- Die Semantik des 16-Byte-IN-Pfads von Interface 1 bleibt offen.
- Zeitverhalten, Timeout und ein praktischer Abbruch-/Recoveryplan wurden
  nicht durch Gerätekommunikation validiert.
