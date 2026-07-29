# Extrahierte Gerätefirmware: rein statische Analyse

Stand: 2026-07-29, Europe/Berlin

## Extraktion und Integrität

Quelle: `research/extracted/firmware-v51/WW11_320x320_2.8inch_v51_TUF_20250626.exe`.
Extrahierte Kopie:
`research/extracted/device-firmware-v51-static/device-firmware-v51.bin`.

| Merkmal | Wert |
| --- | --- |
| Dateioffset Start | `0x1c15b0` |
| Dateioffset Ende exklusiv | `0x1f298c` |
| Länge | `0x313dc` = 201692 Byte |
| korrespondierende PE-VA | `0x5c21b0..0x5f358c` |
| SHA-256 | `c4679ec340fc5edd3dea960ee027281cf6bd81cbbf347afb40e0d0b4f40aeb9f` |
| Shannon-Entropie | `5.96620154` Bit/Byte |
| `file` | `data` |

Die Region liegt vollständig in `.rdata`. Direkt dahinter folgen weitere
Updaterdaten, darunter `05 0b 00 00 7b 1c 00 00`; diese sind nicht Teil der
Kopie. Die Grenzprüfung erfolgte gegen den im Updater fortgeschriebenen
Quellzeiger und die heruntergezählte Länge.

Rohbefunde: `device-firmware-metadata.txt`,
`device-firmware-strings-ascii.txt`, `device-firmware-strings-utf16le.txt`,
`device-firmware-descriptor-scan.txt` und `device-firmware-dispatch-raw.txt`.

## Architektur

Der Anfang lautet:

```text
17 00 00 ea 20 f0 9f e5 20 f0 9f e5 20 f0 9f e5
20 f0 9f e5 44 33 22 11 20 f0 9f e5 20 f0 9f e5
```

Die Little-Endian-Wörter sind ARM-typische Vektorsprünge/LDR-Instruktionen.
Weitere Bereiche enthalten ARM- und Thumb-/Interworking-artige Muster. Damit
ist 32-Bit-ARM-Little-Endian-Code bestätigt. Ein konkreter ARM-Kern, ABI oder
vollständiger Link-Load-Adressenraum ist nicht bestätigt. `N9H20 UDC Library`
ist nur ein Plattformhinweis.

## USB/HID

Im Code um `0x2c340` werden folgende Requestwerte verglichen:

```text
0x06, 0x01, 0x02, 0x03, 0x07, 0x21, 0x22
```

Der String `USBR_GET_DESCRIPTOR pkt.wLength = %d` liegt bei `0x2c644`.
Das belegt USB-Request-/Descriptorverarbeitung, aber keine LCD-Opcodesemantik.

Die bekannten 29-Byte-HID-Deskriptoren der Interfaces 0 und 1 wurden nicht
bytegenau gefunden. Ein isoliertes `06 06 ff` bei `0x311a9` passt im weiteren
Kontext nicht zum Deskriptor und ist kein Beleg für Usage Page `0xff06`.

`05 0b 7b 1c` erscheint bei `0x2ebb0` und `0x311e8`. Der erste Treffer liegt
in einer Konfigurations-/Konstantenregion mit USB-nahen Werten und `0x51`; eine
direkte Deskriptorzuordnung ist nicht bewiesen. Der zweite Treffer ist
semantisch offen. Kandidaten für Deskriptorheader bei `0x311f3`, `0x31201`,
`0x3120a` bilden keine validierte Deskriptorkette.

Die Reportgrößen 16, 440 und 1024 wurden gesucht, aber nicht als belastbare
Firmware-HID-Längen gefunden. `0x1b4` (436) wird in Empfangscode verglichen;
eine bestätigte 440-Byte-Reportgröße darf daraus nicht abgeleitet werden.

## Dispatcher und mögliche LCD-Befehle

Ein gerätespezifischer Dispatcher ab `0x26e00` vergleicht `0x02`, `0x17`,
`0x18..0x1f`, `0x35`, `0x80..0x87` und `0xfd..0xff`. Ein weiterer Dispatcher
bei `0x29400` vergleicht `0x03`, `0x06`, `0x38` und `0x3b`.

Das sind mögliche Nachrichten-/Befehlswerte, aber keine bestätigten normalen
LCD-Befehle: Richtung, Report, Aufrufer und Antwortformat fehlen. Der Handler
für `0x86` existiert auch in der Firmware, bleibt aber wegen der direkten
Übereinstimmung mit der belegten Firmwareblockübertragung ein gefährlicher
Upgradepfad. Es wird kein Dispatcherwert zur Übertragung empfohlen.

## LCD-, Bild- und Flashhinweise

Beobachtete Strings:

- `LCM_Init Start!!`
- `SEGGER emWin V5481110`
- `lcd_boot_proc reboot`, `exit`, `restart---`
- `c:\\syst\\boot`, `c:\\syst\\wapper.jpg`
- `SPI flash id [0x%x]`
- `load config ok` / `load config faild`
- `Shenzhen Xinyao Technology Co., Ltd.`

PNG-, JPEG- und GIF-Dateisignaturen, belastbare Pixelformatstrings und
CRC32-Polynome wurden nicht gefunden. Die Strings belegen Grafik-/LCD-
Initialisierung und eine JPG-bezogene Datei-/Bootreferenz, keinen USB-
Bildtransfer. Bei `0x30820` stehen mehrere `0x0140`-Werte (= 320) in einer
Tabelle. Zusammen mit `320x320` im externen Firmwaredateinamen ist dies ein
Auflösungshinweis, aber keine bestätigte Geometrie oder Farbcodierung.

`0x8000` kommt mehrfach vor; die Firmwaretransportblockgröße `0x8000` ist
separat im Windows-Updater belegt und nicht automatisch eine normale LCD-
Blockgröße.

## Abgrenzung zum gefährlichen Updater

Der Updater belegt `0x45` (direkt nach „Wiping configuration“), `0x86`
(Firmwareblöcke), `0x09` (Completion-Flag), `0x02` (Abschluss/Reenumeration)
und direkte Rohpuffer `88 01 00 80 ...` (Boot-/Post-Upgrade). Diese Werte
werden nicht als normale LCD-Befehle umgedeutet. Die Firmwaredispatcherbefunde
liefern keinen unabhängigen sicheren Status-/Versionspfad.

## Offene Fragen und Sicherheitsentscheidung

Offen bleiben die tatsächliche HID-Empfangsfunktion, Register-/Pufferfelder,
Interfacezuordnung, normale LCD-Befehlsbedeutungen, Bildformat, 320x320-
Orientierung, Pixelformat, Prüfsummen und die Bedeutung der USB-Kandidaten am
Nutzlastende. Ein kontrollierter Schreibtest ist daraus nicht freigegeben.

Nichts wurde ausgeführt, kein USB-/HID-Gerät geöffnet und nichts an die AIO
gesendet.
