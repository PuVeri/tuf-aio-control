# Vorbereitung der LCD-/Bildbefehlsanalyse

Stand: 2026-09-01

## Zweck und Beleggrenze

Dieser Bericht grenzt die nächste Ghidra-Analysephase ein. Er rekonstruiert
noch kein vollständiges LCD-Protokoll und weist keinem Befehl eine fachliche
Bedeutung ohne direkten Datenflussbeleg zu.

Untersucht wurde ausschließlich die extrahierte v51-Gerätefirmware statisch
in Ghidra 12.1 (`ARM:LE:32:v5t`, Basis `0x00100000`). Das bestehende Projekt
wurde mit `-readOnly -noanalysis` geöffnet. Es gab keine Gerätekommunikation,
Emulation, Paketübertragung, Installation oder Aktivierung von
Firmware-Schreibrechten.

Belegbegriffe:

- **beobachtet**: Instruktion, Konstante, direkter Call oder Decompiler-
  Datenfluss;
- **abgeleitet**: mehrere beobachtete Befunde ergeben denselben Zusammenhang;
- **Hypothese**: sinnvolle Arbeitsfrage für die nächste Sitzung, nicht als
  Befehlsbedeutung festgelegt.

Reproduzierbarer Export:

```text
env XDG_CONFIG_HOME=/tmp/tuf-aio-ghidra-config \
  analyzeHeadless research/ghidra-projects device-firmware-v51-ghidra12-1 \
  -process device-firmware-v51.bin -readOnly -noanalysis \
  -scriptPath research/ghidra-scripts \
  -postScript ExportLcdAnalysisPrep.java /tmp/lcd-prep.txt
```

## Wichtigstes Ergebnis

Die bisher getrennten Grafikbefunde bilden jetzt drei eng benachbarte, aber
noch nicht lückenlos verbundene Teilpfade:

1. Interface 1 nimmt mit Befehlsbyte `0x08` segmentierte Großdaten auf.
2. `0x00129b2c` entnimmt Daten aus einer Queue und startet exakt dieselbe
   Hardware-/Grafikrouter-Sequenz wie Interface-0-Befehl `0x08`.
3. Der Boot-/Dateiobjektpfad ermittelt 16-Bit-Bildmaße, zentriert das Objekt
   auf 320×320 und gelangt über `0x0011acd8` ebenfalls zu diesem Router.
4. `0x0011acd8` legt intern einen Puffer mit den Parametern `200 × 1024` an;
   das Produkt ist exakt `0x32000` = 204800 Byte und stimmt mit der bereits
   beobachteten Großpuffergröße überein.

Die fehlende Beweisstelle ist die Identität und Lebensdauer der Queue-/
Pufferobjekte zwischen Endpoint-3-Callback `0x0010df9c`, Empfänger
`0x001297e8` und Konsument `0x00129b2c`. Deshalb ist „Interface 1 überträgt
Bilddaten“ weiterhin eine starke Hypothese und keine festgelegte Semantik.

## 1. Priorisierte LCD-/Bildkandidaten

| Priorität | Kandidat | Handler/Funktion | Beobachteter Beleg | Zulässige Aussage |
| ---: | --- | --- | --- | --- |
| 1 | Interface-1-`0x08` | `0x0010df9c`, `0x001297e8` | 1024-Byte-Empfang; vollständiges `0x08` geht in gesonderten Queue-/Zustandspfad | stärkster Großdatenkandidat; Inhalt offen |
| 2 | Queue-Konsument | `0x00129b2c` | dequeuet Daten und ruft dieselbe Sequenz wie Interface-0-`0x08` auf | stärkster Grafikverbraucher für empfangene Blöcke; Queue-Alias noch offen |
| 3 | Interface-0-`0x08` | `0x00126dfc`, Case bei `0x001271a4` | Reset von Grafikzustand; Payloadzeiger mit Bit 31 an Router-Operation 4; danach Operation `0x0c` | startet/konfiguriert einen zustandsändernden Grafik-/Datenpfad |
| 4 | Dateiobjekt anzeigen | `0x001279e8`, `0x0010f0d0`, `0x0010eff4`, `0x0011acd8` | liest Breite/Höhe als 16 Bit, berechnet `(320-w)/2`, `(320-h)/2`, zeichnet über gemeinsamen Grafikunterbau | belegter zentrierter Objekt-/Bilddarstellungspfad; konkretes Dateiformat offen |
| 5 | 320×320-Grafikaufbau | `0x00127e9c`, `0x0010ee20`, `0x00116774`, `0x00110f74` | emWin-Init; mehrere direkte `0x140`-Dimensionen; 320×320-Konstruktoraufruf | Display-/GUI-Fläche ist 320×320 |
| 6 | Befehl `0x09` | `0x00126dfc`, `0x0010ed1c` | 4-Byte-Wert, Grafikzustand und Rechteckpfad mit `0x140` | Vollbild-Löschen/Füllen/Aktualisieren ist eine Hypothese; Befehl bleibt ausgeschlossen |
| 7 | Modus-/Zeitbytes | `0x1a`, `0x1f`, Abfrage `0x83` in `0x00126dfc` | schreibt Konfiguration `+0x110`/`+0x111`; Boot-/Displaycallback wertet beide aus | Kandidaten für Modus/Animation, nicht semantisch benannt |
| 8 | Objekttransfer | `0x0a..0x0d`, `0x00128404..0x00128580` | Allokation, Blockschreiben, Abschluss und Objektlesen über Funktionszeiger | Datei-/Bildtransfer möglich; persistente Backends nicht ausgeschlossen |

### Befehl `0x08`: die zwei Pfade nicht vermischen

Interface 0:

```text
0x01 OUT / 440 Byte
  -> 0x0010deb8
  -> 0x001293f8
  -> 0x001296d8
  -> Event 0x35
  -> 0x00126dfc, Case 0x08 bei 0x001271a4
     -> 0x001056a4                     Grafikzustand zurücksetzen
     -> 0x001065c4(8, ...)
        -> 0x00106058                  Modus-/Formatwert prüfen/speichern
     -> 0x001065c4(0, pointer|bit31)   Zeiger registrieren
     -> 0x001065c4(0x11, ...)
     -> 0x001065c4(4, payload|bit31)   Daten-/Descriptorzeiger speichern
     -> 0x001065c4(0x0c, 0)
        -> 0x001060ec                  Hardwarezustand anstoßen
```

Interface 1:

```text
0x03 OUT / 1024 Byte
  -> Endpoint-3-Callback 0x0010df9c
  -> segmentierter Empfänger 0x001297e8
  -> vollständiges 0x08 in gesonderten Queue-/Zustandspfad
  - - - hier fehlt der abschließende Queue-/Aliasbeleg - - -
  -> Kandidat 0x00129b2c dequeuet einen Zeiger/Block
     -> 0x001056a4
     -> 0x001065c4(8, ...)
     -> 0x001065c4(0, queue_object_pointer|bit31)
     -> 0x001065c4(0x11, ...)
     -> 0x001065c4(4, dequeued_value|bit31)
     -> 0x001065c4(0x0c, 0)
```

`0x00129b2c` ist besonders stark, weil die fünf Routeraufrufe nicht nur
ähnlich, sondern in Reihenfolge und Argumentklassen praktisch deckungsgleich
mit dem Interface-0-Case sind. Der Konsument ist außerdem als Datenreferenz
im LCD-Bootprozess `0x001268d0` sichtbar. Ein statisch aufgelöster direkter
Call vom Segmentempfänger existiert erwartungsgemäß nicht, weil eine Queue
und Callback-/Taskschnittstellen dazwischenliegen.

## 2. Relevante Grafik-, LCM- und Dateipfade

### emWin, LCM und 320×320

```text
Protokolltask 0x00129d84 registriert Callback 0x00127e9c
  -> bei Initialisierungsereignis 3:
     -> 0x00109360
        -> 0x0010d07c
           -> LCM-Init 0x0010ccd0
              -> Low-Level-LCM-Schreiber 0x0010cc90
     -> emWin-Init 0x0010ee20
        -> 0x00116774
           -> zwei Viewport-/Layeraufrufe 0x00113abc mit 320×320
     -> 0x00110f74(..., 320, 320, ...)
```

`0x0010ccd0` besitzt den String `LCM_Init Start!!` und sendet eine lange
Initialisierungsfolge über `0x0010cc90`; der Wert `0x140` kommt darin vor,
ist allein dort aber noch kein Breitenbeleg. Der 320×320-Beleg entsteht erst
durch die mehrfachen Dimensionsargumente in `0x00116774` und `0x00127e9c`.

### Datei-/Objektpfad bis zum Grafikrouter

```text
Display-/Bootcallback 0x001279e8, Ereignis 0x15
  -> geladenes Objekt vorhanden
  -> 0x0010f0d0
     -> Breite/Höhe aus 16-Bit-Feldern +0x10/+0x12
  -> Zentrum: x=(320-Breite)/2, y=(320-Höhe)/2
  -> 0x0010eff4
     -> 0x0011acd8
        -> interner 200 × 1024-Pufferkandidat
        -> 0x001056a4 / 0x001065c4
```

`0x0011acd8` iteriert über Objektzeilen, verwendet die 16-Bit-Maße aus
`+0x10/+0x12`, unterscheidet interne Zwei- und Vier-Byte-Kopierpfade und
setzt in einem Pfad Alpha-Bytes auf `0xff`. Ein interner Tiefenwert `0x18`
wird auf `0x20` normalisiert. Das belegt interne 16-/32-Bit-nahe
Renderpfade, aber weder Kanalreihenfolge noch das Format der USB-Nutzdaten.

Die Defaultkonfiguration `0x00127854` ist `0x114` Byte groß und enthält
`c:\syst\boot` ab Offset `+3` sowie `c:\syst\wapper.jpg` ab Offset
`+0x7b`. Das belegt einen JPG-benannten Defaultpfad, aber weder den Decoder
noch das Format des USB-Großdatenstroms. In der Firmware wurden keine
eingebetteten PNG-, JPEG- oder GIF-Dateisignaturen und keine entsprechenden
Formatstrings außer `.jpg` gefunden.

### Koordinaten- und Blockfunktion

`0x001063d4` nimmt fünf Werte entgegen, akzeptiert nur `x1 < x2` und
`y1 < y2`, packt je zwei Koordinaten in 16-Bit-Hälften und speichert einen
fünften Datenwert. Sie wird über Router-Operation `0x0d` erreicht. Das ist ein
starker Rechteck-/Blockkandidat, aber noch kein Beleg, dass ein USB-Befehl
direkt genau dieses Format verwendet.

## 3. Bekannte Längen, Felder und Formate

| Kontext | Beobachtetes Format |
| --- | --- |
| Interface 0 OUT/IN | 440 Byte = 4 Byte Steuerwort + 436 (`0x1b4`) Byte Nutzlast |
| Interface 1 OUT | 1024 Byte = 4 Byte Steuerwort + 1020 (`0x3fc`) Byte Nutzlast |
| Steuerwort | Byte 0 Befehl; Bit 31 Erstsegment; Bits 8..30 Anzahl bzw. Segmentindex |
| 1024-Byte-Empfänger | Folgeindex `< 200`; Kopie je 1020 Byte; daraus folgt nur eine statische Obergrenze von 204000 kopierten Nutzbytes, kein freigegebenes Hostformat |
| Transportpuffer | zwei Initialisierungen mit je `0x32000` = 204800 Byte im Transportsetup |
| Renderer-Großpuffer | `0x0011acd8` ruft den Konstruktor mit `200, 0x400` auf; Produkt ebenfalls `0x32000`; API-Dimensionen und Alias zum Transportpuffer noch offen |
| Displayfläche | mehrfach direkt `0x140 × 0x140` = 320×320 |
| Objektmaße | Breite/Höhe als unsigned 16 Bit an Objektfeldern `+0x10`/`+0x12` |
| Interne Renderpfade | Tiefenwert `0x18` wird zu `0x20`; Zeilendaten werden alternativ in 2- oder 4-Byte-Einheiten kopiert; Kanalreihenfolge offen |
| Koordinatenkandidat | vier geordnete Werte, paarweise in 16-Bit-Hälften gepackt; fünfter Wert ist Daten-/Zeigerkandidat |
| Defaultkonfiguration | `0x114` Byte; Pfade bei `+3` und `+0x7b`; DWORDs `+0xf8..+0x10c`; Bytes `+0x110/+0x111` |
| Objekt-/Bootindex | Einträge von `0x10` Byte; additive Integritätsprüfung sichtbar, genaue Feldsemantik offen |
| Interface 1 IN | 16 Byte; Bedeutung weiterhin offen |

Weder ein USB-Rohpixelformat noch RGB565/RGB888, JPEG/PNG/GIF als
USB-Nutzdatenformat oder eine Kompression ist derzeit belegt. Die internen
Zwei-/Vier-Byte-Renderpfade reichen für diese Zuordnung nicht aus.

## 4. Kandidaten nach gewünschter Operation

Diese Tabelle formuliert bewusst Analysehypothesen, keine Befehlsnamen:

| Gesuchte Operation | Stärkste nächste Kandidaten | Belegstatus |
| --- | --- | --- |
| Bild anzeigen | Interface-0-`0x08`; Dateiobjektpfad `0x001279e8 -> 0x0010eff4` | Grafikstart belegt, Bildsemantik für `0x08` offen |
| Bilddaten übertragen | Interface-1-`0x08` plus `0x001297e8` und `0x00129b2c`; alternativ `0x0a..0x0d` | Großdaten und Blocktransfer belegt, Inhalt/Backend offen |
| Displaymodus wählen | `0x11`, `0x1a`, `0x1f`; Konfigurationsbytes `+1`, `+0x110`, `+0x111` | Zustandsänderung belegt, Moduswerte offen |
| Animation starten/stoppen | `0x1f` und Callback `0x001268d0`; periodischer Zweig `0x001279e8` mit `+0x110/+0x111` | Callback-/Zeitverhalten belegt, Animation nur Hypothese |
| Display löschen/aktualisieren | `0x09 -> 0x0010ed1c`; Router-Operation `0x0c -> 0x001060ec` | Vollflächen-/Updatepfade belegt, konkrete Wirkung offen |

## 5. Gefährliche Pfade: von jeder praktischen Prüfung ausgeschlossen

- **`0x88` / kritisch:** `0x00128bc0 -> 0x0012a6d8` liest SPI bei
  `0x21000` und kann über `0x0012a814` schreiben.
- **`0x0a..0x0d` / hoch bis kritisch:** Blockallokation, indirekte
  Schreibcallbacks und Abschlussoperationen; das persistente Backend ist
  nicht ausgeschlossen. Nur statisch weiterverfolgen.
- **`0x1b`, `0x1c`, `0xfe` / hoch:** erreichen den persistenznahen
  Konfigurationsschreiber `0x00126814`.
- **`0x1f` / hoch:** verändert `+0x111` und kann den Bootcallback
  `0x001268d0` anlegen.
- **`0x09` / kritisch:** verändert im Normaldispatcher Displayzustand und
  ist im Updater zusätzlich Completion-Flag.
- **`0x86` / kritisch:** Firmwareblocktransfer im Updater.
- **`0x02` / kritisch:** Updater-Abschluss/Reenumeration.
- **`0x45` / kritisch:** Konfigurationslöschung im Updater.
- **`0xff` mit DWORD 1 / hoch:** unaufgelöster indirekter Callback.

Keine dieser Routen ist Kandidat für Gerätekommunikation. Auch die übrigen
Kandidaten dieses Berichts sind keine Sendefreigabe.

## 6. Konkrete nächste Ghidra-Fragen

1. Endpoint-3-Callback `0x0010df9c` als Funktion definieren/dekompilieren und
   alle Literalpoolwerte der `0x08`-Queue benennen; dabei den Firmwareblock
   weiter nicht schreibbar lassen.
2. Sind Queueobjekt und Puffer, die `0x0010df9c` füllt, bytegenau dieselben,
   die `0x00129b2c` über `0x0012a390` konsumiert? Alle Konstruktoren,
   Produzenten und Freigaben gegenüberstellen.
3. Welcher Wert wird in `local_20` von `0x00129b2c` zurückgegeben, und ist er
   Länge, Pufferadresse, Descriptoradresse oder Offset?
4. Welche Struktur erwartet `0x001065c4` bei Operationen `0`, `4`, `8`,
   `0x0c`, `0x0d` und `0x11`? Besonders die Felder `+0x7c`, `+0xa0` und der
   Statusblock hinter `DAT_00106590` typisieren.
5. `0x0011acd8` vollständig zerlegen: Welche Formate/Marker wählt die Funktion
   vor den Aufrufen des Grafikrouters, und hängen sie mit JPEG, Rohpixeln oder
   einem proprietären Descriptor zusammen?
6. In `0x0010f0d0` den Erzeuger der Objektfelder `+0x10/+0x12` verfolgen und
   feststellen, ob eine Formatprüfung vor der Dimensionsextraktion liegt.
7. Die 16-Byte-Einträge des Boot-/Objektindex in `0x001268d0` typisieren:
   Offset, Länge, Breite/Höhe, Prüfsumme und Folgerahmen voneinander trennen.
8. Für `0x1a` (`+0x110`) und `0x1f` (`+0x111`) sämtliche Leser sammeln und
   Zustandsautomaten zeichnen, bevor Begriffe wie Modus, Loop oder Animation
   vergeben werden.
9. `0x09 -> 0x0010ed1c -> 0x00115704` prüfen: ist `0x00115704` ein
   FillRect-, Invalidate-, Flush- oder anderer Rechteckpfad? Farbreihenfolge
   des 4-Byte-Payloads nur aus Operationen, nicht aus Vermutung ableiten.
10. Für `0x0a..0x0d` zuerst die indirekten Backends auf SPI/EEPROM/Dateisystem
    klassifizieren. Diese Befehle bleiben unabhängig vom Ergebnis gefährlich.

## Kurzpriorität für die nächste Sitzung

1. Queue-Alias `0x0010df9c -> 0x001297e8 -> 0x00129b2c` schließen.
2. `0x0011acd8` und `0x001065c4` als gemeinsame Format-/Grafikgrenze
   typisieren.
3. Objektmaße und Zentrierpfad `0x0010f0d0/0x0010eff4` bis zum Dateileser
   zurückverfolgen.
4. `0x1a/+0x110` und `0x1f/+0x111` als Zustandsautomat untersuchen.
5. SPI-, Updater- und persistente Objektpfade ausschließlich statisch halten.
