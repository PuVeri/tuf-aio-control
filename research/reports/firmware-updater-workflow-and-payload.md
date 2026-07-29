# Firmware-Updater: Ablauf und eingebettete Nutzlast

## Beobachtete Fakten

- Der zentrale Ablauf liegt ungefähr bei `0x402b40` bis `0x403168`.
- Boot-Warten: höchstens `0x258` (= 600) Durchgänge mit je 100 ms Schlaf,
  also ungefähr 60 Sekunden maximale Schleifenwartezeit.
- Danach erscheint „Wiping configuration“. Der Code führt einen
  Schreib-/Leseaustausch aus und bricht bei Fehler ab. Numerische Argumente
  werden mangels gesicherter Signatur nicht als Opcodes bezeichnet.
- Firmwareübertragung:
  - Start: virtuelle Adresse `0x5c21b0`, PE-Dateioffset `0x1c15b0`
  - Länge: `0x313dc` = 201692 Byte
  - exklusives Ende: virtuelle Adresse `0x5f358c`, Dateioffset `0x1f298c`
  - äußere Blöcke von höchstens `0x8000` Byte
  - weitere Zerlegung in höchstens `0x3fe` Datenbytes je Nutzblock
  - ein `0x8000`-Byte-Arbeitspuffer wird mit `0xff` gefüllt und dann mit der
    aktuellen Nutzlastmenge überschrieben
  - nach jedem äußeren Block folgt ein Lesevorgang; bei Erfolg werden
    Restlänge und Quellzeiger fortgeschrieben
- Nach der Übertragung wird eine Drei-DWORD-Struktur mit `0x00100000`,
  `0x000313dc` und `1` gesendet und eine Vier-Byte-Antwort gelesen. Der
  UI-Text nennt diesen Abschnitt „write upgrade completion flag“.
- Danach folgen ein weiterer Schreibaufruf und eine Schleife von höchstens
  `0x258` Durchgängen mit 100-ms-Schlaf sowie eine Abschlussprüfung.
- Die eingebettete Region liegt vollständig in `.rdata`. Ihre Grenzen folgen
  aus dem tatsächlich inkrementierten Quellzeiger und der heruntergezählten
  Länge.

## Abgeleitete Zusammenhänge

- `0x5c21b0..0x5f358c` ist die vom Updater als Firmwareinhalt übertragene
  Bytefolge. Dies bestätigt die Transportgrenze, nicht das interne Format.
- Die Abschlussstruktur wiederholt die Länge und vermutlich eine Zieladresse.
  `0x00100000` wird nicht als bestätigte Flashadresse bezeichnet.
- Boot-, Lösch-, Transfer- und Abschlussphase sind als Reihenfolge statisch
  belegt; die Bedeutung einzelner Zahlenwerte bleibt offen.

## Hypothesen

- Vier-Byte-Antworten könnten Statuswerte oder Bestätigungen sein.
- Der Wert `1` in der Abschlussstruktur könnte ein Flag sein; nur der
  umgebende UI-Text stützt diese Interpretation.

## Unbekannt und negative Befunde

- Kein bestätigter Paketheader oder Opcode-Katalog.
- Keine bestätigte transportseitige Prüfsumme über die Firmware.
- Keine bestätigte Geräte-, Interface- oder Firmwareversionsprüfung.
- Keine Aussage zur internen Architektur oder zum Containerformat allein aus
  der Firmwaregrenze; ARM-artige Daten und Embedded-Strings bleiben Hinweise.

