# Untersuchung zu Firmware v49 und `bcdDevice 0.49`

Stand: 2026-09-01

## Kurzfazit

- Es wurde **keine Firmware-v49-Datei** gefunden.
- Das reale Gerät liefert inzwischen empirisch sowohl `bcdDevice 0.49` als
  auch den `0x87`-Versionswert `0x0049`. Nicht bestätigt ist weiterhin die
  bytegenaue Identität mit einer offiziellen ASUS-v49-Firmwaredatei.
- Ein statischer Vergleich des `0x87`-Handlers zwischen v49 und v51 ist ohne
  v49-Binärdatei nicht möglich. Für v51 ist die Antwort
  `87 01 00 80 51 00 | 434 × 00` belegt.
- Live-Test 02 lieferte vollständig
  `87 01 00 80 49 00 | 434 × 00`. Die Bytes des ersten Tests bleiben dennoch
  verloren und werden dadurch nicht rückwirkend rekonstruiert.

Während dieser Untersuchung wurde keine ASUS-Datei ausgeführt, nichts an ein
USB-/HID-Gerät gesendet, keine Firmware übertragen, keine Schreibberechtigung
geändert und kein Paket installiert.

## Untersuchungsfrage und Bewertungsmaßstab

Gesucht wurden zunächst ausschließlich offizielle ASUS-Belege für Firmware
v49, ältere Downloads, eine Releasehistorie und eine Zuordnung zwischen dem
USB-Feld `bcdDevice` und der von ASUS angezeigten Firmwareversion. Erst nach
dem negativen ASUS-Befund wurden öffentliche Archive, GitHub sowie Linux- und
Hardwarequellen durchsucht.

Die Ergebnisse werden in drei Klassen getrennt:

- **Bestätigt:** direkt aus einer vorhandenen Binärdatei, einem gesicherten
  Deskriptor oder einer offiziellen Quelle belegt.
- **Abgeleitet:** mehrere Fakten stützen die Aussage, aber ein direktes
  Bindeglied fehlt.
- **Unbekannt:** mit den vorhandenen Daten nicht entscheidbar.

## 1. Offizielle ASUS-Quellen

### Aktueller Produkt-Support

Die offizielle
[BIOS-/Firmware-Seite des Produkts](https://www.asus.com/motherboards-components/cooling/tuf-gaming/tuf-gaming-lc-iii-360-argb-lcd/helpdesk_bios?model2Name=TUF-Gaming-LC-III-360-ARGB-LCD)
führte am 2026-09-01 genau einen Firmwaredownload:

| Feld | Offizieller Wert |
| --- | --- |
| Version | `51` |
| Datum | `2025/07/10` |
| Größe | `1.27 MB` |
| Datei | `ASUS_InfoHub_Firmware_TUF_GAMING_LC_III_360_ARGB_LCD_v51.rar` |
| SHA-256 | `267b1477374d28fca01be92b2ff11748591560d30c1a1392bf9d06493a43bfd8` |
| Beschreibung/Versionshinweise | leer |

Die von der Seite verwendete offizielle ASUS-API
`/support/webapi/ProductV2/GetPDBIOS` meldete ebenfalls `Count: 1` und nur
dieselbe v51-Datei. Sie lieferte weder ältere Einträge noch Release Notes.
Das bestätigt den aktuellen Katalogzustand, nicht die historische
Nichtexistenz älterer Downloads.

Reproduzierbare offizielle Endpunkte der Abfrage:

```text
https://www.asus.com/support/webapi/ProductV2/GetPDBIOS?website=global&model=tuf-gaming-lc-iii-360-argb-lcd&pdhashedid=vuxiprtwlnip2fc9&pdid=34029&cpu=&siteID=www&sitelang=
https://dlcdnets.asus.com/pub/ASUS/Accessory/Cooling/TUF_GAMING_LC_III_360_ARGB_LCD/ASUS_InfoHub_Firmware_TUF_GAMING_LC_III_360_ARGB_LCD_v51.rar
```

### Offizielle InfoHub-FAQ

Die offizielle
[ASUS-InfoHub-FAQ](https://rog.asus.com.cn/support/faq/1055446/)
erklärt getrennte Felder für Anwendungs- und Firmwareversion. Ihre Abbildung
`20250701144727892_13.png` zeigt für das Zielmodell sichtbar
`Firmware version 50`. Damit ist offiziell belegt, dass ASUS vor oder während
der Veröffentlichung der FAQ einen Stand 50 in InfoHub anzeigte. Die FAQ
stellt jedoch keine v50-Datei bereit und ordnet diesen Wert keinem
`bcdDevice` zu.

Dieselbe FAQ beschreibt InfoHub primär als Werkzeug für das AIO-Display und
verweist die Beleuchtungssteuerung an Armoury Crate. Für dieses Linux-Projekt
gilt die entsprechende klare Abgrenzung: **OpenRGB bleibt für sämtliche
RGB-Beleuchtung zuständig; `tuf-aio-control` betrifft ausschließlich das
LCD.**

### Direkte Dateinamen und Archive

Am 2026-09-01 wurden die aus dem offiziellen v51-Namensschema naheliegenden
ASUS-CDN-Pfade für v49 geprüft, unter anderem die Varianten mit `v49`, `V49`
und dem verkürzten Namensbestandteil `TUF_GAMING_v49`. Sie antworteten mit
HTTP 404. Auch ein entsprechend gebildeter v50-Pfad antwortete mit 404.

```text
https://dlcdnets.asus.com/pub/ASUS/Accessory/Cooling/TUF_GAMING_LC_III_360_ARGB_LCD/ASUS_InfoHub_Firmware_TUF_GAMING_LC_III_360_ARGB_LCD_v49.rar
https://dlcdnets.asus.com/pub/ASUS/Accessory/Cooling/TUF_GAMING_LC_III_360_ARGB_LCD/ASUS_InfoHub_Firmware_TUF_GAMING_LC_III_360_ARGB_LCD_V49.rar
https://dlcdnets.asus.com/pub/ASUS/Accessory/Cooling/TUF_GAMING_LC_III_360_ARGB_LCD/ASUS_InfoHub_Firmware_TUF_GAMING_v49.rar
https://dlcdnets.asus.com/pub/ASUS/Accessory/Cooling/TUF_GAMING_LC_III_360_ARGB_LCD/ASUS_InfoHub_Firmware_TUF_GAMING_LC_III_360_ARGB_LCD_v50.rar
```

Zusätzlich ergaben Abfragen des Internet Archive CDX-Index für den ASUS-CDN-
Produktordner und die Supportseite keine archivierten Treffer. Ein heutiges
404 und ein leerer Archivindex beweisen nicht, dass eine Datei nie öffentlich
existierte.

### Ergebnis der offiziellen Suche

- Kein offizieller v49-Download gefunden.
- Keine ASUS-Releasehistorie oder Versionshinweise gefunden.
- Keine offizielle Zuordnung `bcdDevice 0.49` → Firmware 49 gefunden.
- Offiziell bestätigt sind der aktuelle v51-Download und eine ältere
  InfoHub-Anzeige `Firmware version 50`.

## 2. Vertrauenswürdige öffentliche Quellen

Nach dem negativen offiziellen Befund wurden Suchen mit Produktname, USB-ID
`0b05:1c7b`, exakten und abgeleiteten Firmwaredateinamen, Updaterdateiname,
`bcdDevice 0.49`, `firmware 49` und `version 49` durchgeführt.

### GitHub, Linux-/Hardwareprojekte und Firmwarearchive

Es wurde kein Repository, Linux-Treiber, Hardwareprojekt oder öffentliches
Firmwarearchiv gefunden, das eine v49-Datei, deren Prüfsumme oder eine
nachprüfbare Zuordnung von `bcdDevice` zur InfoHub-Firmwareversion enthält.
Insbesondere ergaben die Suchen nach der USB-ID und den exakten ASUS-
Dateinamen keinen passenden Quellcode- oder Binärfund.

### Öffentlicher Nutzerbericht

Ein
[Bahamut-Forenbeitrag zum exakten AIO-Modell](https://forum.gamer.com.tw/C.php?bsn=60030&snA=677317)
vom 2025-11-16 sagt, vor einem Update sei eine „Softwareversion 49“ angezeigt
worden. Die beigefügte InfoHub-Abbildung zeigt zwar getrennte Zeilen für App-
und Firmwareversion, das Firmwarefeld ist darauf jedoch leer; die Zahl 49 ist
nicht im Bild sichtbar. Der Beitrag ist deshalb nur ein glaubwürdiges, aber
anekdotisches Indiz. Er belegt weder eine Firmwaredatei noch `bcdDevice 0.49`.

Eine
[Hardwarebesprechung bei Bug.hr](https://www.bug.hr/recenzije/asus-tuf-gaming-lc-iii-360-argb-lcd-zlatna-sredina-53729)
vom 2026-01-31 bestätigt unabhängig, dass InfoHub die aktuelle AIO-
Firmwareversion anzeigt und das Update damals manuell über die ASUS-Seite
erfolgte. Sie nennt keine Versionsnummer und schließt die Zuordnungslücke
daher nicht.

Es wurde keine Drittanbieter-Firmware heruntergeladen oder ausgeführt.

## 3. Statische Prüfung vorhandener v51-Daten

### Unveränderte Ausgangsdaten

| Artefakt | SHA-256 |
| --- | --- |
| Offizielles ASUS-v51-RAR | `267b1477374d28fca01be92b2ff11748591560d30c1a1392bf9d06493a43bfd8` |
| Statisch extrahierter Windows-Updater | `037b581f2bd5bc95db7db1a6f68d25d7ac2c19afe9fa09888851f0d6e448fb65` |
| Statisch extrahierte ARM-Nutzlast | `c4679ec340fc5edd3dea960ee027281cf6bd81cbbf347afb40e0d0b4f40aeb9f` |

### Was v51 direkt belegt

1. Der `0x87`-Case bei `0x00127588..0x001275c8` lädt fest `0x51` und baut
   eine Zwei-Byte-Antwort. Der resultierende 440-Byte-Report lautet exakt
   `87 01 00 80 51 00 | 434 × 00`.
2. Die ARM-Nutzlast enthält am Dateioffset `0x2eba0` eine headerartige Region
   mit einem 32-Bit-Wert `0x51`, unmittelbar gefolgt von `0x0b05` und
   `0x1c7b`. Das korreliert Version und Zielgerät, doch die genaue
   Feldsemantik dieser internen Struktur ist nicht abschließend belegt.
3. Der Windows-Updater ruft `HidD_GetAttributes` auf. Er initialisiert bei
   `0x40bdbd` eine 12 Byte große `HIDD_ATTRIBUTES`-Struktur, ruft die API bei
   `0x40bdec` auf und übernimmt das WORD an Strukturoffset `+8` bei
   `0x40bdf2` beziehungsweise erneut bei `0x40be4c` in seine interne
   Gerätebeschreibung. Laut
   [Microsoft-Dokumentation zu `HIDD_ATTRIBUTES`](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidsdi/ns-hidsdi-_hidd_attributes)
   ist dieses Feld `VersionNumber`, die Hersteller-Revision des HID-Geräts.
4. Im untersuchten Auswahl- und Upgradepfad wurde keine Bedingung gefunden,
   die diesen gespeicherten `VersionNumber`-Wert mit `0x49`, `0x51` oder dem
   eingebetteten Firmwarewert vergleicht. Die Zielzeile nach der Nutzlast
   enthält für ASUS `0x0b05, 0x1c7b, 0, -1`; sie ist keine belegte
   Firmwareversionszuordnung.

Das USB-Feld `bcdDevice` ist normativ nur eine vom Gerätehersteller
zugewiesene, BCD-codierte Geräte-Release-Nummer; daraus folgt nicht allgemein,
dass es mit einer separaten Firmwareversionsanzeige identisch sein muss. Siehe
[USB-IF, USB 2.0 Specification](https://www.usb.org/document-library/usb-20-specification)
und
[Microsoft, USB Device Descriptors](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/usb-device-descriptors).

### Beweiswert für `bcdDevice 0.49 = Firmware 49`

| Aussage | Bewertung | Begründung |
| --- | --- | --- |
| Das reale Gerät meldete `bcdDevice 0.49`. | bestätigt | Gesicherter USB-Gerätedeskriptor vom 2026-07-29. |
| ASUS verwendet eigenständige numerische Firmwarestände. | bestätigt | Offizieller Download v51; offizielle InfoHub-Abbildung mit Firmware 50. |
| Die v51-Nutzlast gibt über `0x87` den Wert `0x0051` zurück. | bestätigt | Statischer ARM-Kontrollfluss und Antwortbauer. |
| Das reale Gerät gibt über `0x87` den Wert `0x0049` zurück. | bestätigt | Vollständige 440-Byte-Antwort aus Live-Test 02. |
| Der v51-Updater kann die HID-Herstellerrevision lesen. | bestätigt | `HidD_GetAttributes` und Übernahme von `VersionNumber`. |
| Das reale Gerät läuft wahrscheinlich mit Firmware 49. | sehr starke Ableitung | `bcdDevice 0.49`, realer `0x87`-Wert `0x0049`, v51-`0x87`=`0x0051`, v51-Metadatenkorrelation und öffentlicher Bericht über Anzeige 49 passen zusammen. |
| `bcdDevice` und InfoHub-Firmwareversion sind bei diesem Modell immer identisch. | unbekannt | Ein reales Wertepaar 0.49/`0x0049` ist bestätigt; eine offizielle allgemeine Zuordnung, eine v49-Binärdatei und ein v51-Gerätedeskriptor fehlen. |

Der geräteseitige Versionswert 49 ist bestätigt. Für die strengere
Paket-/Binäridentität „offizielle ASUS-Firmware v49“ fehlt weiterhin
mindestens eines der folgenden Bindeglieder:

- eine glaubwürdige v49-Nutzlast mit `0x87` → `0x0049` und passender interner
  Versionsstruktur,
- ein offizieller ASUS-Hinweis zur Bedeutung von `bcdDevice`, oder
- ein Gerätedeskriptor desselben Controllers vor und nach einem dokumentierten
  Firmwarewechsel, ergänzt um die jeweilige InfoHub-Anzeige.

## 4. Vergleich von `0x87`

| Merkmal | reales Gerät, als v49 abgeleitet | v51 |
| --- | --- | --- |
| Binärdatei gefunden | nein | ja |
| SHA-256 der ARM-Nutzlast | nicht verfügbar | `c4679ec340fc5edd3dea960ee027281cf6bd81cbbf347afb40e0d0b4f40aeb9f` |
| Handler statisch analysierbar | nein | ja, `0x00127588..0x001275c8` |
| Rückgabewert | empirisch bestätigt `0x0049` | statisch bestätigt `0x0051` |
| Vollständiger Ein-Paket-Report | `87 01 00 80 49 00 | 434 × 00` | `87 01 00 80 51 00 | 434 × 00` |

Ein empirischer Antwortvergleich ist möglich und zeigt ausschließlich Offset
`0x0004` als unterschiedlich. Ein statischer Handlervergleich bleibt ohne
v49-Binärdatei unmöglich; daher wurde auch kein v49-SHA-256 berechnet.

## 5. Bedeutung für den bisherigen Einmaltest

Der Einmaltest bestätigt nur, dass nach dem einmaligen Request ein 440-Byte-
Report empfangen wurde, der nicht exakt der v51-Folge entsprach. Seine Bytes
wurden nicht gespeichert.

- Falls das Gerät Firmware 49 ausführt und `0x87` versionsabhängig arbeitet,
  wäre eine Antwort mit `49 00` an Offset 4/5 die naheliegende Erklärung.
- Diese Erklärung kann nachträglich nicht geprüft werden; selbst Header,
  Befehlsbyte und Position der Abweichung sind unbekannt.
- Ein nach `open()` eingetroffener unabhängiger Report bleibt möglich, weil
  das Testprogramm vor dem Write nicht auf eine bereits lesbare Queue prüfte
  und danach den ältesten Report las.
- Die Abweichung widerlegt nicht die statische v51-Analyse. Sie zeigt nur,
  dass deren exakte Antwort nicht ohne bestätigte Firmwareidentität als
  versionsübergreifende Live-Erwartung verwendet werden darf.

Aus dieser ursprünglichen Untersuchung folgte keine Wiederholungsfreigabe. Der
später separat autorisierte Test 02 ist im Nachtrag dokumentiert und erteilt
seinerseits keine weitere Schreibfreigabe.

## 6. Offene Fragen und sichere nächste Schritte

- Existierte ein öffentliches oder nur werksseitiges v49-Paket?
- Ist der in InfoHub angezeigte Firmwarewert direkt die `0x87`-Antwort, ein
  Updater-Metadatum oder eine andere Quelle?
- Meldet ein Gerät mit sicher installierter v51 tatsächlich
  `bcdDevice 0.51`?
- Setzte v50 ebenfalls `0x87` auf `0x0050` und `bcdDevice` auf `0.50`?
- Welche konkrete 440-Byte-Folge lieferte der verlorene Einmaltest?

Vertretbar bleiben ausschließlich passive Maßnahmen: bereits vorhandene
Deskriptoraufnahmen vergleichen, offizielle ASUS-Kataloge und Archive später
erneut prüfen oder eine von einer glaubwürdigen Quelle bereitgestellte Datei
zunächst nur anhand Herkunft und Prüfsumme bewerten. Ein Downloadfund wäre vor
jeder Extraktion gesondert als vertrauenswürdig zu verifizieren und dürfte
nicht ausgeführt oder übertragen werden.

## Nachtrag: Live-Test 02 am 2026-09-01

Ein später gesondert autorisierter zweiter Einmaltest lieferte nach leerer
fünfsekündiger Ruhephase und leerer unmittelbarer Pre-Write-Queue vollständig:

```text
87 01 00 80 49 00 | 434 × 00
```

Damit ist der reale `0x87`-Versionswert `0x0049` empirisch bestätigt. Zusammen
mit `bcdDevice 0.49` ist die Aussage „installierte Firmwareversion
wahrscheinlich 49“ nun sehr stark gestützt. Die strengere Aussage, der
installierte Binärstand sei bytegenau eine offizielle ASUS-v49-Datei, bleibt
mangels Datei, Prüfsumme und offizieller Zuordnung abgeleitet. Der vollständige
Lauf steht in `command-0x87-live-test-02.md`.
