# TUF AIO Control

`tuf-aio-control` ist ein Forschungs- und Entwicklungsprojekt für eine native
Linux-Anwendung zur Steuerung des LCDs der **ASUS TUF Gaming LC III 360 ARGB
LCD**. Langfristig soll das Display eigene Bilder oder Animationen sowie reale
Hardwaretemperaturen anzeigen können.

Das Projekt befindet sich in einer frühen Analysephase. Das USB-/HID-Protokoll
ist bislang nicht dokumentiert. Daher hat die sichere, passive Untersuchung des
Geräts Vorrang vor der Implementierung einer Steuerung.

## Projektziele

Die geplante Anwendung soll:

- das unterstützte Gerät zuverlässig erkennen, ohne wechselnde
  `/dev/hidrawX`-Pfade fest zu codieren,
- eigene Bilder und Animationen für das LCD aufbereiten und übertragen,
- CPU-Temperatur, CPU-Die-/Package-Temperatur und GPU-Temperatur aus
  Linux-Schnittstellen beziehen,
- fehlende oder plattformspezifisch anders benannte Sensorwerte sauber
  behandeln,
- Zugriffsfehler und nicht unterstützte Geräte verständlich melden,
- das ermittelte Protokoll nachvollziehbar und reproduzierbar dokumentieren.

Nicht Ziel der aktuellen Phase sind Schreibzugriffe auf das Gerät,
Paketinstallation oder Anwendungscode.

## Aktueller Erkenntnisstand

### Bestätigt

- Das Zielgerät ist die ASUS TUF Gaming LC III 360 ARGB LCD.
- Die USB-Kennung lautet `0b05:1c7b`.
- Das Gerät wird unter Linux als USB-HID-Gerät erkannt.
- Es besitzt zwei HID-Schnittstellen.
- Die zugehörigen HID-Raw-Geräte wurden in einer bisherigen Umgebung als
  `/dev/hidraw7` und `/dev/hidraw8` beobachtet.

### Noch nicht bestätigt

- Die Aufgabenverteilung zwischen den beiden HID-Schnittstellen.
- Report-IDs, Report-Größen und Report-Typen.
- Die Bedeutung einzelner Befehle und Antworten.
- Das Bildformat, die Displayauflösung, Farbreihenfolge und
  Übertragungssegmentierung.
- Initialisierungs-, Status- oder Keepalive-Sequenzen.
- Ob Sensorwerte vom Host gerendert oder als Zahlenwerte übertragen werden.

Die beobachteten HID-Raw-Nummern sind nur Momentaufnahmen. Sie können sich nach
Neustart, Neuverbinden oder durch andere USB-Geräte ändern und dürfen nicht als
stabile Gerätekennung verwendet werden.

Details, Beobachtungen und Hypothesen werden im
[Protokolltagebuch](docs/PROTOCOL_NOTES.md) getrennt voneinander geführt.

## Bekannte Hardwarekennung

| Merkmal | Wert |
| --- | --- |
| Hersteller | ASUS |
| Gerät | TUF Gaming LC III 360 ARGB LCD |
| USB Vendor-ID | `0b05` |
| USB Product-ID | `1c7b` |
| USB-Kennung | `0b05:1c7b` |
| Geräteklasse unter Linux | USB HID |
| Beobachtete HID-Schnittstellen | 2 |
| Bisher beobachtete Pfade | `/dev/hidraw7`, `/dev/hidraw8` |

Eine spätere Implementierung muss passende Geräte über Vendor-ID und
Product-ID identifizieren. Falls mehrere Geräte oder Schnittstellen passen,
müssen zusätzlich stabile USB- und HID-Merkmale wie Interface-Nummer,
Report-Deskriptor, Seriennummer oder physischer Gerätepfad ausgewertet werden.

## Geplante Architektur

Die genaue Sprache, GUI-Technik und Bibliotheksauswahl sind noch nicht
festgelegt. Die fachlichen Grenzen sollen unabhängig davon wie folgt getrennt
werden:

```text
Geräteerkennung ──> HID-/Protokollschicht ──> LCD-Transport
                           ^
                           |
Sensorquellen ──> Datenmodell ──> Renderer für Bilder, Animationen und Werte
                           ^
                           |
                  Anwendung und Benutzeroberfläche
```

### Geräteerkennung

Ermittelt das Zielgerät anhand von `0b05:1c7b`, ordnet dessen zwei
HID-Schnittstellen korrekt zu und prüft Zugriffsrechte. Dynamische
`/dev/hidrawX`-Pfade werden erst zur Laufzeit aufgelöst.

### HID- und Protokollschicht

Kapselt HID-Reports, Report-IDs, Paketgrößen, Befehle, Antworten und
Fehlerbehandlung. Erkenntnisse aus der passiven Analyse müssen dokumentiert und
mit Originaldaten belegbar sein, bevor daraus Schreiboperationen entstehen.

### Sensorquellen

Liest verfügbare Linux-Sensorquellen aus und ordnet sie den gewünschten Werten
CPU, CPU Die/Package und GPU zu. Da Benennung und Verfügbarkeit von Hardware,
Treiber und Kernel abhängen, bleibt die Erfassung austauschbar und liefert
explizite Angaben zu Quelle, Einheit, Zeitstempel und Verfügbarkeit.

### Renderer

Erzeugt aus Bildern, Animationen und Sensordaten ein vom Display erwartetes
Format. Auflösung, Pixelreihenfolge, Farbraum, Bildrate und Segmentierung werden
erst nach Protokollanalyse festgelegt.

### Anwendung und Benutzeroberfläche

Verwaltet Konfiguration, Gerätestatus, Anzeigeinhalt und Fehlermeldungen. Die
Fachlogik soll von der konkreten Oberfläche und vom Hardwarezugriff getrennt
bleiben, damit sie ohne angeschlossenes Gerät getestet werden kann.

## Sicherheitsregeln

Bis auf Weiteres gilt **ausschließlich passive Analyse**:

- Es werden keine Daten, Feature Reports oder Output Reports an das Gerät
  gesendet.
- Es werden keine willkürlichen oder geratenen HID-Pakete ausprobiert.
- Beobachtete `/dev/hidrawX`-Pfade werden nicht fest codiert.
- Mitschnitte, Deskriptoren und andere Originaldaten werden unverändert
  aufbewahrt und nicht überschrieben.
- Beobachtung, Hypothese und bestätigte Erkenntnis werden klar getrennt.
- Schreibtests beginnen frühestens nach dokumentierter Analyse der
  Report-Größen, Report-IDs und Befehlsstruktur und benötigen einen gesonderten,
  ausdrücklich freigegebenen Arbeitsauftrag.

Die verbindlichen Einzelheiten stehen in [docs/SAFETY.md](docs/SAFETY.md).

## Grobe Roadmap

1. **Passive Bestandsaufnahme**
   - USB- und HID-Deskriptoren sichern,
   - Interfaces, Endpunkte und Report-Deskriptoren dokumentieren,
   - Gerätezuordnung über stabile Merkmale nachvollziehen.
2. **Referenzverkehr erfassen**
   - legitimen Datenverkehr einer vorhandenen Herstellerlösung passiv
     mitschneiden,
   - Originalmitschnitte unverändert sichern,
   - beobachtete Transaktionen zeitlich und funktional einordnen.
3. **Protokoll ableiten und validieren**
   - Paketfelder, Report-Größen, Sequenzen und Bildübertragung hypothesengeleitet
     analysieren,
   - Erkenntnisse durch wiederholte Beobachtung bestätigen,
   - erst danach einen begrenzten und freigegebenen Schreibtest planen.
4. **Linux-Grundfunktionen entwickeln**
   - robuste Geräteerkennung,
   - lesende Diagnose und Protokollmodell,
   - abstrahierte Sensorerfassung,
   - hardwareunabhängige Tests.
5. **LCD-Ausgabe entwickeln**
   - kontrollierte Bildübertragung,
   - Renderer für Bilder und Animationen,
   - Anzeige der gewünschten Temperaturwerte.
6. **Anwendung stabilisieren**
   - native Linux-Oberfläche,
   - Konfiguration und Autostart nach Bedarf,
   - Fehlerbehandlung, Dokumentation und Paketierung.

Jede Phase setzt voraus, dass ihre Sicherheitsgrenzen und Abnahmekriterien vor
Beginn geklärt sind.

## Projektstruktur

```text
tuf-aio-control/
├── assets/
├── captures/
├── docs/
│   ├── PROTOCOL_NOTES.md
│   └── SAFETY.md
├── logs/
├── src/
├── .gitignore
├── package-lock.json
├── package.json
└── README.md
```

- `assets/`: kontrollierte Quellmedien und spätere Testbilder oder Animationen.
  Herkunft und Nutzungsrechte dauerhafter Assets müssen dokumentiert sein.
- `captures/`: unveränderte USB-/HID-Mitschnitte und zugehörige Metadaten.
  Originaldateien werden nicht überschrieben; abgeleitete Daten erhalten neue
  Dateien.
- `docs/`: Projektdokumentation, Sicherheitsregeln und Protokolltagebuch.
- `logs/`: lokale Diagnose- und Analyseprotokolle. Temporäre Logdateien werden
  nicht versioniert.
- `src/`: späterer Anwendungscode. In der aktuellen Dokumentationsphase bleibt
  der Ordner leer.

`package.json` und `package-lock.json` sind bereits vorhandene
Projektmetadaten. Ihre technische Rolle ist noch nicht festgelegt und wird in
dieser Phase nicht erweitert.

## Status

**Forschungsphase / passive Analyse.** Es existiert noch keine funktionsfähige
Anwendung und es wurde im Rahmen dieser Projektgrundlage kein Schreibzugriff auf
das Gerät autorisiert.

