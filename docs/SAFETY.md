# Sicherheitsregeln für die Geräteanalyse

Die ASUS TUF Gaming LC III 360 ARGB LCD verwendet ein bislang undokumentiertes
USB-/HID-Protokoll. Fehlerhafte Reports könnten das Gerät in einen unbekannten
Zustand versetzen. Diese Regeln gelten für Analyse, Dokumentation und spätere
Implementierung.

## Aktuell zulässiger Umfang

Die aktuelle Phase ist auf **passive Analyse** beschränkt. Zulässig sind
insbesondere:

- vorhandene Linux-Geräteinformationen lesen,
- USB- und HID-Deskriptoren lesen und sichern,
- bereits erzeugte Mitschnitte offline untersuchen,
- legitimen Referenzverkehr passiv mitschneiden,
- Beobachtungen, Prüfsummen und Hypothesen dokumentieren,
- Parser und Auswertungen ausschließlich mit gespeicherten Daten testen.

Das Vorhandensein eines beschreibbaren Gerätepfads ist keine Erlaubnis, ihn zu
verwenden.

## Verbotene Aktionen in der aktuellen Phase

- Keine Daten an `/dev/hidrawX`, USB-Endpunkte oder Control-Endpunkte schreiben.
- Keine Output Reports oder Feature Reports senden oder setzen.
- Keine willkürlichen, geratenen, mutierten oder durch Fuzzing erzeugten
  HID-Pakete übertragen.
- Keine bekannten Pakete mit ungeklärten Feldern, Längen oder Zielinterfaces
  wiedergeben.
- Keine Geräte-Resets, Firmwareaktionen oder privilegierten Zugriffsregeln ohne
  gesonderten Auftrag durchführen.

Auch ein scheinbar harmloses Nullpaket oder ein aus ähnlicher Hardware
übernommener Befehl gilt als willkürlicher Schreibzugriff.

## Geräteidentifikation

Die Pfade `/dev/hidraw7` und `/dev/hidraw8` wurden lediglich in einer bisherigen
Sitzung beobachtet. HID-Raw-Nummern werden von Linux dynamisch vergeben und
dürfen weder in Quellcode noch in dauerhafter Konfiguration fest codiert werden.

Eine spätere Anwendung identifiziert das Gerät mindestens anhand von:

- Vendor-ID `0b05`,
- Product-ID `1c7b`.

Zur sicheren Auswahl der korrekten Schnittstelle müssen zusätzlich
Interface-Nummer, HID-Report-Deskriptor und gegebenenfalls Seriennummer,
physischer Gerätepfad oder weitere stabile Deskriptormerkmale geprüft werden.
Bei Mehrdeutigkeit wird kein Gerät automatisch zum Schreiben geöffnet.

## Umgang mit Mitschnitten und Originaldaten

- Originale USB-/HID-Mitschnitte, Deskriptor-Dumps und Rohdaten werden nicht
  überschrieben oder nachträglich bearbeitet.
- Jede neue Aufzeichnung erhält einen neuen, eindeutigen Dateinamen.
- Auswertungen, gefilterte Exporte und kommentierte Varianten werden als
  separate abgeleitete Dateien gespeichert.
- Zu Originaldaten werden Datum, Zeitzone, Aufnahmeumgebung, Gerätezustand,
  Werkzeugversion und nach Möglichkeit eine kryptografische Prüfsumme
  dokumentiert.
- Temporäre Logs dürfen gelöscht werden; als Evidenz referenzierte
  Originaldaten nicht.
- Sensible oder proprietäre Mitschnitte werden nicht ohne Prüfung der
  Berechtigung veröffentlicht.

## Voraussetzungen für spätere Schreibtests

Ein Schreibtest darf erst geplant werden, wenn:

1. die HID-Report-Deskriptoren beider Schnittstellen gesichert und analysiert
   sind,
2. Report-IDs, Report-Typen und exakte Report-Größen dokumentiert sind,
3. die Befehlsstruktur durch legitimen, passiv beobachteten Referenzverkehr
   nachvollziehbar ist,
4. Zielinterface, Richtung, Sequenz und erwartete Antwort bekannt sind,
5. unbekannte Felder, Längenregeln und Abbruchbedingungen bewertet wurden,
6. Originalmitschnitte unverändert als Evidenz vorliegen,
7. ein minimaler, begrenzter Testfall mit Logging und sicherem Abbruch
   dokumentiert ist,
8. der konkrete Schreibtest durch einen gesonderten Auftrag ausdrücklich
   freigegeben wurde.

Eine allgemeine Freigabe zur Codeentwicklung autorisiert keinen realen
Geräteschreibzugriff.

## Verhalten bei Unsicherheit

Bei unklarer Schnittstellenzuordnung, widersprüchlichen Deskriptoren,
unerwarteten Geräteantworten, Verbindungsabbrüchen oder nicht reproduzierbaren
Beobachtungen wird die Analyse gestoppt. Der Zustand wird dokumentiert; fehlende
Informationen werden nicht durch Vermutungen ersetzt.

Beobachtungen und Hypothesen werden im
[Protokolltagebuch](PROTOCOL_NOTES.md) getrennt geführt.

