# Statische Sicherheitsbewertung von Befehl `0x87`

Stand: 2026-07-29

## Ergebnis

Die abschließende Einstufung lautet:

> **wahrscheinlich rein lesend**

| Bewertungsstufe | Entscheidung |
| --- | --- |
| nachweislich rein lesend | nein |
| wahrscheinlich rein lesend | **ja** |
| unklar | nein |
| nicht sicher | nein |

Der befehlsspezifische `case 0x87` ist statisch vollständig und
antwortorientiert: Er liest keinen Payload, legt den konstanten
16-Bit-Wert `0x0051` auf dem Stack ab und übergibt ihn dem
440-Byte-Antwortbauer. Dieser Zweig erreicht keinen Flash-, SPI-,
Dateisystem-, Boot-, Reset- oder persistenten Konfigurationspfad.

Die stärkere Einstufung **nachweislich rein lesend** ist für den vollständigen
Handlerpfad trotzdem nicht gerechtfertigt. Vor der Befehlsauswahl besitzt der
Gerätedispatcher einen gemeinsamen, modusabhängigen Prolog. Wenn
`Konfiguration[0x111] == 2` gilt, schreibt er ein RAM-Flag auf null. Beim
ersten solchen Aufruf setzt er ein zweites RAM-Flag und ruft eine
Peripherie-Initialisierung auf, die mehrere Memory-Mapped-Register verändert.
Ihr vollständig statisch erreichbarer direkter Unterbaum enthält keine
bekannte persistente oder gefährliche Routine, ist aber nachweislich nicht
rein lesend.

Die Bewertung gilt ausschließlich für Firmware 51 mit SHA-256
`c4679ec340fc5edd3dea960ee027281cf6bd81cbbf347afb40e0d0b4f40aeb9f`,
den normalen 440-Byte-Pfad auf Interface 0 und das exakt angegebene Paket.
Sie ist keine Ausführung oder Sendefreigabe.

## Umfang und Evidenz

Verwendet wurden ausschließlich vorhandene statische Artefakte:

- `ghidra-static-export-v4.txt`
- `ghidra-dispatcher-call-paths.txt`
- `dispatcher-handler-matrix.tsv`
- `ghidra-memory-classification.txt`
- `hid-host-framing.md`
- die erfassten USB- und HID-Reportdeskriptoren
- die vorhandenen statischen Firmware- und Updaterberichte

Zusätzlich wurde das bestehende Ghidra-Projekt read-only und mit
`-noanalysis` geöffnet, um für die bereits analysierte Firmware
Funktionsdekompilate, Speicherreferenzen und rekursive direkte
Erreichbarkeit zu exportieren. Es gab keine Emulation, keine
Firmwareausführung, keinen Zugriff auf ein HID-Gerät und keine
Gerätekommunikation.

Der rekursive direkte Call-Graph ab dem gemeinsamen Prolog `0x0010dd58` und
dem Antwortbauer `0x001298f8` umfasst 43 Funktionen und 55 Kanten. In diesem
Unterbaum existiert kein indirekter Call. Die indirekten Calls vor dem Handler
gehören zum generischen internen Ereignisrouter; ihr für Ereignis `0x35`
registriertes Ziel ist statisch der Gerätedispatcher `0x00126dfc`.

## Vollständiger befehlsrelevanter Aufrufpfad

### Empfang und Zustellung

```text
Interface 0 / 0x01 OUT, 440 Byte
  -> Endpoint-1-Callback 0x0010deb8
  -> 440-Byte-Empfangsqueue
  -> internes Ereignis 0x38
  -> transport_dispatch_candidate 0x001293f8
  -> Queue-Leser 0x0012a390
  -> segmented_command_receive_candidate 0x001296d8
  -> generischer Ereignisrouter 0x0012b3bc, Ereignis 0x35
       -> Tabelleniterator 0x0012b54c oder 0x0012b470
       -> Callbackauflösung 0x0012ad64
       -> indirekter Aufruf des registrierten Callbacks
  -> device_command_dispatch_candidate 0x00126dfc
```

`0x0012b3bc` enthält den einzigen für die Zustellung wesentlichen
unaufgelösten `blx r12`. Registrierung, Busobjekt und akzeptiertes Ereignis
ordnen das Laufzeitziel in diesem Pfad dem Gerätedispatcher zu. Der Router
wählt das Ziel anhand des internen Ereignisses, nicht anhand des
`0x87`-Payloads.

Der Segmentempfänger stellt den Dispatcher erst nach einem vollständigen
Segment bereit. Für den Ein-Paket-Header `87 01 00 80` sind Befehlsbyte
`0x87`, Paketanzahl 1 und First-Packet-Bit 31 gesetzt. Die 436 Payloadbytes
sind für den `0x87`-Case ohne Bedeutung.

### Globale Variablen und Speicherzugriffe nach Phase

Die folgende Tabelle erfasst alle für den `0x87`-Kontrollfluss relevanten
globalen Speicherklassen. Reine Code-/Konstantenreferenzen werden von
veränderlichem RAM und Memory-Mapped-I/O getrennt:

| Phase | Globale/Adresse | Zugriff und Wirkung |
| --- | --- | --- |
| Endpointempfang | Endpoint-1-Zustand, 440-Byte-Empfangspuffer und Empfangsqueue | USB-Status lesen/Bestätigen, Paket in flüchtigen Queue-/Segmentzustand übernehmen |
| Segmentierung | Zustand hinter `DAT_001296bc` | Steuerwort, Segmentindex, Länge und 436 Payloadbytes lesen beziehungsweise im flüchtigen Rekonstruktionspuffer ablegen |
| Ereigniszustellung | Busobjekt `DAT_001296c0` sowie Callbacktabellen des Routers | Registrierungstabellen lesen; Callback indirekt aufrufen; keine befehlsspezifische Persistenz |
| Dispatcher-Prolog | `DAT_001275d4` → Konfigurationsbasis `0x004e8348` | Byte `+0x111` und bedingt Byte `+0` lesen |
| Dispatcher-Prolog | `DAT_001275d8` → `0x001315c8` | bedingt null schreiben |
| Dispatcher-Prolog | `DAT_001275dc` → `0x001314fc` | lesen und beim ersten Modus-2-Aufruf eins schreiben |
| Dispatcher-Vorladung | `DAT_001275e0`, `DAT_001275e4`, `DAT_001275e8`, `DAT_001275ec`, `DAT_001275f0`, `DAT_001275f4`, `DAT_00127618` | Pointer/Konstanten lesen; der `0x87`-Case dereferenziert sie nicht als Antwortquelle |
| `case 0x87` | Stack bei `sp+4` und Aufrufargument bei `sp+0` | `0x0051` als Halfword und null als fünftes Argument schreiben |
| Antwortbauer | `DAT_00129ad4` | Headermaske lesen |
| Antwortbauer | `DAT_00129ad8` → Antwortqueue | Basis, Ende, Schreibzeiger, Slotgröße, Belegung und Kapazität lesen; Schreibzeiger und Belegung erhöhen; 440-Byte-Slot beschreiben |
| Queue-voll-Fehler | Queueoffsets `+0x10`, `+0x12`, `+0x14`; Diagnoseglobals um `0x00131788`, `0x00131789`, `0x001317a4`; Register `0xb0000004` | Zähler lesen, Diagnosezustand lesen/schreiben und gegebenenfalls Zeichenausgabe initialisieren |
| Antworttransport | `DAT_001296b0`, `DAT_001296c4`, `DAT_001296c8`, `DAT_001296cc`, `DAT_001296d0`, `DAT_001296d4` | Queue-/Endpointzeiger lesen, Queuezustand reservieren/freigeben und Transferadresse setzen |
| Antworttransport | `0xb100805c`, `0xb1008060`, `0xb1008700` | USB-Controllerzustand und Transferlänge/-adresse schreiben; Busybit lesen |
| Abschluss | Endpoint-2-Transferzustand | flüchtigen IN-Transferzustand löschen |

Die Übernahme des eingehenden Reports, Queueverwaltung und USB-Ausgabe sind
damit erwartete Schreibseiteneffekte des Transports. Sie ändern keine
fachliche oder persistente Gerätekonfiguration. Die einzige zusätzliche,
nicht rein transportbedingte Schreibklasse ist der nachfolgend beschriebene
gemeinsame Peripherieprolog.

### Gemeinsamer Prolog vor `case 0x87`

Nach Prüfung auf Ereignis `0x35`, aber vor der Befehlsauswahl, führt
`0x00126dfc` aus:

```text
wenn *(0x004e8348 + 0x111) == 2:
    *(uint32_t *)0x001315c8 = 0
    wenn *(uint32_t *)0x001314fc == 0:
        *(uint32_t *)0x001314fc = 1
        FUN_0010dd58(*(uint8_t *)0x004e8348)
```

Die Assemblerfolge bei `0x00126e48` lädt das erste Konfigurationsbyte in
`r0`, unmittelbar bevor `0x0010dd58` aufgerufen wird. Der parameterlose
Decompiler-Ausdruck an dieser Call-Site ist daher kein Beleg für einen
unbestimmten Wert.

Der direkte Unterbaum von `0x0010dd58` ist:

```text
0x0010dd58
  -> 0x0010892c
  -> 0x00108b28
       -> 0x001019b0
       -> Integerdivision 0x0010dcf8 / 0x0010d80c
       -> Rechenhelfer 0x0012e3d0, 0x0012e560, 0x0012e628,
          0x0012e6ac, 0x0012e6d4, 0x0012e758, 0x0012e908
          -> gemeinsamer Rechenhelfer 0x0012e858
  -> 0x00109278
  -> 0x00108a28
  -> alternativ 0x0010853c -> 0x001003f8
  -> alternativ 0x0010895c -> 0x001003f8
```

Wenn das erste Konfigurationsbyte Bit 7 nicht gesetzt und in Bits 0..6
ungleich null ist, wird der erste Initialisierungszweig genommen. Andernfalls
wird der alternative Deaktivierungs-/Rücksetzzweig genommen. Statisch
sichtbare Zugriffe umfassen:

- Timing-/Konfigurationswerte im RAM bei `0x001316e4..0x001316fc`,
- RAM-/Peripheriezustand um `0x004ea90c`,
- Memory-Mapped-Register bei `0xb0000018`, `0xb000008c`,
  `0xb0000208`, `0xb8000124`, `0xb8001030..0xb8001038` und
  `0xb8007000..0xb800707c`.

Die Routinen konfigurieren damit flüchtigen Hardwarezustand. Die genaue
Peripheriebezeichnung ist ohne Registerdokumentation nicht bestätigt. Im
vollständig rekursiv aufgelösten direkten Unterbaum gibt es keine indirekten
Calls und keine Kante zu den bekannten SPI-, Flash-, Dateisystem-, Boot-,
Reset- oder Konfigurationsspeicherroutinen.

### Befehlsspezifischer Zweig

Die vollständige `0x87`-Sequenz bei `0x00127588..0x001275a4` ist:

```text
mov  r0,#0x51
strh r0,[sp,#0x4]       ; Stackwert 0x0051
mov  r3,#0              ; kein optionales Präfix
mov  r2,#2              ; zwei Antwortbytes
add  r1,sp,#0x4         ; Zeiger auf 0x51 0x00
mov  r0,#0x87           ; Antwortbefehl
str  r6,[sp,#0]         ; Segment-/Präfixlänge 0
b    0x001275c8
```

Bei `0x001275c8` folgt genau ein direkter Aufruf von
`response_packet_builder_candidate` bei `0x001298f8`. Der Case:

- liest `param_4` beziehungsweise den Request-Payload nicht,
- liest keine befehlsspezifische globale Variable,
- schreibt nur den lokalen Stackwert `0x0051`,
- ruft keine andere Handlerfunktion auf,
- besitzt keine alternative Verzweigung innerhalb des Cases.

Die übrigen direkten Callees des großen Gerätedispatchers gehören exklusiven
anderen Cases. Sie sind für `local_2c == 0x87` kontrollflussseitig nicht
erreichbar. Insbesondere werden die im selben Dispatcher vorhandenen
Konfigurations-, Boot- und zustandsändernden Befehlszweige nicht durchlaufen.

### Antwortaufbau und Queue

Der direkte Unterbaum von `0x001298f8` lautet:

```text
0x001298f8 response_packet_builder_candidate
  -> 0x0010d6a8  Speicher nullen
  -> 0x0010dcf8  Integerdivision
  -> 0x0010d430  Speicher kopieren
  -> 0x0012a2cc  festen Antwort-Queue-Slot reservieren
  -> 0x0010d5d8  Speicher kopieren
  -> bei voller Queue: 0x00103d14 Diagnoseausgabe
```

Für zwei Datenbytes und Präfixlänge null berechnet der Antwortbauer genau ein
440-Byte-Paket. Er nullt seinen lokalen Puffer, setzt das Steuerwort auf
`87 01 00 80`, kopiert `51 00` an Payloadoffset null und kopiert anschließend
alle 440 Byte in einen reservierten Slot der globalen Antwortqueue.

`0x0012a2cc` verändert ausschließlich Zeiger, Belegungszähler und
Wrap-around-Zustand des Queueobjekts. Bei voller Queue liefert es null. Dann
wird keine Antwort eingereiht; stattdessen wird die Meldung
`no enough space1` über `0x00103d14` ausgegeben.

Der vollständig direkte Fehlerlogger-Unterbaum besteht aus Formatierung,
Zeit-/Diagnosezustand und Zeichenausgabe:

```text
0x00103d14
  -> 0x00103cf0, 0x00103050, 0x001014b8
  -> 0x00103504 -> 0x00103438, 0x00100510, 0x0010042c
  -> 0x00103ad4 -> 0x001036d8, 0x0010d3e0, 0x00103914,
                    0x0010389c, 0x001038c4
  -> weitere Blatthelfer 0x001003bc, 0x00100b18, 0x00100b94,
                          0x0010dd28, 0x001038ec
```

Auch dieser Fehlerunterbaum enthält keinen indirekten Call und keine
statische Kante zu persistentem Speicher oder Reset. Er kann jedoch
flüchtigen Diagnose-/Ausgabezustand initialisieren und verändern.

### Senden der Antwort und nachgelagerte Seiteneffekte

Beim nächsten Transportereignis `0x38`:

```text
transport_dispatch_candidate 0x001293f8
  -> Queueprüfung/-reservierung 0x0012a3f0
  -> USB-Endpointzustand und Register bei 0xb100805c,
     0xb1008060 und 0xb1008700 setzen
  -> gegebenenfalls auf Controllerbit 0x20 warten
  -> Queuezustand zurücksetzen
  -> 440 Byte mit 0x0010d430 in den Endpointpuffer kopieren
  -> Endpoint-2-Abschlusscallback 0x0010df88 löscht Transferzustand
```

Das sind notwendige flüchtige Transportseiteneffekte. Im Firmwarepfad ist für
die Controller-Warteschleife kein eigener Softwaretimeout sichtbar.

Nach dem Kopieren prüft der Transportdispatcher das niederwertige Byte des
Pakets. Nur wenn es `0xff` ist, folgen ein weiteres internes Ereignis und
`0x0012a218`, eine Routine mit Scheduler-/Stop-Aufrufen und Endlosschleife.
Bei der korrekt gebauten `0x87`-Antwort ist das erste Byte fest `0x87`; der
Sprung verlässt den Zweig daher vor diesem Pfad. Der gefährliche
`0xff`-Nachlauf ist für die korrekte `0x87`-Antwort kontrollflussseitig
ausgeschlossen.

## Prüfung auf gefährliche Funktionsklassen

| Funktionsklasse | Befund im vollständigen `0x87`-Pfad |
| --- | --- |
| Flash-Schreiben/-Löschen | nicht erreichbar |
| SPI-Lesen/-Schreiben | nicht erreichbar |
| Dateisystemzugriff | nicht erreichbar |
| Boot-/Upgradepfad | nicht erreichbar |
| Reset/Fatalpfad | nur im nachgelagerten `0xff`-Sonderzweig; für Antwortbyte `0x87` ausgeschlossen |
| Persistente Konfiguration | nicht erreichbar |
| RAM-Schreibzugriffe | vorhanden: Segment-, Queue-, Transfer- und Initialisierungszustand |
| Memory-Mapped-I/O | vorhanden: USB-Transport; bedingt gemeinsamer Peripherieprolog |
| Diagnoseausgabe | nur wenn die Antwortqueue voll ist |

„Nicht erreichbar“ bedeutet hier: keine statische direkte Kante im
rekursiven befehlsrelevanten Unterbaum und keine passende
kontrollflussseitige Route über die bekannten indirekten Ereignisaufrufe.
Unbekannte Firmwarefehler und durch Ghidra nicht erkannter Code können damit
nicht mathematisch ausgeschlossen werden.

## Zustands- und Modusabhängigkeit

Der konstante `0x87`-Antwortinhalt selbst hängt statisch weder vom Payload
noch vom Gerätezustand ab. Unterschiedliches Verhalten ist an folgenden
Grenzen möglich:

- Ein Callbackereignis ungleich `0x35` wird abgewiesen; es entsteht keine
  `0x87`-Antwort.
- Ein unvollständiger oder inkonsistenter Segmentheader erreicht den
  Gerätedispatcher möglicherweise nicht.
- Ist `Konfiguration[0x111]` ungleich 2, wird der gemeinsame
  Peripherieprolog vollständig übersprungen.
- Ist der Wert gleich 2, wird `0x001315c8` bei jedem Aufruf auf null gesetzt.
- Ist zusätzlich `0x001314fc` noch null, wird es auf eins gesetzt und
  `0x0010dd58` einmal ausgeführt. Dessen Zweig hängt vom ersten
  Konfigurationsbyte ab.
- Ist die Antwortqueue voll, wird geloggt und keine Antwort eingereiht.
- Bleibt der USB-Controller im Busy-Zustand, kann der Transporttask in der
  sichtbaren Warteschleife verbleiben; der Host sieht dann einen Timeout.
- Nicht analysierte andere Firmwareversionen, Bootloader- oder Updatemodi
  fallen nicht unter diese Bewertung.

Vorherige Initialisierung kann also die flüchtigen Seiteneffekte verändern,
nicht aber den statisch gebauten Wert `0x0051`.

## Vollständig spezifiziertes Testpaket

Für Linux `hidraw.write()` wäre genau ein 441-Byte-Userspace-Puffer
erforderlich:

```text
Offset 0:       00
Offset 1..4:    87 01 00 80
Offset 5..440:  436-mal 00
```

Das erste Byte ist das Host-API-Reportnummernfeld für einen unnummerierten
Report. Der Linux-USB-HID-Treiber entfernt es. Auf `0x01` OUT gehen genau
440 Byte:

```text
Offset 0..3:    87 01 00 80
Offset 4..439:  436-mal 00
```

Die erwartete einzelne `hidraw.read()`-Antwort ist genau 440 Byte:

```text
Offset 0..3:    87 01 00 80
Offset 4..5:    51 00
Offset 6..439:  434-mal 00
```

Interface 0 muss zur Laufzeit anhand VID `0b05`, PID `1c7b` und
USB-Interface-Nummer 0 bestimmt werden; eine feste `/dev/hidrawX`-Nummer ist
unzulässig.

## Abbruch- und Timeoutverhalten eines späteren Einzeltests

Ein später ausdrücklich freigegebener Test sollte folgende harte Grenzen
haben:

1. Genau ein Writeversuch, keine automatische Wiederholung.
2. Erfolg nur bei einem Write-Rückgabewert von exakt 441.
3. Danach genau eine Antwort bis zu einer festen Hostdeadline von 3 Sekunden
   abwarten.
4. Die 3 Sekunden sind eine konservative Hostregel, keine aus der Firmware
   abgeleitete Antwortgarantie.
5. Bei partiellem Write, `EAGAIN`, `EIO`, Disconnect, Timeout, falscher Länge
   oder abweichendem Inhalt sofort abbrechen, den Deskriptor schließen und
   nichts erneut senden.
6. Keine Reset-, Boot-, Konfigurations-, Feature-Report- oder
   USB-Control-Transfer-„Recovery“ auslösen.

Ein nonblocking geöffneter hidraw-Deskriptor mit `poll()`/`select()` verhindert
einen unbegrenzt blockierenden Hostleser. Die Firmware selbst besitzt im
sichtbaren USB-Sendezweig keine entsprechende Timeoutgarantie.

## Denkbare Fehlerfälle und minimale Recovery

| Fehlerfall | Beobachtbares Ergebnis | Minimale Maßnahme |
| --- | --- | --- |
| falsches hidraw-Interface oder zwischenzeitliche Reenumeration | falsches Ziel, Writefehler oder unerwartete Antwort | sofort schließen; VID/PID/Interface neu nur lesend bestimmen |
| falsche API-Länge oder fehlendes Nullpräfix | partieller/abgewiesener Write oder falsch gerahmter Gerätebefehl | nicht korrigierend nachsenden; schließen |
| Antwortqueue voll | Diagnoseausgabe, keine Antwort | Hosttimeout; schließen |
| USB-Controller bleibt busy | keine Antwort, möglicher Transporttask-Stall | schließen; zunächst Gerät beobachten |
| zustandsabhängiger gemeinsamer Prolog | flüchtige Peripherie-/Anzeigeänderung möglich | keine weiteren Writes; Zustand beobachten |
| unerwarteter 440-Byte-Report | möglicherweise alter oder fremder Queueinhalt | als Fehlschlag protokollieren; schließen |
| Gerät verschwindet oder wird unresponsiv | `ENODEV`/`EIO`, Timeout | erst USB-Verbindung neu herstellen; nur falls nötig AIO stromlos machen |

Die minimale Recovery-Reihenfolge ist:

1. Hostseitig abbrechen und den Dateideskriptor schließen.
2. Keine weiteren Protokollbefehle senden.
3. Prüfen, ob das Gerät ohne Eingriff normal weiterarbeitet.
4. Nur bei anhaltender Störung USB neu verbinden.
5. Nur wenn das nicht genügt, die AIO kontrolliert aus- und wieder einschalten.

Ein softwareseitiger Resetbefehl ist ausdrücklich keine minimale Recovery,
weil sein Pfad gefährlicher und schlechter verstanden ist als `0x87`.

## Verbleibendes Schadensrisiko

Für das exakt gerahmte Paket unter Firmware 51 ist das Risiko einer
persistent schädigenden Wirkung **sehr gering, aber nicht null**:

- Es wurde kein persistenter oder destruktiver Pfad gefunden.
- Der eigentliche Case ist konstant und antwortorientiert.
- Der gemeinsame Prolog kann jedoch flüchtige Peripherieregister ändern.
- Queueüberlauf oder USB-Busy können zu ausbleibender Antwort und
  vorübergehender Transportstörung führen.
- Generische Callbackinfrastruktur, nicht dokumentierte Hardwarewirkung,
  Firmwarefehler und andere Laufzeitmodi verhindern einen formalen
  Nullrisikobeweis.
- Ein falsches Zielgerät, falsches Interface oder falsch gerahmtes Paket
  liegt außerhalb dieser Bewertung und kann ein deutlich höheres Risiko
  haben.

## Schlussentscheidung

Ein einzelner `0x87`-Test ist nun **technisch vollständig spezifiziert**:
Zielinterface, Linux-Write-Länge, API-Präfix, 440-Byte-Drahtpaket,
erwartete 440-Byte-Antwort, Einmaligkeit, Timeout, Abbruchkriterien und
minimale Recovery sind festgelegt.

Die statische Sicherheitsklasse bleibt **wahrscheinlich rein lesend** und
nicht „nachweislich rein lesend“, weil der gemeinsame Handlerprolog
zustandsabhängig nachweisbare flüchtige Schreibzugriffe besitzt. Dieses
Dokument erteilt keine praktische Testfreigabe.
