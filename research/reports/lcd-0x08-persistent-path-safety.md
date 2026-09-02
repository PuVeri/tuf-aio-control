# Statischer Safety-Crosscheck des LCD-Befehls 0x08

Stand: 2026-09-02

## Zweck und Grenze

Dieser Bericht beantwortet ausschließlich, ob der aus ASUS InfoHub 1.0.0.15
rekonstruierte Interface-1-Bildtransfer im analysierten v51-Gerätepfad einen
persistenten oder updatebezogenen Pfad erreichen kann. Untersucht wurden nur
bereits vorhandene Binär-, Ghidra- und Berichtartefakte. Das vorhandene
v51-Ghidra-Projekt wurde read-only und ohne erneute Analyse geöffnet. Es gab
keine Gerätekommunikation, keine HID-Zugriffe, keine Firmwareausführung und
keinen Testcode.

Der Nachweis gilt für die analysierte normale v51-Anwendungsfirmware. Eine
v49-Binärdatei liegt nicht vor; Aussagen zu v49 werden deshalb ausdrücklich
als Versionsrestrisiko abgegrenzt.

## 1. Hostformat gegen v51-Empfänger

| Merkmal | ASUS InfoHub 1.0.0.15 | v51-Gerätepfad | Bewertung |
| --- | --- | --- | --- |
| Reportgröße auf dem Draht | 1024 Byte | Endpoint-Callback `0x0010df9c` armiert und übergibt `0x400` Byte | exakt kompatibel |
| Aufteilung | 4 Byte Controlword + 1020 Byte Payload | `0x001297e8` liest ein DWORD und kopiert ab Byte 4 stets `0x3fc` Byte | exakt kompatibel |
| Segmentzahl | `N = ceil(L / 1020)` | Erstsegment speichert `N`; Abschluss bei `N <= letzter_index + 1` | exakt kompatibel für normales `1 <= N <= 200` |
| Erstsegment | `08 N 00 80` | Byte 0 ist Befehl `0x08`, Bit 31 ist First, Feld Bits 8..30 ist `N` | exakt kompatibel |
| Folgesegmente | `08 i 00 00`, `i = 1..N-1` | akzeptiert den aktuellen Index als Duplikat oder genau den nächsten; normaler Fortschritt ist `1..N-1` | exakt kompatibel |
| Payloadkopie | immer volle 1020 Byte | Erst- und Folgesegment kopieren immer `0x3fc` Byte | exakt kompatibel |
| letzter Block | JPEG-Rest plus ausschließlich `00` bis 1020 Byte | Firmware übernimmt alle 1020 Byte unverändert; kein Restlängenfeld und kein EOI-Scan im ARM-USB-Pfad | transportseitig exakt kompatibel; Hardware-Suffixakzeptanz bleibt nur stark gestützt |
| Verbrauch | neu encodiertes 320×320-JPEG | Queuepayload wird als Quelle des Modus `0x6021` an den MMIO-Grafikblock gegeben; Hardware-JPEG-Decoder ist durch den Referenzpfad stark typisiert | kompatibel |

InfoHub stellt unter Windows zusätzlich ein Report-ID-Nullbyte voran. Dieses
Byte gehört zum 1025-Byte-Windows-API-Puffer, nicht zu den 1024 Drahtbytes und
gelangt daher nicht in das Geräte-Controlword.

Die Kompatibilitätsaussage ist bewusst auf `N <= 200` begrenzt. v51 kopiert
Folgesegmente nur bei Index `< 200`; sein normaler rekonstruierter
Assemblierungspuffer umfasst 200 Payloadblöcke. InfoHub schreibt nur das
niedrige Byte von `N` und besitzt selbst keine entsprechende Obergrenzenprüfung.
Vor einem späteren Review muss deshalb für das konkrete, bereits erzeugte
JPEG statisch `1 <= ceil(L/1020) <= 200` feststehen. Eine Verletzung dieser
Bedingung wäre ein Ablehnungs-/Fehlassemblierungsrisiko, kein belegter
Persistenzpfad.

## 2. Erreichbarer v51-0x08-Pfad

Der befehlsrelevante direkte und verzögert über Queue/Callback fortgesetzte
Pfad ist:

```text
Interface-1 OUT, 1024 Byte
  -> 0x0010df9c
  -> 0x001297e8              Controlword, 1020-Byte-Kopien
  -> Queue 0x003bb430         N*1020-Byte-Kopie
  -> 0x00129b2c              periodischer Queueconsumer
       -> Interface-1 IN 08 81
       -> 0x001056a4          flüchtigen Grafikzustand zurücksetzen
       -> 0x001065c4          Modus 0x6021, Ziel, Callback, Quelle
            -> 0x001060ec     Hardwaredecoder über MMIO starten
       -> 0x00105e60          Decoder-active abfragen
       -> 0x0012a310          Queueeintrag freigeben
  -> 0x00129cf0              späterer Displaycallback
       -> 0x00109394          Framebufferregister b1002050 schreiben
```

Zusätzlich kopiert `0x0010df9c` nach einem formal vollständigen `0x08` den
bereits vorhandenen Konfigurationswert `config+0x108` nach dem flüchtigen
Countdown bei `0x001315c4`. Das ist eine RAM-Zustandsänderung und kein Write
zurück in die Konfiguration. Der Consumer verändert außerdem Queue-, Busy-,
Ring- und Decoderzustände in RAM. Abhängig vom schon vorhandenen Modus kann er
den bekannten gemeinsamen Peripherieprolog `0x0010dd58` aufrufen; dessen
bereits geprüfter direkter Unterbaum enthält Peripherie-/Rechenoperationen,
aber keinen SPI-, Flash- oder persistenten Konfigurationswriter.

Der Grafikrouter erhält die Quelladresse aus dem intern allokierten
Queueeintrag und die Zieladresse aus dem vorinitialisierten Framebuffer-Ring.
Weder Quell- noch Zieladresse werden aus JPEG-Inhaltsbytes oder aus den
ungenutzten Controlwordbits gebildet. Der installierte Completion-Callback
`0x00115110` besteht nur aus `bx lr`. Die Decoderabschlussbehandlung führt
zur Queuefreigabe und später zum Framebufferwechsel, nicht zu einem
persistenten Commit.

## 3. Persistenz- und Update-Reachability

Die Spalte „Klassifikation“ beschreibt zuerst die Erreichbarkeit **ab dem
Interface-1-`0x08`-Dispatcher**. „Nur über andere Befehle“ bedeutet, dass die
Funktionalität im Image existiert, aber keine Kontrollflusskante vom
untersuchten `0x08`-Pfad dorthin belegt ist.

| Frage | Klassifikation ab `0x08` | Statischer v51-Befund |
| --- | --- | --- |
| SPI-Write erreichbar? | **nicht erreichbar**; nur über andere Befehle | Der bekannte seitenweise SPI-Writer `0x0012a814` liegt hinter `0x88 -> 0x00128bc0`. Weder Producer, Queueconsumer, Grafikrouter noch Decoder-/Displayabschluss rufen `0x00128bc0` oder `0x0012a814` auf. |
| Flash-Write erreichbar? | **nicht erreichbar**; nur über andere Befehle/Backends | Der belegte SPI-Flash-Writer `0x0012a814` ist vom `0x08`-Pfad getrennt. Die persistenzverdächtigen Objektbefehle `0x0a..0x0d` besitzen eigene indirekte Schreib-/Abschlussrouten; ihr Backend bleibt teilweise unbekannt, sie werden durch Interface-1-`0x08` aber nicht dispatcht. |
| Firmwareupdate erreichbar? | **nicht erreichbar**; nur über andere Befehle und Updaterzustand | Firmwareblocktransfer `0x86`, Updaterabschluss `0x02` und Konfigurationslöschung `0x45` gehören zu getrennten Updatersemantiken. Das Bild-`0x08` gelangt ausschließlich in die normale JPEG-Queue und den Grafikblock. |
| Bootloader/Reset erreichbar? | **nicht erreichbar** vom untersuchten Pfad | `0x08` startet beziehungsweise setzt nur den Grafik-/Decoderzustand zurück. Das ist kein CPU-, USB- oder Bootreset. Reenumeration/Updaterabschluss ist nur über den getrennten Updaterbefehl `0x02` bekannt; eine allgemeine Bootloader-Einstiegssemantik bleibt außerhalb dieses Pfads unbekannt. |
| Persistente Konfigurationsänderung erreichbar? | **nicht erreichbar**; nur über andere Befehle | `0x08` liest `config+0x108` und schreibt dessen Wert nur in RAM. Die bekannten Befehle `0x1b`, `0x1c` und `0xfe` erreichen dagegen den persistenznahen Konfigurationswriter `0x00126814`; `0x45` löscht Konfiguration im Updater. Keine dieser Kante gehört zum Interface-1-`0x08`-Pfad. |

Damit lautet das enge v51-Ergebnis: **Keiner der fünf persistenten,
firmwareaktualisierenden oder bootbezogenen Zielpfade ist vom exakt
rekonstruierten Interface-1-`0x08`-Bildpfad erreichbar.** Direkt erreichbar
sind ausschließlich flüchtige RAM-Zustände, USB-IN-Ausgabe, Decoder-/Display-
MMIO und Framebufferspeicher.

Diese Aussage bedeutet nicht, dass das Image generell keine gefährlichen
Befehle besitzt. Insbesondere `0x88`, `0x0a..0x0d`, `0x1b`, `0x1c`, `0xfe`
sowie die Updaterbefehle bleiben getrennte, von einem praktischen Bildtest
auszuschließende Routen.

## 4. Enges v49-Risiko

Für v49 ist mangels Binärdatei die Persistenz-Reachability **unbekannt**. Damit
ein exakt von ASUS InfoHub erzeugter, normal großer Transfer auf v49
gefährlich statt lediglich inkompatibel oder fehlerhaft wäre, müsste v49
mindestens eine konkrete strukturelle Abweichung von v51 besitzen:

1. **Dispatcher-Alias:** Interface 1 mit Befehlsbyte `0x08` müsste in v49 auf
   einen SPI-/Flash-, Updater-, Boot-/Reset- oder persistenten
   Konfigurationshandler zeigen, statt auf die JPEG-Queue.
2. **Neue persistente Kante im JPEG-Unterbaum:** Der v49-Queueconsumer,
   Decoderabschluss oder Fehlerpfad müsste zusätzlich einen persistenten
   Writer beziehungsweise Updater-/Bootpfad aufrufen. Ein anderer JPEG-
   Decoder, anderes ACK oder fehlender Displaycommit genügt dafür nicht.
3. **Gefährliche Speicherfehlerabweichung:** Der v49-Assembler müsste bei
   einem im ASUS-Normalformat liegenden `N` beziehungsweise bei seiner vollen
   1020-Byte-Kopie eine gegenüber v51 fehlende oder kleinere Puffergrenze so
   überschreiben, dass daraus kontrollfluss- oder adresswirksam ein
   persistenter MMIO/SPI-/Bootpfad erreichbar wird. Eine reine Verwerfung,
   falsche Segmentzählung, Decoderstörung oder flüchtige Speicherbeschädigung
   ohne solche Folgekante wäre nur fehlerhaft, nicht als persistenter Write
   belegt.
4. **Hostgesteuerte Zieladressierung:** v49 müsste entgegen v51 Quell- oder
   Zieladressen für DMA/Decoder aus JPEG- oder Controlwordbytes übernehmen
   und damit persistenten Adressraum adressieren können. In v51 stammen diese
   Adressen ausschließlich aus Queueallokation und Framebuffer-Ring.

Normale Versionsabweichungen wie eine andere Indexprüfung, Ablehnung des
Nullpaddings, ein anderes unterstütztes JPEG-Profil, fehlendes `08 81`, ein
Timeout, Decoderfehler oder ein ausbleibender sichtbarer Commit würden den
ASUS-Transfer scheitern lassen oder nur flüchtigen Anzeigezustand betreffen.
Sie machen ihn für sich genommen nicht persistent gefährlich.

Das verbleibende v49-Risiko ist daher nicht ein im v51-Pfad sichtbarer
gefährlicher Seiteneffekt, sondern die unbelegte Möglichkeit einer der vier
oben beschriebenen strukturellen Änderungen. Sie kann ohne v49-Firmware oder
gleichwertige passive Evidenz nicht von „unbekannt“ auf „nein“ herabgestuft
werden.

## 5. Readiness-Folge

**GO für einen vollständigen Readiness-Review nach Reset: ja.** Das ist nur
die Freigabe für den nächsten Review, keine Freigabe für Gerätekommunikation
oder einen HID-Write. Der Review muss mindestens das konkrete JPEG statisch
fixieren, dessen `L` und `N` mit `1 <= N <= 200` prüfen, exakt einen
ASUS-identischen Transfer ohne andere Befehle und ohne Retry abgrenzen und das
weiterhin unbekannte v49-Risiko ausdrücklich als eigene Freigabeentscheidung
behandeln.

