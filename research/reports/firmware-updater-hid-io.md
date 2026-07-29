# Firmware-Updater: HID-I/O und Transporthelfer

## Beobachtete Fakten

- Die schreibende Routine bei `0x40b380` verwendet `WriteFile`. Sie reserviert
  `0x401` Byte, setzt das erste Byte auf null und schreibt die Nutzdaten ab
  Offset 1. Die Write-Länge wird aus einem internen 16-Bit-Wert bei
  Struktur-Offset `+6` übernommen, sofern dieser zwischen 1 und `0x400`
  liegt; sonst wird `0x401` verwendet.
- Die lesende Schwester bei `0x40b4e0` hat denselben `0x401`-Byte-Rahmen,
  verwendet `ReadFile` und kopiert nach Abschluss `0x400` Byte ab Puffer+1 in
  den Zielbereich.
- Beide Routinen unterstützen Overlapped-I/O. Bei `ERROR_IO_PENDING`
  (`0x3e5`) warten sie mit `WaitForMultipleObjects` höchstens `0xbb8`
  Millisekunden (3000 ms), rufen danach `GetOverlappedResult` auf und
  behandeln `WAIT_TIMEOUT` (`0x102`) gesondert.
- Die Strings `usb writex(%d):%08x` und `usb readex(%d):%08x` werden aus
  diesen Routinen referenziert. Dahinter liegen die beschriebenen
  WriteFile-/ReadFile-Schleifen; die Namen sind Diagnosebegriffe, keine
  exportierten Symbole.
- Vor I/O wird an Event-Handles mit `WaitForSingleObject(..., INFINITE)`
  serialisiert; der Code versucht eine Operation bis zu dreimal.
- Die Routine bei `0x402460` konstruiert einen `0x400`-Byte-Nutzpuffer. Byte 0
  stammt aus einem Funktionsargument. Byte 1 enthält einen 7-Bit-Zähler; beim
  ersten Segment ist zusätzlich Bit 7 gesetzt. Bis zu `0x3fe` Bytes folgen ab
  Offset 2. Folgesegmente löschen Bit 7 und erhöhen den 7-Bit-Wert.
- Die Routine bei `0x4027c0` liest entsprechend `0x400` Byte und prüft Byte 0
  gegen einen erwarteten Wert. Byte 1 wird als 7-Bit-Folgewert ausgewertet;
  Bit 7 kennzeichnet den ersten Teil. Daten beginnen bei Byte 2.

## Abgeleitete Zusammenhänge

- Das zusätzliche führende Nullbyte ist mit HID-Konventionen für Geräte ohne
  deklarierte Report-ID vereinbar. Es wird nicht als bestätigte Report-ID
  bezeichnet.
- Der 7-Bit-Wert verhält sich im Code wie eine Segmentfolge. Seine weitere
  Protokollsemantik ist unbekannt.
- Die `0x400` Nutzblockgröße passt zur 1024-Byte-Outputgröße des separat
  beobachteten Interface 1. Das ist eine starke Übereinstimmung, aber keine
  direkte Interfacezuordnung.

## Hypothesen

- Byte 0 könnte ein Befehl oder Kanalbezeichner sein. Sichtbare Werte werden
  ohne weitere Evidenz nicht als bestätigte Opcodes bezeichnet.
- Bit 7 von Byte 1 könnte „erstes Segment“ bedeuten; diese Benennung folgt nur
  dem Kontrollfluss.

## Unbekannt

- Bedeutung aller Werte in Byte 0.
- Ob die Steuerbytes Teil eines HID-Reports oder einer höheren
  Transportstruktur sind.
- Eine Prüfsummenberechnung über den Paketinhalt ist nicht erkennbar.

