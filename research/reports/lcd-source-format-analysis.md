# Quellformat des Grafikmodus `0x6021`

Stand: 2026-09-02

## Ergebnis

**JPEG ist für die Quellseite des `0x6021`-Pfads statisch belegt.**

Der entscheidende Beleg ist nicht nur passende Markerarithmetik: Der
Referenzaufrufer `0x0011acd8` validiert ein Eingabeobjekt als JPEG, kopiert
anschließend genau dessen unveränderte Quellbytes in einen zusammenhängenden
Beschleunigerpuffer und übergibt genau diesen Puffer als Quelle an Modus
`0x6021`. Erst danach wird Operation `0x0c` gestartet. Der eigentliche
Parser/Decoder hinter `0x0c` ist Hardware bei `0xb100a000`; ab `0x0c` wird
kein Software-JPEG-Parser mehr aufgerufen.

Untersucht wurde ausschließlich das vorhandene Firmwareimage und das
Read-only-Ghidra-Projekt. Es gab keine Gerätekommunikation und keine
Untersuchung anderer Protokollantworten oder Befehle.

## Marker- und Decoderbelege

`0x0011acd8` ruft vor dem Hardwarepfad `0x00110a58` auf. Diese Funktion:

- verlangt am Anfang `ff d8` (JPEG SOI);
- lässt den Markerparser `0x00124988` bis zum Frameheader laufen;
- akzeptiert `c0`, `c1` und `c2`, also SOF0, SOF1 und SOF2;
- liest Höhe und Breite als Big-Endian-16-Bit-Werte aus dem SOF;
- verwirft das Objekt bei ungültigem Marker oder ungültiger Geometrie.

Die Software-Referenzdekodierung `0x0010f16c`, die bei fehlgeschlagenem
Hardwarepfad verwendet wird, verarbeitet dasselbe JPEG-Objekt und prüft am
Bildende mit `0x00124988` ausdrücklich auf Marker `d9` (JPEG EOI).

Für den Hardwareversuch lädt `0x0011acd8` danach:

```text
r1 = source_pointer   aus 0x0013193c
r2 = source_length    aus 0x00131940
r0 = accelerator_input_buffer
indirect_copy(r0, r1, r2)
```

Es werden also die JPEG-Quelldaten in ihrer bekannten Länge kopiert, nicht
bereits dekodierte Pixelzeilen. Derselbe Buffer wird unmittelbar anschließend
über Grafikrouter-Operation `4` nach `b100a0a0` geschrieben. Abhängig nur von
der gewünschten Ausgabetiefe folgt Modus `0x6021` für 16 Bit beziehungsweise
`0x14021` für 32 Bit. Die zuvor aus dem JPEG-SOF gelesenen Dimensionen werden
über Operationen `0x0f` und `0x0e` gesetzt, der Zielbuffer über Operation `0`,
danach startet `0x0c`.

Damit ist die Datenidentität geschlossen:

```text
JPEG-Objekt
  -> SOI-/SOF-Prüfung
  -> bytegenaue Kopie von source_length Byte
  -> b100a0a0 (Hardwarequelle)
  -> mode 0x6021
  -> operation 0x0c
```

## Exakter Call-Tree

Der ab Operation `0x0c` tatsächlich erreichbare synchrone Pfad ist:

```text
0x001065c4, case 0x0c
  -> 0x001060ec
     -> 0x0010d6a8(0x004ea848, 0x24)   // Ergebniszustand löschen
     -> b100a02c = 0x4666              // Ereignisse freigeben/quittieren
     -> b100a000 bit 0 setzen/löschen  // Hardwaredecoder starten
```

Danach arbeitet der MMIO-Block asynchron. Sein bei der Initialisierung durch
`0x00105ea8` registrierter IRQ-`0x1a`-Handler ist:

```text
0x00105a10
  status 0x40
    -> 0x001059f4                      // erkannte Breite/Höhe aus b100a028
    -> optionaler Headercallback
    -> 0x0010574c                      // Zielgeometrie/-transfer konfigurieren
  status 0x08
    -> Ergebnisregister b100a0a8/b100a0ac sichern
  status 0x04
    -> 0x0010572c                      // Abschlusswerte lesen
    -> Status 0x04 quittieren
    -> active = 0                      // Dekodierung beendet
  status 0x02
    -> Status 0x02 quittieren
    -> active = 0, error = 1
  status 0x20
    -> optionaler Stream-Refill-Callback
```

`0x00105e3c` wartet auf `active == 0` und liefert Erfolg genau bei
`error == 0`. `0x00105e60` ist die nicht blockierende Abfrage desselben
Aktivzustands.

Die JPEG-Beweisstrecke vor diesem Downstream-Tree lautet:

```text
0x0011acd8
  -> 0x00110a58                       // FF D8, SOF0/1/2, Breite/Höhe
     -> 0x00124988                    // JPEG-Markerparser
  -> indirect_copy(source, length)    // komprimierte Bytes
  -> 0x001065c4(op 4, source)
  -> 0x001065c4(op 8, 0x6021)
  -> 0x001065c4(op 0x0f, height, width)
  -> 0x001065c4(op 0x0e, width)
  -> 0x001065c4(op 0, destination)
  -> 0x001065c4(op 0x0c)
  -> 0x00105e3c                       // Hardwareerfolg/-fehler
  -> bei Hardwarefehler 0x0010f16c   // Software-JPEG-Decoder, FF D9
```

Der Softwaredecoder ist keine von `0x0c` aufgerufene Unterfunktion, sondern
der Referenz-/Fallbackpfad desselben validierten Quellobjekts.

## Eingabelänge und Terminierung

Im Referenzpfad ist die Quelldateilänge bekannt und wird ausschließlich zum
Kopieren in den Beschleunigerpuffer benutzt. Weder `0x001065c4(op 4)` noch
`0x001060ec` übergibt diese Länge an den Hardwareblock. Der direkte
`0x6021`-Pfad besitzt ebenfalls kein anderes Längenregister im beobachteten
Setup.

Die Dekodiergrenze ist daher in-band im JPEG-Strom. Die Firmwarereferenz
fordert dafür `ff d9` und behandelt den EOI-Marker als erfolgreiches
Bildende. Im Hardwarepfad selbst ist die Markerprüfung nicht als ARM-Code
sichtbar; der MMIO-Decoder signalisiert nach erkanntem Ende Status `0x04`.
Darauf quittiert `0x00105a10` den Status, löscht `active` und macht das
Ergebnis verfügbar. Status `0x02` beendet denselben Ablauf mit Fehler.

Statisch nicht bestimmbar ist, ob der Hardwaredecoder ein vorzeitiges
Pufferende ohne EOI toleriert oder welche Bytes nach `ff d9` erlaubt sind.
Für ein Hostmodell ist deshalb `ff d9` die einzige belegte Terminierung; eine
separat übertragene JPEG-Länge existiert auf dieser Ebene nicht.

## Zielbuffer, Geometrie und Ausgabeformat

- Operation `0` setzt den Zielbuffer bei `b100a07c`.
- `0x6021` berechnet im IRQ-/Transferpfad exakt
  `erkannte_breite * erkannte_höhe * 2` Ausgabebyte.
- `0x14021` verwendet für dieselbe JPEG-Quelle vier Byte pro Pixel.
- Die 320×320-Konfiguration gehört zum Display-/Zielbuffer. Modus `0x6021`
  erzwingt nicht selbst 320×320; im Referenzpfad stammen die tatsächlichen
  Bilddimensionen aus dem JPEG-SOF.
- Der zusammenhängende JPEG-Eingabepuffer des Beschleunigerpfads hat
  `200 * 1024 = 0x32000` Byte Kapazität. Das ist eine Quellkapazität, kein
  Beleg für 204800 rohe Eingabepixelbyte.

## Wichtigste offene Frage

Offen bleibt die Hardwaretoleranz rund um das Ende des JPEG-Stroms:
Insbesondere ist statisch nicht sichtbar, ob und wie viele Paddingbytes nach
`ff d9` gelesen oder akzeptiert werden und ob der Hardwarepfad alle vom
Softwareparser zugelassenen SOF-Varianten C0/C1/C2 tatsächlich beschleunigt.
Das Quellformat selbst ist dagegen als JPEG belegt.
