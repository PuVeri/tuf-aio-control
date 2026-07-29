# Ghidra-Firmwarekarte

Stand: 2026-07-29

## Methodik

Die extrahierte Firmware wurde mit Ghidra 12.1 statisch als Raw Binary,
`ARM:LE:32:v5t:default`, an Loader-Basis `0x00100000` analysiert. Der
geladene Block reicht von `0x00100000` bis `0x001313db` und ist nach der
Vorbereitung lesbar, nicht schreibbar und ausführbar markiert.

Begriffe in diesem Bericht:

- **Beobachtet**: direkt in Bytes, Instruktionen, Xrefs oder Decompiler-Output
  sichtbar.
- **Abgeleitet**: durch mehrere beobachtete Befunde gestützt.
- **Hypothese**: plausible, aber nicht hinreichend belegte Bedeutung.
- **Unbekannt**: durch diese statische Analyse nicht aufgelöst.

Die Rohbelege stehen insbesondere in:

- `ghidra-static-export-v4.txt`
- `ghidra-memory-classification.txt`
- `ghidra-dispatcher-call-paths.txt`
- `ghidra-headless-import-cache.log`

## Architektur und Speicherbild

### Beobachtete Fakten

- Ghidra dekodiert den Start als gültige 32-Bit-ARM-Instruktionen, darunter
  `b 0x00100064`, mehrere CPSR-Moduswechsel sowie CP15-`mrc`/`mcr`.
- Absolute Stack- und Sprungziele liegen konsistent im Ladebild ab
  `0x00100000`.
- Der Raw-Loader besitzt keine Sektionstabelle.
- 694 Funktionen wurden erkannt.
- Ghidras momentane Klassifikation: 167290 Byte Code, 5617 Byte definierte
  Daten, 28785 Byte undefiniert.

### Belastbare Ableitung

32-Bit ARM Little Endian und die Loader-Basis `0x00100000` sind bestätigt.
`ARM:LE:32:v5t` ist als geeignete Analysesprache belegt; der genaue
Mikroprozessorkern und alle ARM-/Thumb-Grenzen bleiben offen.

Ghidras byteweise Klassifikation ist keine Firmware-Sektionskarte. Einzelne
Literalpools, Sprungtabellen oder bislang nicht erreichte Funktionen können
falsch beziehungsweise noch gar nicht klassifiziert sein.

## Relevante Regionen

| Adresse | Inhalt | Status |
| --- | --- | --- |
| `0x00100000` | Vektor-/Startupcode | beobachtet |
| `0x0010ccd0` | Eigentümer des Strings `LCM_Init Start!!` | beobachtet |
| `0x0010ee20` | Eigentümer des Strings `SEGGER emWin V5481110` | beobachtet |
| `0x001268d0` | Bootprozess-Callback mit Exit-/Rebootzweigen | beobachtet |
| `0x00126dfc..0x001275d3` | gerätespezifischer Befehlsdispatcher | beobachtet |
| `0x00127660` | Initialisierung von SPI, EEPROM und Konfiguration | beobachtet |
| `0x00127854` | Initialisierung einer `0x114`-Byte-Konfiguration einschließlich Boot-/JPG-Pfaden | beobachtet |
| `0x001293f8..0x00129697` | 440-Byte-Transportdispatcher | beobachtet |
| `0x001296d8..0x001297c3` | segmentierter 440-Byte-Empfänger | beobachtet |
| `0x001297e8..0x001298cf` | segmentierter 1024-Byte-Empfänger | beobachtet |
| `0x001298f8..0x00129ad3` | 440-Byte-Antwortpaketbauer | beobachtet |
| `0x00129d84..0x00129f7b` | Protokolltask und Callbackregistrierung | beobachtet |
| `0x0012a5ac` | SPI-Initialisierung und ID-Lesen | beobachtet |
| `0x0012a6d8` | SPI-Lesetransaktion | abgeleitet aus Sequenz und Datenfluss |
| `0x0012a814` | seitenweise SPI-Schreibtransaktion | abgeleitet aus Sequenz und Datenfluss |
| `0x0012c12c` | USB-Setup-Request-Dispatcher | beobachtet |
| `0x0012ced0` | USB-Ereignisdispatcher | beobachtet |

## USB-Setup- und Empfangspfade

### Beobachtete Fakten

Der direkte Setup-Pfad lautet:

```text
usb_event_dispatch_candidate (0x0012ced0)
  -> direkter Call bei 0x0012d4b4
usb_setup_request_dispatch (0x0012c12c)
  -> bRequest 0x06
  -> GET_DESCRIPTOR-Diagnose bei 0x0012c318
  -> Descriptor-Typ = High-Byte von wValue
```

Im GET_DESCRIPTOR-Zweig werden die Typen `0x01`, `0x02`, `0x03`, `0x06`,
`0x07`, `0x21` und `0x22` unterschieden. Das sind Descriptor-Typen innerhalb
des Standardrequests `bRequest=0x06`, keine Geräteprotokoll-Opcodes. Die
Antwortlänge wird jeweils gegen `wLength` begrenzt.

Der Protokolltask bei `0x00129d84` registriert unter mehreren Funktionszeigern
den Gerätedispatcher `0x00126dfc`, den Transportdispatcher `0x001293f8`, den
Initialisierungs-/Konfigurationscallback `0x00127660` und den Bootcallback
`0x001268d0`.

### Unbekannt

Der statisch aufgelöste Ghidra-Call-Graph findet keinen direkten Pfad vom
USB-Setup-Dispatcher zu Geräte-, Grafik-, Dateisystem- oder SPI-Funktionen.
Das ist wegen Callbackregistrierung und indirekter Aufrufe kein
Negativbeweis. Die konkrete Endpoint-, MI- und Interfacezuordnung dieser
Callbacks ist weiterhin nicht direkt belegt.

## Transportformat

### 440-Byte-Pfad

`segmented_command_receive_candidate` kopiert je Paket exakt `0x1b4` = 436
Bytes hinter einem 4-Byte-Steuerwort. `response_packet_builder_candidate`
erzeugt immer `0x1b8` = 440 Byte.

Das Little-Endian-Steuerwort hat statisch folgende belegte Felder:

| Bits | Bedeutung |
| --- | --- |
| `7..0` | Befehlswert |
| `30..8` im ersten Paket | vom Antwortbauer als Anzahl benötigter Pakete gesetzt |
| `30..8` in Folgepaketen | fortlaufender Segmentindex |
| `31` | Kennzeichen des ersten Pakets |

Der Antwortbauer berechnet die Paketanzahl als Aufrundung von
`(Antwortdaten + optionaler Präfix) / 436`, setzt im ersten Paket Bit 31 und
beginnt Folgepakete mit Index 1. Es ist keine transportseitige Prüfsumme in
diesen drei Routinen sichtbar.

Die exakte Übereinstimmung mit der bekannten 440-Byte-Reportgröße stützt die
Zuordnung zu dem entsprechenden HID-Interface stark. Eine direkte
MI-/Endpoint-Xref fehlt aber noch.

### 1024-Byte-Pfad

`segmented_data_receive_candidate` verwendet dasselbe Steuerwortprinzip und
kopiert `0x3fc` = 1020 Nutzbytes, insgesamt also 1024 Byte. Der maximale
Indexvergleich ist `< 200`. Ghidra fand keinen direkten Aufrufer; ein
indirekter Callback ist wahrscheinlich, aber nicht belegt. Die
Übereinstimmung mit dem bekannten 1024-Byte-Outputreport ist eine belastbare
Größenkorrelation, keine bestätigte Interfacezuordnung.

## Gerätedispatcher

### Funktionskette

```text
protocol_task_setup_candidate (0x00129d84)
  -> registriert device_command_dispatch_candidate (0x00126dfc)

transport_dispatch_candidate, Ereignis 0x38
  -> segmented_command_receive_candidate (0x001296d8)
  -> bei vollständiger Nachricht:
       Befehl 0x88 -> FUN_00128bc0
       sonst      -> indirekte Ereignis-/Callbackzustellung

device_command_dispatch_candidate
  -> akzeptiert nur Callback-Ereignis 0x35
  -> dritter Parameter ist Befehlswert
  -> response_packet_builder_candidate (0x001298f8)
```

Die indirekte Zustellung zwischen dem Transportpfad und Ereignis `0x35` ist
stark gestützt, aber wegen des noch unbenannten Eventsystems nicht als
direkter Call sichtbar.

### Beobachtete kurze Antwortbefehle

| Befehl | Antwortquelle | Länge | Bewertung |
| --- | --- | ---: | --- |
| `0x1e` | gelesenes globales Halbwort | 2 | möglicher Statuswert |
| `0x80` | globaler Puffer | 8 | mögliche Identitäts-/Statusdaten |
| `0x81` | Strukturbyte bei Offset 1 | 1 | möglicher Statuswert |
| `0x82` | globaler Puffer | 4 | möglicher Statuswert |
| `0x83` | Strukturbyte bei Offset `0x110` | 1 | möglicher Statuswert |
| `0x84` | erstes Konfigurationsbyte | 1 | möglicher Konfigurations-/Displayzustand |
| `0x85` | Konfigurationsbytes ab Offset 1 | `0x20` | mögliche Gerätekennung/Konfiguration |
| `0x87` | konstantes Halbwort `0x0051` | 2 | stärkster Versionskandidat |

Bei `0x87` ruft der Handler nur den gemeinsamen Antwortbauer auf. Für eine
einpaketige, leere Anfrage folgt aus dem Transportformat als statische
Hypothese:

```text
Request, 440 Byte:
87 01 00 80  00 ... 00

Erwartete Antwort, 440 Byte:
87 01 00 80  51 00  00 ... 00
```

Beobachtet sind der Befehlswert, das Headerverfahren, die Länge 440 und die
Antwortbytes `51 00`. Hypothetisch bleibt, dass genau dieses Paket ohne
weiteres Report-ID-/Interface-Framing vom Host zu senden wäre. Es wurde
nicht gesendet.

## Komponentenpfade

### Beobachtete Fakten

- `0x0010ccd0` initialisiert einen LCM-bezogenen Bereich und referenziert
  `LCM_Init Start!!`.
- `0x0010ee20` referenziert die emWin-Versionszeichenkette und enthält einen
  indirekten Callback.
- Gerätebefehl `0x08` stößt eine Folge von Grafik-/Systemaufrufen an und
  verändert globalen Zustand.
- Gerätebefehl `0x09` verändert Anzeigezustand, ruft mehrere Displaypfade auf
  und verwendet den Wert `0x140`; er ist nicht lesend.
- `0x0a..0x0d` führen über Objekt-/Speicherfunktionen und teils indirekte
  Lese-/Schreibcallbacks. Sie sind keine sicheren Statusabfragen.
- Der Callback `0x00127660` initialisiert SPI-Flash, lädt EEPROM und
  Konfiguration und legt bei Fehlern Defaultwerte an.
- `0x00127854` schreibt die Strings `c:\syst\boot` und
  `c:\syst\wapper.jpg` in eine Konfigurationsstruktur.
- In der Firmware wurden keine PNG-, JPEG- oder GIF-Dateisignaturen gefunden.
  Ein JPG-Dateipfad belegt noch keinen integrierten JPEG-Decoder.

### Grenze

Die begrenzte Ghidra-Call-Graph-Suche fand von den drei Dispatchern keine
vollständig statisch aufgelösten Pfade zu den String-Eigentümern von LCM,
emWin, Boot/JPG oder SPI. Indirekte Funktionszeiger verhindern hier eine
vollständige Zuordnung. Namen wie „Dateisystem“, „JPEG-Handler“ oder
„Framebuffertransfer“ werden deshalb keinem Gerätebefehl als bestätigt
zugeordnet.

## Gefährliche Pfade

| Wert/Paket | statischer Firmwarebefund | Risikobewertung |
| --- | --- | --- |
| `0x45` | im normalen Gerätedispatcher nicht behandelt; im Updater direkt im Kontext der Konfigurationslöschung | kritisch, ausgeschlossen |
| `0x86` | im normalen Dispatcher antwortorientierter Zweig, im Updater bestätigter Firmwareblocktransfer | kritisch wegen modusabhängiger Semantik |
| `0x09` | im normalen Dispatcher deutlich zustands-/displayverändernd; im Updater Completion-Flag | kritisch |
| `0x02` | im normalen Dispatcher nur leerer Antwortpfad, im Updater Abschluss/Reenumeration | kritisch wegen modusabhängiger Semantik |
| `88 01 00 80 ...` | einpaketiger Befehl `0x88`; Sonderpfad über `0x00128bc0` zu SPI-Lesen und bedingtem SPI-Schreiben an Bereich `0x21000` | kritisch |
| `0xff` mit Payload-DWORD 1 | indirekter Callback über `FUN_0012b37c` | hoch/unklar, ausgeschlossen |
| `0x1f` | verändert Modus und kann den Bootcallback `0x001268d0` anlegen | hoch, ausgeschlossen |

`FUN_0012a814` verarbeitet Daten in Blöcken bis `0x100` und setzt vor dem
Datentransfer den Wert 2 in das SPI-Datenregister; `FUN_0012a6d8` setzt
entsprechend 3 und liest Daten. Zusammen mit der SPI-ID-Initialisierung ist
die Einordnung als SPI-Write beziehungsweise SPI-Read belastbar.

## Offene Fragen

- Welches MI/HID-Interface liefert die Callbackereignisse `0x35` und `0x38`?
- Gibt es vor dem 440-Byte-Paket eine Report-ID, die der Host-API separat
  behandeln muss?
- Was bedeuten die globalen Quellen von `0x1e` und `0x80..0x85`?
- Wird der 1024-Byte-Empfänger ausschließlich für Bild-/Dateidaten genutzt?
- Wo werden Reportdeskriptor und Endpoint-Callbacks konkret verknüpft?
- Welche indirekten Grafik-/Dateifunktionen sind reine Leser und welche
  schreiben persistenten Zustand?

## Sicherheitsentscheidung

`0x87` ist der beste statische Versionskandidat. Ein kontrollierter Einzeltest
ist dennoch noch nicht freigegeben: Interface, Report-ID und vollständige
indirekte USB-/Callbackkette sind nicht belegt. Alle Boot-, Config-, SPI- und
Upgradewerte bleiben ausdrücklich ausgeschlossen.
