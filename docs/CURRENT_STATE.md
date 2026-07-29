# Aktueller Projektstand

Stand: 2026-07-29

## Aktuelles Projektziel

Ziel ist eine native Linux-Steuerung für das LCD der ASUS TUF Gaming LC III
360 ARGB LCD. Die aktuelle Phase rekonstruiert das undokumentierte HID-
Protokoll ausschließlich statisch und passiv. Noch werden keine
Steuerbefehle an das Gerät gesendet.

## Bestätigte Hardware- und Protokollfakten

- Zielgerät: ASUS TUF Gaming LC III 360 ARGB LCD.
- USB-ID: `0b05:1c7b`.
- Das Gerät besitzt zwei HID-Interfaces mit Usage Page `0xff06`, Usage
  `0x01` und ohne im Reportdeskriptor deklarierte Report-IDs.
- Interface 0: 440 Byte Input, 440 Byte Output; Interrupt-Endpunkte `0x82`
  IN und `0x01` OUT.
- Interface 1: 16 Byte Input, 1024 Byte Output; Interrupt-Endpunkte `0x84`
  IN und `0x03` OUT.
- Dynamische `/dev/hidrawX`-Nummern sind keine stabile Geräteidentität.
- Die extrahierte Gerätefirmware ist 32-Bit ARM Little Endian, 201692 Byte
  lang und wurde in Ghidra an Basis `0x00100000` analysiert.
- Der 440-Byte-Transport besteht aus einem 4-Byte-Steuerwort und 436 Byte
  Nutzdaten.
- Ein zweiter Empfangspfad besteht aus einem 4-Byte-Steuerwort und 1020 Byte
  Nutzdaten, insgesamt 1024 Byte.
- Im Steuerwort enthält Byte 0 den Befehlswert. Bit 31 kennzeichnet das erste
  Paket; Bits 8..30 enthalten Paketanzahl beziehungsweise Segmentindex.
- Der Antwortbauer erzeugt segmentierte 440-Byte-Pakete. In diesem Pfad wurde
  keine Transportprüfsumme erkannt.
- USB `GET_DESCRIPTOR` wird separat vom Geräteprotokoll verarbeitet. Die
  Werte `0x01`, `0x02`, `0x03`, `0x06`, `0x07`, `0x21` und `0x22` sind dort
  Descriptor-Typen und keine Gerätebefehle.

## Bestätigte gefährliche Befehle

- `0x45`: Konfigurationslöschung im Windows-Updater.
- `0x86`: Firmwareblocktransfer im Updater; wegen möglicher
  modusabhängiger Semantik vollständig ausgeschlossen.
- `0x09`: verändert im normalen Dispatcher Anzeige-/Gerätezustand und dient
  im Updater als Completion-Flag.
- `0x02`: Abschluss-/Reenumerationspfad im Updater; trotz einfachem Zweig im
  normalen Dispatcher ausgeschlossen.
- `0x88`, transportiert als `88 01 00 80 ...`: führt zu SPI-Lesen und
  bedingtem SPI-Schreiben im Bereich `0x21000`.
- `0x1f`: verändert Moduszustand und kann einen Bootcallback anlegen.
- `0xff` mit Payload-DWORD 1: löst einen noch nicht vollständig aufgelösten
  indirekten Callback aus.

## Stärkster aktueller Kandidat: `0x87`

`0x87` erzeugt eine Zwei-Byte-Antwort mit dem konstanten Wert `0x0051`.
Der statisch abgeleitete Ein-Paket-Kandidat lautet:

```text
Anfrage, 440 Byte:  87 01 00 80 00 ... 00
Antwort, 440 Byte:  87 01 00 80 51 00 00 ... 00
```

Headeralgorithmus, Befehlswert, Antwortkonstante und Länge sind belegt.
Die Bedeutung als Versionsabfrage ist eine starke, aber noch nicht endgültig
bestätigte Ableitung. Das Paket ist keine Sendefreigabe.

## Offene Transportfragen

- Welches HID-Interface und welcher Endpoint führen zu den internen
  Callbackereignissen `0x35` und `0x38`?
- Ist trotz fehlender Report-ID im Deskriptor auf Host-API-Ebene ein
  zusätzliches führendes Nullbyte erforderlich?
- Wie ist der 1024-Byte-Empfänger mit Interface 1 verbunden?
- Welche Bedeutung haben die globalen Antwortquellen von `0x1e` und
  `0x80..0x85`?
- Welche indirekten Callbackziele verbinden Transport, LCD/Grafik,
  Dateisystem und SPI-Flash?

## Letzter abgeschlossener Arbeitsschritt

Ghidra 12.1 hat die Firmware statisch als `ARM:LE:32:v5t:default` analysiert.
USB-Setup-Pfad, Geräte- und Transportdispatcher, beide Segmentempfänger,
Antwortpaketbauer sowie der gefährliche SPI-Pfad von `0x88` wurden
dokumentiert. Firmwarekarte und Dispatcher-Matrix wurden aktualisiert.

## Nächster klarer Arbeitsschritt

Als Nächstes sind rein statisch die HID-Reportdeskriptorzeiger,
Endpoint-Callbacks und Registrierungen der Ereignisse `0x35`/`0x38` zu
verfolgen. Ziel ist die direkte Zuordnung des 440-Byte-Transports zu
Interface 0 und die Klärung eines möglichen Host-seitigen Präfixbytes.

## Sicherheitsgrenze

Weiterhin keine HID-Schreibtests: keine Output- oder Feature-Reports, keine
USB-Control-Transfers und keine Übertragung des `0x87`-Kandidaten. Ein
Schreibtest erfordert einen späteren, ausdrücklich freigegebenen Auftrag.
