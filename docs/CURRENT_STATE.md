# Aktueller Projektstand

Stand: 2026-08-05

## Aktuelles Projektziel

Ziel ist eine native Linux-Steuerung für das LCD der ASUS TUF Gaming LC III
360 ARGB LCD. Das undokumentierte HID-Protokoll wurde zunächst statisch und
passiv rekonstruiert. Am 2026-08-05 fand genau ein gesondert freigegebener,
eng begrenzter realer `0x87`-Test statt. Weitere HID-Schreibtests sind nicht
freigegeben.

## Bestätigte Hardware- und Protokollfakten

- Zielgerät: ASUS TUF Gaming LC III 360 ARGB LCD.
- USB-ID: `0b05:1c7b`.
- Das Gerät besitzt zwei HID-Interfaces mit Usage Page `0xff06`, Usage
  `0x01` und ohne im Reportdeskriptor deklarierte Report-IDs.
- Interface 0: 440 Byte Input, 440 Byte Output; Interrupt-Endpunkte `0x82`
  IN und `0x01` OUT.
- Interface 1: 16 Byte Input, 1024 Byte Output; Interrupt-Endpunkte `0x84`
  IN und `0x03` OUT.
- Die Firmware ordnet den 440-Byte-Pfad eindeutig Interface 0 zu:
  Endpointcallback 1 (`0x0010deb8`) bedient `0x01` OUT; Endpointcallback 2
  (`0x0010df88`) gehört zum 440-Byte-IN-Pfad über `0x82`.
- Der 1024-Byte-Empfänger `0x001297e8` wird direkt vom Endpoint-3-Callback
  `0x0010df9c` aufgerufen und gehört damit zu Interface 1 / `0x03` OUT.
  Endpointcallback 4 (`0x0010e0a8`) gehört zum 16-Byte-Pfad über `0x84` IN.
- Dynamische `/dev/hidrawX`-Nummern sind keine stabile Geräteidentität.
- Die extrahierte Gerätefirmware ist 32-Bit ARM Little Endian, 201692 Byte
  lang und wurde in Ghidra an Basis `0x00100000` analysiert.
- Der 440-Byte-Transport besteht aus einem 4-Byte-Steuerwort und 436 Byte
  Nutzdaten.
- Ein zweiter Empfangspfad besteht aus einem 4-Byte-Steuerwort und 1020 Byte
  Nutzdaten, insgesamt 1024 Byte.
- Die High-Speed-Konfiguration setzt die vier Endpointgrößen direkt auf
  440, 440, 1024 und 16 Byte. Die Reportdeskriptorzeiger für Interface 0/1
  lauten `0x00131330`/`0x00131350`, jeweils mit Länge 29 Byte.
- Die internen Ereignisse `0x35` und `0x38` sind keine USB-Endpointnummern:
  `0x35` stellt vollständige Befehle dem Gerätedispatcher zu; `0x38` ist der
  wiederholt ausgelöste 440-Byte-Transporttick.
- Linux `hidraw.write()` erwartet für Interface 0 genau 441 Byte:
  ein Host-API-Reportnummernbyte `00` plus den 440-Byte-Outputreport. Der
  USB-HID-Treiber entfernt die Null vor dem 440-Byte-Transfer auf `0x01`.
- Dieses Nullbyte ist weder Padding noch eine firmwareseitige Report-ID. Die
  gleiche Null-ID-Konvention erklärt den `WriteFile`-Puffer des
  Windows-Updaters.
- Der Updater füllt beim Öffnen `HIDP_CAPS` in sein I/O-Objekt und liest für
  `WriteFile` `OutputReportByteLength` an Caps-Offset `+0x06`; der Lesepfad
  verwendet `InputReportByteLength` an `+0x04`.
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
bestätigte Ableitung. Die Route ist nun ebenfalls belegt: Interface 0,
`0x01` OUT für die Anfrage und `0x82` IN für die Antwort. Das Paket ist keine
Sendefreigabe.

Im realen Einmaltest wurde zwar eine Antwort mit exakt 440 Byte empfangen, ihr
Inhalt wich jedoch von der statisch erwarteten Gesamtfolge ab. Die Antwortbytes
wurden nicht gespeichert und können deshalb nicht nachträglich ausgewertet
werden. Die statische Erwartung ist damit für diesen Lauf nicht praktisch
bestätigt; die konkrete Abweichung bleibt unbekannt.

Die abschließende statische Sicherheitsklasse lautet **wahrscheinlich rein
lesend**. Der `0x87`-Case selbst liest keinen Payload und baut ausschließlich
die konstante Antwort `0x0051`. Der gemeinsame Dispatcherprolog kann jedoch
in einem bestimmten Konfigurationsmodus RAM-Flags und flüchtige
Peripherieregister verändern. Weder dieser rekursive Unterbaum noch der
Antwortbauer erreicht einen bekannten Flash-, SPI-, Dateisystem-, Boot-,
Reset- oder persistenten Konfigurationspfad. Details stehen in
`../research/reports/command-0x87-safety-review.md`.

## Bestätigte Testspezifikation

- Ziel: Interface 0, zur Laufzeit über VID `0b05`, PID `1c7b` und
  Interface-Nummer 0 bestimmt.
- Einmaliger Linux-Write: 441 Byte
  `00 | 87 01 00 80 | 436 × 00`.
- Erwarteter Read: 440 Byte
  `87 01 00 80 51 00 | 434 × 00`.
- Genau ein Writeversuch, keine Wiederholung; Antwortdeadline 3 Sekunden.
- Bei partiellem Write, Fehler, Timeout, Disconnect oder abweichender Antwort
  sofort schließen und nichts nachsenden.

## Restrisiken

- Der gemeinsame Dispatcherprolog kann flüchtige RAM- und
  Peripheriezustände verändern.
- Eine volle Antwortqueue oder ein dauerhaftes USB-Busy kann zu Timeout
  beziehungsweise vorübergehendem Transportstillstand führen.
- Andere Firmwareversionen, Boot-/Updatemodi, Firmwarefehler sowie ein
  falsch ausgewähltes Interface fallen nicht unter die Bewertung.
- Die konkrete 440-Byte-Antwort des ersten realen Tests ist nicht erhalten.
  Ein erneuter Test allein zur Gewinnung dieser Bytes ist nicht zulässig.

## Ergebnis des realen Einmaltests 01

- Datum: 2026-08-05; exakte Uhrzeit nicht protokolliert.
- Interface 0 wurde dynamisch als `/dev/hidraw7` erkannt.
- Genau ein 441-Byte-Request
  `00 | 87 01 00 80 | 436 × 00` wurde gesendet.
- Genau eine Antwort mit 440 Byte wurde empfangen.
- Der Inhalt wich von
  `87 01 00 80 51 00 | 434 × 00` ab.
- Die tatsächlichen Antwortbytes wurden nicht gespeichert.
- Das Programm schloss sofort und sendete nichts nach.
- Die temporäre Schreibregel wurde entfernt; beide Interfaces besitzen wieder
  `0640`.
- Die AIO wird weiterhin normal erkannt. Im Kernelprotokoll erschienen keine
  testbedingten USB-Fehler, Resets oder Disconnects.

Der vollständige Bericht liegt unter
`../research/reports/command-0x87-live-test-01.md`.

## Offene Transportfragen

- Welche Semantik hat der 16-Byte-IN-Pfad von Interface 1?
- Welche höhere Bedeutung haben die über Interface 1 / `0x03` OUT
  empfangenen 1024-Byte-Daten? `0x08` kennzeichnet dort statisch den
  gesonderten Datenqueue-/Zustandspfad; die höhere Bedeutung bleibt offen.
- Wie ist dieser Interface-1-`0x08`-Datenpfad mit dem zustandsändernden
  Grafik-/Systemzweig von Befehl `0x08` auf Interface 0 verbunden?
- Welche Bedeutung haben die globalen Antwortquellen von `0x1e` und
  `0x80..0x85`?
- Welche indirekten Callbackziele verbinden Transport, LCD/Grafik,
  Dateisystem und SPI-Flash?

## Letzter abgeschlossener Arbeitsschritt

Der einmalige reale `0x87`-Test und der vollständige Rückbau der temporären
Schreibrechte wurden dokumentiert. Die Diagnose für einen etwaigen zukünftigen,
neu autorisierten Test gibt unerwartete Antworten nach dem Schließen vollständig
als Hexdump und Bytevergleich aus, ohne sie dauerhaft zu speichern.

## Nächster klarer Arbeitsschritt

Keine Wiederholung des Tests allein zur Gewinnung der fehlenden Antwortbytes.
Weitere Arbeit bleibt zunächst offline und untersucht statisch, welche
Transport-, Queue- oder Zustandsannahme die Abweichung erklären könnte. Jeder
weitere reale HID-Write wäre ein neuer Test und benötigte eine eigene
Sicherheitsbewertung und ausdrückliche Freigabe.

## Sicherheitsgrenze

Weiterhin keine weiteren HID-Schreibtests: keine Output- oder Feature-Reports,
keine USB-Control-Transfers und keine erneute Übertragung des `0x87`-Kandidaten.
Der abgeschlossene Einmaltest erteilt keine Wiederholungsfreigabe. Ein weiterer
Schreibtest erfordert einen neuen, ausdrücklich freigegebenen Auftrag.
