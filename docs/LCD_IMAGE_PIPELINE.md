# Sichere Bildvorbereitung für das AIO-LCD

## Zweck und Grenze

`src/image_pipeline.py` bereitet normale Bilddateien vollständig offline für
den bestehenden ASUS-Einzelbildtransport vor. Das Modul enthält keine HID-,
USB- oder Geräteerkennung und verändert keine Originaldatei. Die erzeugten
JPEG-Bytes bleiben im Speicher.

Unterstützte Eingabeformate:

- JPEG/JPG;
- PNG;
- WebP;
- BMP;
- GIF ausschließlich als Standbild aus Frame 0.

Animationen, Timer, Mehrfachframes und Hintergrundverarbeitung sind nicht Teil
dieser Pipeline.

## Verarbeitung

Die Pipeline führt für genau eine Quelldatei aus:

1. tatsächliches Dateiformat mit Pillow erkennen und gegen die Allowlist
   prüfen;
2. ausschließlich den aktuellen ersten Frame laden;
3. EXIF-Orientierung anwenden;
4. Transparenz deterministisch auf Schwarz zusammensetzen;
5. nach RGB konvertieren;
6. mit dem gewählten Modus auf exakt 320×320 skalieren;
7. konservatives JPEG vollständig im Speicher encodieren;
8. die Ergebnisbytes zwingend mit `lcd_transport.validate_jpeg()` prüfen.

Quellen sind zusätzlich auf 64.000.000 Pixel begrenzt, damit unkontrollierte
Speicherlast vor der vollständigen Verarbeitung abgewiesen wird.

## Skalierungsmodi

### Zuschneiden / Crop

Das Seitenverhältnis bleibt erhalten. Das Bild wird so skaliert, dass die
gesamte 320×320-Fläche gefüllt ist, und anschließend mittig beschnitten. Es
findet keine freie Verzerrung statt.

### Einpassen / Fit

Das Seitenverhältnis bleibt erhalten und das gesamte Bild bleibt sichtbar.
Die nicht belegte Fläche wird symmetrisch mit Schwarz aufgefüllt. Es findet
keine freie Verzerrung statt.

Standardmodus der GUI ist `Zuschneiden`.

## JPEG-Vertrag

Der lokal vorhandene Stack besteht aus Pillow 12.3.0 mit libjpeg-turbo. Die
Pipeline setzt explizit:

```text
Format:       JPEG
Größe:        320×320
Eingabe:      RGB
Qualität:     60
Subsampling:  2 / YCbCr 4:2:0
Progressive:  false
Optimize:     false
```

`optimize=False` verwendet die normalen libjpeg-Huffmantabellen. Der
nachgelagerte bestehende Validator prüft byteinhaltlich alle vier erwarteten
Standard-Huffmantabellen und lehnt Abweichungen ab. Er bestätigt außerdem
JFIF, SOF0/Baseline, 8 Bit, drei YCbCr-Komponenten, 4:2:0, genau einen
Baseline-Scan, EOI ohne Dateinachlauf und `N<=200` beziehungsweise höchstens
204000 Byte.

Damit hängt die Sendbarkeit nicht nur von Encoderoptionen ab: Jede konkrete
Ausgabe muss den bereits live erprobten Validatorvertrag erneut erfüllen.

## GIF-Verhalten

GIF wird derzeit ausdrücklich **nicht animiert**. Die Pipeline setzt den
Decoder auf Frame 0, lädt und kopiert ausschließlich diesen Frame und erzeugt
daraus ein einzelnes JPEG. Sie iteriert nicht über weitere Frames. Die GUI
kennzeichnet dies als `GIF · erstes Bild als Standbild`.

## GUI

`src/tuf_aio_gui.py` zeigt getrennte Vorschauen für Original und finale
320×320-Ausgabe. Die Auswahl `Zuschneiden`/`Einpassen` erzeugt die finale
Vorschau erneut, sendet sie aber nicht. Angezeigt werden Originalauflösung,
Eingabeformat, Ausgabeauflösung, JPEG-Vertrag, JPEG-Größe, Segmentzahl,
Padding und Validatorstatus.

`Auf Display senden` ist nur aktiv, wenn Pipeline und ASUS-Validator
erfolgreich waren und die dynamische Geräteerkennung ein gültiges Interface 1
gefunden hat. Beim Klick werden die finalen JPEG-Bytes erneut validiert, das
Gerät erneut erkannt und genau einmal `lcd_transport.send_frame_once()`
aufgerufen. Es existiert kein Retry oder automatischer Folgeframe.

## Offline-Tests

Die Tests decken Landscape/Portrait für Crop und Fit, Quadrat, PNG-Alpha,
JPEG, PNG, WebP, BMP, animiertes GIF mit ausschließlich rotem Frame 0,
EXIF-Rotation, 1×1-Quelle, große Quelle, ungültige Datei und den vollständigen
JPEG-/Validatorvertrag ab. GUI-Tests mocken Discovery und Transfer vollständig.

Während der Implementierung wurde kein Gerät geöffnet und kein Bild gesendet.

## Schritte bis zu echter GIF-Animation

Eine spätere Animation ist eine eigene Betriebsart und benötigt vor jeder
Implementierung mindestens:

- statische und reale Erkenntnisse zu sicherem Frame-Timing und Decoder-Lease;
- definierte Obergrenzen für Framerate, Laufzeit, Framezahl und Datenmenge;
- Verhalten bei teilweise übertragenen Frames, Busy-Zustand und USB-Fehlern;
- Abbruch-, Sichtbarkeits- und Kühlungssicherheitskonzept;
- eine neue explizite Freigabe für Mehrfachframe-Sends.

Die aktuelle Pipeline enthält bewusst keinen Timer, keine Frameiteration und
keinen Weg, mehr als ein JPEG pro Sendeklick zu übertragen.
