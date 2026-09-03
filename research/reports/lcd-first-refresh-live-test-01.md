# Erster begrenzter LCD-Refresh-Live-Test 01

Stand: 2026-09-03

## Zweck und Evidenzgrenze

Dokumentiert wird der erste reale, streng begrenzte Lauf des festen
Refresh-Testprofils auf dem ASUS-LCD. In diesem Dokumentationsticket erfolgten
keine weitere Gerätekommunikation, kein weiterer HID-Write und kein weiterer
Live-Test.

Der Lauf bestätigt den wiederholten Transport und mindestens einen sichtbaren
Commit. Die visuelle Beobachtung wurde nicht zeitlich vermessen. Deshalb wird
weder lückenlose Sichtbarkeit noch eine zuverlässige Unterdrückung des ASUS-
Defaultbilds abgeleitet.

## Testprofil

| Merkmal | Tatsächlicher Wert |
| --- | --- |
| Gerät | `0b05:1c7b` |
| USB-Geräterevision | `bcdDevice 0.49` / numerisch `0x0049` |
| Interface | ausschließlich Interface 1 |
| Bild | eingefrorenes Referenz-JPEG |
| JPEG-Länge | 2236 Byte |
| Segmente pro Frame | `N=3` |
| Frames | exakt 5 |
| hidraw-Writes | exakt 15 |
| Puffergröße je Write | exakt 1025 Byte |
| Sollabstand der Frame-Starts | 1,0 s |
| Retry | keiner |
| Fehler/Recovery | keiner / keine |

## Gemessener Transportablauf

Die vom Testprogramm relativ protokollierten Frame-Startzeiten waren ungefähr:

| Frame | Startzeit |
| ---: | ---: |
| 1 | 0,000126 s |
| 2 | 1,000215 s |
| 3 | 2,000251 s |
| 4 | 3,000321 s |
| 5 | 4,000398 s |

Die aufeinanderfolgenden Startabstände lagen damit ungefähr bei 1,000089 s,
1,000036 s, 1,000070 s und 1,000077 s. Es trat kein Catch-up-Burst auf.

Jeder vollständige Frame benötigte ungefähr 108 bis 109 ms. Alle drei Writes
jedes Frames meldeten die vollständige Länge von 1025 Byte. Nach insgesamt
fünf Frames und 15 vollständigen Writes endete die Session ohne Fehler,
Short Write, Retry oder Recovery.

Damit ist auf dem realen Gerät mit Versionsstand `0x0049` empirisch bestätigt:

- fünf direkt aufeinanderfolgende vollständige Interface-1-`0x08`-JPEG-
  Transfers funktionieren im getesteten 1-s-Raster;
- die Hostseite serialisiert die Frames ohne Überlappung und ohne Nachholburst;
- das bekannte `N=3`-Framing kann fünfmal fehlerfrei übertragen werden;
- für diesen Lauf waren weder Retry noch automatische Recovery erforderlich;
- der Transporterfolg lautet exakt **5 Frames / 15 vollständige Writes**.

Dieser Transporterfolg belegt weiterhin keinen separaten geräteseitigen
Decoder-Done-Status für jeden Frame. Er belegt das beobachtete erfolgreiche
Host-/hidraw-Transportergebnis der vollständigen Session.

## Manuelle visuelle Beobachtung

Das bekannte Referenzbild war während des Refresh-Laufs real auf dem
physischen LCD sichtbar. Zusammen mit dem bereits bestätigten Einzeltransfer
ist damit auch während einer wiederholten Transferfolge ein sichtbarer
JPEG-Commit empirisch bestätigt.

Nicht gemessen oder beobachtungsseitig protokolliert wurden:

- Beginn und Ende der Sichtbarkeit;
- lückenlose Sichtbarkeit über das gesamte Testfenster;
- ob das ASUS-Defaultbild zwischen zwei Frames kurz erschien;
- die Sichtdauer nach dem fünften Frame;
- der Zeitpunkt eines späteren Default-Fallbacks.

Deshalb ist ausdrücklich **nicht bestätigt**, dass der 1-s-Refresh das
Defaultbild zuverlässig oder dauerhaft unterdrückt. Ebenso ist noch keine
belastbare Persistenzlösung und keine minimale beziehungsweise erforderliche
Refreshrate bestimmt.

## Ergebnis

| Aussage | Status nach Live-Test 01 |
| --- | --- |
| Wiederholter vollständiger `0x08`-Transport auf realem v49-Gerät | empirisch bestätigt für 5 Frames bei 1,0 s Sollintervall |
| Exakt 15 vollständige 1025-Byte-Writes | empirisch bestätigt |
| Kein Retry, Fehler oder Catch-up | empirisch bestätigt |
| Referenzbild real sichtbar | empirisch bestätigt |
| Mindestens ein sichtbarer Commit während des Refresh-Laufs | empirisch bestätigt |
| Jeder der fünf Frames sichtbar committed | nicht einzeln beobachtet |
| Bild während des gesamten Testfensters lückenlos sichtbar | nicht bestätigt |
| ASUS-Defaultbild erschien währenddessen niemals | nicht bestätigt |
| 1,0 s ist eine ausreichende zuverlässige Refreshrate | nicht bestätigt |
| Sichtdauer nach Frame 5 | unbekannt |
| Refresh ist bereits eine zuverlässige Persistenzlösung | nicht bestätigt |

Die nächste offene Frage ist ausschließlich die zeitliche Displaywirkung:
Unter kontrollierter, zeitgestempelter Beobachtung muss später getrennt
bestimmt werden, ob und wann das Defaultbild zwischen beziehungsweise nach
vollständigen Refreshframes erscheint. Erst daraus kann eine erforderliche
Refreshrate abgeleitet werden.

