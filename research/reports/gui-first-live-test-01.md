# Erster kontrollierter GUI-Hardware-Live-Test 01

Datum: 2026-09-03

## Auftrag und Grenzen

Ausgeführt wurde genau ein beaufsichtigter GUI-Live-Test des bestehenden
Produktions-Refreshpfads. Zulässig waren ausschließlich das bekannte Gerät
`0b05:1c7b`, Interface 1, der bestätigte `0x08`-JPEG-Transport sowie das feste
GUI-Entwicklungsprofil mit 1,0 s Frame-Startintervall, höchstens 30,0 s und
höchstens 30 vollständigen Frames.

Es gab keinen zweiten Testlauf, keine neue Protokollanalyse, keine neuen
Opcodes und keine Codeänderung. Interface 0 und das getrennte OpenRGB-Gerät
`0b05:19af` wurden nicht beschrieben oder anderweitig angesprochen.

## Preflight ohne Writes

Vor jeder Schreibfreigabe bestanden:

- vollständige Offline-Suite: 168 Tests erfolgreich;
- `git diff --check`: sauber;
- dynamische Erkennung: genau zwei Treffer für `0b05:1c7b`;
- Interface 0: `/dev/hidraw7`;
- Interface 1: `/dev/hidraw8`;
- Gerät: `ASUS TUF GAMING LC III 360 ARGB LCD`;
- `bcdDevice`: Rohwert `0049`, numerisch `0x0049`;
- Interface-1-Usage: `0xff06/0x01`;
- Interface-1-Reports: Input 16 Byte, Output 1024 Byte, keine Feature-Reports
  und keine Report-ID;
- Production-Safety-Gates: vollständig bestanden;
- konkurrierende Writer: keine erkannt;
- GUI-Hardware-Livefreigabe: standardmäßig aus.

Beide Knoten standen zunächst auf `0640 root:input`. Interface 0 war effektiv
nicht schreibbar. Vor diesem Preflight gab es keinen hidraw-Open und keinen
HID-Write.

## Temporäre Berechtigung und Freigabe

Nur der dynamisch bestätigte Interface-1-Knoten `/dev/hidraw8` wurde manuell
und temporär auf `0660 root:input` gesetzt. `/dev/hidraw7` blieb unverändert
auf `0640 root:input`. Es wurde keine Udev-Regel installiert oder verändert.

Der anschließende read-only Preflight bestätigte erneut:

- Interface 0 effektiv nicht schreibbar;
- Interface 1 effektiv schreibbar;
- weiterhin exakt `0b05:1c7b`, Interface 1;
- alle Metadaten- und Report-Gates bestanden;
- keine konkurrierenden Writer.

Danach wurde vor dem ersten Write angehalten. Der Human Project Owner erteilte
ausdrücklich die Freigabe für genau diesen einzelnen begrenzten Lauf.

## Durchführung

Die normale GUI wurde einmal gestartet. Es gab keine programmgesteuerte
Bildauswahl, Freigabe oder Buttonbetätigung. Der Benutzer lud manuell ein
gültiges Bild, aktivierte das Temperaturoverlay, aktivierte
`Hardware-Livebetrieb freigeben`, startete die LCD-Session und änderte während
`running` die Overlayfarbe.

Die Session verwendete ausschließlich das fest verdrahtete Entwicklungsprofil:

```text
Frame-Startintervall: 1,0 s
maximale Laufzeit:    30,0 s
maximale Framezahl:   30
```

### Tatsächliche Framezahl und Laufzeit

Der Refreshworker war bei der Postflight-Prüfung terminal beendet und es lief
keine zweite Session. Die tatsächliche `RefreshResult.frames_sent`-Zahl und
`elapsed_seconds` wurden in diesem ersten GUI-Lauf jedoch nicht außerhalb des
GUI-Prozesses protokolliert und vor dessen Schließen nicht abgelesen. Deshalb
werden keine erfundenen Istwerte angegeben:

- tatsächliche vollständige Framezahl: **nicht exakt erfasst**, durch den Code
  hart auf höchstens 30 begrenzt;
- tatsächliche Controllerlaufzeit: **nicht exakt erfasst**, durch den Code hart
  auf höchstens 30,0 s begrenzt.

Dieser Beobachtungsmangel rechtfertigt keinen zweiten Live-Test. Ein späterer
Test benötigt vorab eine rein diagnostische, persistente Ergebnisprotokollierung.

## Sichtbeobachtung

Das reale LCD-Ergebnis war negativ:

- Das in der GUI geladene Bild erschien nicht auf dem physischen LCD.
- CPU Package/Tctl erschien nicht auf dem physischen LCD.
- GPU/edge erschien nicht auf dem physischen LCD.
- CPU CCD/Tccd1 erschien nicht auf dem physischen LCD.
- Sichtbare Temperaturänderungen konnten daher auf dem LCD nicht bestätigt
  werden.
- Die während `running` geänderte Overlayfarbe war in der GUI sichtbar, führte
  aber zu keinem sichtbaren neuen LCD-Frame.
- Das ASUS-Defaultbild wurde auf dem LCD permanent weiter abgespielt; eine
  sichtbare Unterbrechung oder Änderung wurde nicht beobachtet.

Damit sind weder sichtbarer Erstcommit noch sichtbare dynamische Updates für
diesen GUI-Lauf bestätigt. Aus der Beobachtung allein folgt nicht, ob Frames
transportseitig erfolgreich übertragen, vom Gerät nicht sichtbar committed
oder unmittelbar vom internen Defaultproduzenten überstimmt wurden. Ohne
persistentes Transportresultat bleibt diese Unterscheidung unbekannt.

## GUI-Verhalten und Sessionende

Die GUI wurde als optisch korrekt und responsiv beobachtet. Bild,
Temperaturwerte und Farbänderung waren in der UI sichtbar. Es wurde kein
unerwarteter GUI-Fehler gemeldet.

Nach dem Test zeigte die Prozessprüfung keinen Thread
`tuf-aio-lcd-refresh`; vorhanden waren nur der Qt-Hauptthread sowie Qt-/Wayland-
Hilfsthreads. Die Konkurrenzprüfung fand keinen offenen Writer auf Interface 1.
Damit waren Refreshworker und Gerätehandle beendet, und es startete keine neue
Session automatisch.

Die GUI wurde erst nach dieser Prüfung geschlossen. Zwei Terminal-Interrupts
trafen lediglich einen Qt-Timercallback und beendeten den bereits senderlosen
Prozess nicht; anschließend wurde genau dieser eindeutig identifizierte
GUI-Prozess per `SIGTERM` beendet. Zu diesem Zeitpunkt existierten weder
Refreshworker noch Gerätewriter, sodass dadurch kein Transfer unterbrochen
wurde.

## Postflight und Berechtigungen

Die temporäre Interface-1-Berechtigung wurde manuell entfernt. Der abschließende
read-only Postflight bestätigte:

| Interface | Knoten | Modus | Eigentümer | effektives Schreibrecht |
| --- | --- | --- | --- | --- |
| 0 | `/dev/hidraw7` | `0640` | `root:input` | nein |
| 1 | `/dev/hidraw8` | `0640` | `root:input` | nein |

Weiterhin bestanden die Interface-1-Safety-Gates. Es gab keine konkurrierenden
Writer, keinen GUI-Prozess und keine Hintergrundsession.

## Ergebnis und nächster Entscheidungspunkt

Der Test ist betrieblich sauber beendet, aber hinsichtlich der sichtbaren
LCD-Ausgabe fehlgeschlagen. Der 30-s-/30-Frame-Entwicklungshardcap darf im
nächsten Ticket **nicht** durch normalen Dauerbetrieb ersetzt werden.

Vor einem weiteren Live-Test sind zunächst ohne Gerätekommunikation eine
persistente Protokollierung von Stopgrund, tatsächlicher Framezahl,
Controllerlaufzeit und erstem Transportfehler sowie eine gezielte Auswertung
des negativen Sichtbefunds zu entwerfen. Ein weiterer Live-Test, ein anderes
Intervall, Interface-0-Steuerung oder ein Versuch gegen den internen
Defaultproduzenten sind durch dieses Ergebnis nicht freigegeben.
