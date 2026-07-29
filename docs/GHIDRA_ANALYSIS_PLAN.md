# Statische Ghidra-Analyse der Gerätefirmware

Stand: 2026-07-29

## Status und Sicherheitsrahmen

Ghidra 12.1 PUBLIC ist unter
`/home/l/HeartdriveLab/tools/ghidra/ghidra_12.1_PUBLIC` vorhanden.
`analyzeHeadless` verwendet das portable Temurin JDK 21.0.12+8. Die
Ghidra-Metadaten verlangen mindestens Java 21.

Die Firmware wurde ausschließlich als Datenobjekt importiert, disassembliert
und dekompiliert. Es gab keine Emulation und keine Ausführung von Firmwarecode.
Kein USB-/HID-Gerät wurde geöffnet und es wurden keine Daten an die AIO
gesendet.

## Eingabe und Ladeparameter

| Parameter | Verwendeter Wert | Status |
| --- | --- | --- |
| Eingabe | `research/extracted/device-firmware-v51-static/device-firmware-v51.bin` | beobachtet |
| SHA-256 | `c4679ec340fc5edd3dea960ee027281cf6bd81cbbf347afb40e0d0b4f40aeb9f` | beobachtet |
| Länge | `0x313dc` = 201692 Byte | beobachtet |
| Loader | Raw Binary | verwendet |
| Sprache | `ARM:LE:32:v5t` | verwendet; ARM/LE/32 bestätigt, genauer Kern offen |
| Compiler Spec | `default` | verwendet |
| Loader-Basis | `0x00100000` | verwendet und durch gültige Vektor-/Codereferenzen gestützt |
| geladener Block | `0x00100000..0x001313db` | beobachtet |
| Blockrechte nach Vorbereitung | Read, nicht Write, Execute | beobachtet |
| Analysezeitlimit | 600 Sekunden pro Datei | verwendet |
| maximale CPU-Zahl | 2 | verwendet |

Der Raw-Loader meldet die Programmeigenschaft `IMAGE_BASE=0`, obwohl sein
einziger Block bei `0x00100000` liegt. Für Adressen in den Berichten ist die
Block-/Loader-Basis maßgeblich. Das Execute-Flag des gesamten Raw-Blocks ist
eine Loader-/Analysekonfiguration und kein Beleg, dass jedes Byte Code ist.

## Projekt und Reproduzierbarkeit

Das getrennte Ghidra-Projekt liegt unter:

```text
research/ghidra-projects/device-firmware-v51-ghidra12-1
```

Die Originalkopie der Firmware wurde nicht verändert. Erstimport und
Standardanalyse wurden einmal in diesem neuen Projekt gespeichert. Danach
wurde der Block mit
`research/ghidra-scripts/PrepareFirmwareFunctions.java` nicht schreibbar
markiert, die von der Standardanalyse übersehene Funktion bei `0x001297e8`
angelegt und ausschließlich evidenzbasierte `*_candidate`-Namen vergeben.

Alle späteren Exporte öffneten das Projekt mit `-readOnly -noanalysis`.
Ghidra-Cache, temporäre Dateien und Einstellungen wurden jeweils in neue
Verzeichnisse unter `/tmp` umgeleitet. Die Exportscripte verweigern das
Überschreiben vorhandener Ausgaben:

- `ExportFirmwareAnalysis.java`
- `ExportDispatcherCallPaths.java`
- `ExportMemoryClassification.java`

Der maßgebliche, erweiterte Export ist
`research/reports/ghidra-static-export-v4.txt`. Frühere Exporte bleiben als
unveränderte Zwischenstände erhalten.

## Tatsächlich ausgeführte Analysatoren

Der Headless-Standardlauf protokolliert unter anderem:

- ARM Constant Reference Analyzer
- ASCII Strings
- Create Address Tables
- Create Function und Function Start Search
- Data Reference und Reference
- Decompiler Switch Analysis
- Disassemble und Disassemble Entry Points
- Embedded Media
- Stack und Subroutine References

Ghidra erkannte 694 Funktionen. Seine aktuelle byteweise Einordnung umfasst
167290 Byte Code, 5617 Byte definierte Daten und 28785 undefinierte Byte. Das
ist eine Analyseklassifikation, keine bestätigte Sektionstabelle.

## Bestätigte statische Anker

| Adresse | Arbeitsname | Befund |
| --- | --- | --- |
| `0x00126dfc` | `device_command_dispatch_candidate` | akzeptiert Callback-Ereignis `0x35`; eigentlicher Befehl ist sein dritter Parameter |
| `0x001293f8` | `transport_dispatch_candidate` | initialisiert und verarbeitet den 440-Byte-Transport |
| `0x001296d8` | `segmented_command_receive_candidate` | zerlegt 440 Byte in 4 Byte Steuerwort plus `0x1b4` Nutzbytes |
| `0x001297e8` | `segmented_data_receive_candidate` | zerlegt 1024 Byte in 4 Byte Steuerwort plus `0x3fc` Nutzbytes |
| `0x001298f8` | `response_packet_builder_candidate` | baut segmentierte 440-Byte-Antworten |
| `0x00129d84` | `protocol_task_setup_candidate` | registriert Geräte- und Transportdispatcher als Callbacks |
| `0x0012c12c` | `usb_setup_request_dispatch` | Standard-USB-Setup-Requests und Deskriptoren |
| `0x0012ced0` | `usb_event_dispatch_candidate` | ruft bei Setup-Ereignissen direkt `0x0012c12c` auf |

Die Namen mit Suffix `_candidate` beschreiben nur den statisch sichtbaren
Zweck; sie sind keine ursprünglichen Symbole.

## Nächste sichere Analyseschritte

1. Indirekte Callback-Ziele des Protokolltasks typisieren und den
   Endpoint-/Interfacekontext der Ereignisse `0x35` und `0x38` belegen.
2. Reportdeskriptorzeiger im USB-Zustand verfolgen und damit die
   440-/1024-Byte-Pfade direkt den Interface-Nummern zuordnen.
3. Globale Quellen der Antwortbefehle `0x1e`, `0x80..0x85` benennen.
4. Für Grafik- und Dateifunktionen indirekte Callbacks manuell auflösen.
5. Erst danach neu bewerten, ob ein aktiver Einzeltest vertretbar wäre.

Bis diese Punkte geklärt sind, bleibt selbst der kurze Kandidat `0x87` ein
statischer Kandidat und keine Freigabe zum Senden.
