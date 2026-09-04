# TUF AIO Control

`tuf-aio-control` ist ein Forschungs- und Entwicklungsprojekt für eine native
Linux-Anwendung zur Steuerung des LCDs der **ASUS TUF Gaming LC III 360 ARGB
LCD**. Langfristig soll das Display eigene Bilder oder Animationen sowie reale
Hardwaretemperaturen anzeigen können.

Der sichere JPEG-Pfad und kontinuierliche Betrieb sind auf dem realen Gerät
bestätigt. Die Desktop-UI bereitet JPEG, PNG, WebP, BMP und vollständige GIF-
Animationen als validierte 320×320-Kompositionen vor. GIF-Liveanimation ist
offline implementiert, aber noch nicht real validiert. Vier frei wählbare
CPU-/GPU-Metrics können als LCD-Overlay angezeigt werden.

## Desktop-UI starten

Die lokal installierte Desktop-/Tray-Anwendung verwendet PySide6 und startet
mit:

```text
tuf-aio-control
tuf-aio-control --background
```

Direkte Starts aus `src/` sind ausschließlich Entwicklungsarbeit, nicht der
produktive Benutzerbetrieb. Verwendet werden die bereits vorhandenen lokalen
Pakete PySide6 6.11.2 und
Pillow 12.3.0 mit libjpeg-turbo; das Projekt installiert keine Pakete selbst.

Die UI sendet niemals automatisch. Sie zeigt Original und finale
320×320-Vorschau und bietet mittiges Zuschneiden oder Einpassen auf Schwarz.
Optional legt derselbe Renderer `CPU Package / Tctl`, `GPU / edge` und
`CPU CCD / Tccd1` dreiecksförmig über Vorschau und finalen JPEG-Frame. Die
gemeinsame Schriftfarbe ist frei wählbar, wird sofort sichtbar und als
`#RRGGBB` in den App-Einstellungen gespeichert; Default ist Weiß.
Erst nach erfolgreicher Konvertierung und erneuter ASUS-JPEG-Validierung
startet ein ausdrücklicher Klick auf `LCD starten` die kontrollierte Session.
GIF-Frames verwenden ein transportgeführtes serielles Pacing ohne feste
App-seitige FPS-Grenze. Die reale Transferdauer begrenzt die Bildrate
natürlich; dieses Verhalten muss erneut am realen LCD validiert werden.
`GIF-Geschwindigkeit` ist persistent auf 1×, 1.5×, 2× oder 3× einstellbar;
neue und fehlende Einstellungen verwenden 2×. Die sichtbare Preview folgt
diesem Faktor unabhängig von der LCD-Transportgeschwindigkeit.
Die Oberfläche verändert keine Geräteberechtigungen.

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

Nicht Ziel der aktuellen Phase sind aggressive Animationsraten oder eine
unbestätigte Änderung des empirisch belegten Transportprotokolls.

## Aktueller Erkenntnisstand

### Bestätigt

- Das Zielgerät ist die ASUS TUF Gaming LC III 360 ARGB LCD.
- Die USB-Kennung lautet `0b05:1c7b`.
- Das Gerät wird unter Linux als USB-HID-Gerät erkannt.
- Interface 1 besitzt einen unnummerierten 1024-Byte-OUT-Report und ist der
  empirisch bestätigte JPEG-Bildkanal.
- Linux-hidraw verwendet dafür `00 || 1024-Byte-Report`, insgesamt 1025 Byte.
- Ein 320×320-SOF0-/Baseline-JFIF-YCbCr-4:2:0-JPEG wurde auf dem realen Gerät
  mit Versionswert `0x0049` erfolgreich sichtbar dargestellt.
- Der wiederverwendbare Einzelbildpfad sendet ausschließlich Command `0x08`
  und höchstens einen Frame pro explizitem Aufruf beziehungsweise Klick.

### Noch nicht bestätigt

- Reale GIF-Liveanimation und die endgültige sichere Hardware-Framerate.
- Weitere Eingabeformate außerhalb JPEG, PNG, WebP, BMP und GIF.
- Fehler-, Timeout- und Recoveryverhalten des realen v49-Geräts.
- Andere JPEG-Profile und Segmentzahlen als der erfolgreiche Referenztransfer.
- Weitere Sensorkanäle jenseits der aktuellen CPU-/Package-/GPU-Anzeige.

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

Die Implementierung identifiziert passende Geräte über Vendor-ID, Product-ID,
Interface-Nummer und Reportstruktur. Dynamische hidraw-Pfade werden unmittelbar
vor jedem Write erneut gegen sysfs validiert.

## Architektur

Die erste Anwendung verwendet Python und PySide6. GUI, Validierung und
Hardwarezugriff bleiben wie folgt getrennt:

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

`src/lcd_transport.py` kapselt Geräteprüfung, JPEG-Validierung, Paketbildung
und den einmaligen synchronen Frame-Transfer. Die GUI enthält keine eigene
USB- oder HID-Protokollimplementierung.

### Sensorquellen

Liest verfügbare Linux-Sensorquellen aus und ordnet sie den gewünschten Werten
CPU, CPU Die/Package und GPU zu. Da Benennung und Verfügbarkeit von Hardware,
Treiber und Kernel abhängen, bleibt die Erfassung austauschbar und liefert
explizite Angaben zu Quelle, Einheit, Zeitstempel und Verfügbarkeit.

### Renderer

`src/image_pipeline.py` berücksichtigt EXIF-Orientierung und Transparenz,
skaliert per Crop oder Fit und erzeugt im Speicher ein konservatives
320×320-JPEG. Ein optionales Temperaturoverlay wird aus einem gecachten
Basisframe gerendert, ohne Sensor- oder Transportzugriff. Der bestehende
ASUS-Validator prüft jede Ausgabe erneut.

### Anwendung und Benutzeroberfläche

`src/tuf_aio_gui.py` zeigt Gerätestatus, Vorschau, Bildmetadaten und Fehler.
Sie ruft für einen expliziten Sendeklick genau einmal die Transport-API auf und
ist ohne angeschlossenes Gerät testbar.

## Sicherheitsregeln

Für alle aktuellen Senderpfade gelten enge Sicherheitsgrenzen:

- Es wird niemals automatisch gesendet; jeder Frame benötigt eine explizite
  Benutzeraktion.
- Zulässig ist ausschließlich der bestätigte `0x08`-JPEG-Pfad auf Interface 1.
- Es gibt keinen Retry, Reconnect, IN-Read, Recovery-Command oder Folgeframe.
- Es werden keine willkürlichen oder geratenen HID-Pakete ausprobiert.
- Beobachtete `/dev/hidrawX`-Pfade werden nicht fest codiert.
- Mitschnitte, Deskriptoren und andere Originaldaten werden unverändert
  aufbewahrt und nicht überschrieben.
- Beobachtung, Hypothese und bestätigte Erkenntnis werden klar getrennt.
- Andere Commands, Animationen und weitere Betriebsarten benötigen eine neue
  Sicherheitsbewertung und ausdrückliche Freigabe.

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
- `src/`: Geräteerkennung, geprüfter Einzelbildtransport, CLI-Werkzeuge und
  PySide6-Desktop-UI.

`package.json` und `package-lock.json` sind bereits vorhandene
Projektmetadaten. Ihre technische Rolle ist noch nicht festgelegt und wird in
dieser Phase nicht erweitert.

## Status

**Funktionsfähige Einzelbildstufe mit lokaler Temperaturanzeige.** Der
`0x08`-JPEG-Transfer und die wiederverwendbare Einzelbild-CLI wurden auf dem
realen v49-Gerät bestätigt. Bildpipeline und Desktop-UI sind vollständig
offline getestet. Die GUI liest CPU-, Package- und GPU-Werte ausschließlich
lokal und read-only aus hwmon; fehlende getrennte Werte erscheinen als `N/A`.
Der vorbereitete LCD-Frame kann Tctl, Tccd1 und `edge` der primären GPU mit
persistenter gemeinsamer Schriftfarbe darstellen; fehlende Overlaywerte
erscheinen als `—`. Die offline implementierte GIF-Animation benötigt noch
eine eigene reale Validierung und Freigabe.
