# Realer Einmaltest von Befehl `0x87` – Test 02

Dokumentiert: 2026-09-01  
Exakter Testzeitpunkt: nicht mitgeteilt

## Quelle und Umfang

Dieser Bericht dokumentiert ausschließlich das vom Bediener bestätigte
Live-Ergebnis des zweiten, zuvor gesondert freigegebenen `0x87`-Einmaltests.
Während der Erstellung dieses Berichts fand keine weitere Gerätekommunikation
statt. Nicht mitgeteilte Laufzeitdetails werden nicht ergänzt oder geschätzt.

## Pre-Write-Sicherheitsphase

Nach dem endgültigen Öffnen von Interface 0 lief die gehärtete
Pre-Write-Sequenz vollständig durch:

1. Während der festen fünfsekündigen rein lesenden Ruhephase ging kein
   Inputreport ein.
2. Die unmittelbare Nullzeit-Prüfung direkt vor dem Write fand die per-Open-
   Inputqueue leer vor.
3. Erst nach beiden Leerbefunden wurde die einzige `os.write()`-Stelle
   erreicht.

Damit wurde vor diesem konkreten Write kein bereits wartender Report
beobachtet. Das unvermeidbare Race-Fenster zwischen der letzten Prüfung und
dem Write wird dadurch verkleinert, aber nicht formal beseitigt.

## Einziger Request

Es wurde genau ein `hidraw.write()` mit 441 Byte ausgeführt:

```text
00 | 87 01 00 80 | 436 × 00
```

Das führende `00` ist das Linux-hidraw-Reportnummernfeld für einen
unnummerierten Report. Der an das Gerät übertragene Report war 440 Byte lang:

```text
87 01 00 80 | 436 × 00
```

Es gab keinen zweiten Write, keinen Retry und keine automatische Recovery.

## Vollständige empfangene Antwort

Es wurde genau ein 440-Byte-Inputreport empfangen:

```text
87 01 00 80 49 00 | 434 × 00
```

Vollständiger Hexdump aller 440 Byte:

```text
0000: 87 01 00 80 49 00 00 00 00 00 00 00 00 00 00 00
0010: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0020: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0030: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0040: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0050: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0060: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0070: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0080: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0090: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00a0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00b0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00c0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00d0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00e0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00f0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0100: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0110: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0120: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0130: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0140: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0150: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0160: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0170: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0180: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0190: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
01a0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
01b0: 00 00 00 00 00 00 00 00
```

## Vergleich mit der statischen v51-Antwort

Die aus der analysierten v51-Firmware statisch belegte Antwort lautet:

```text
87 01 00 80 51 00 | 434 × 00
```

Der reale Report stimmt in Länge, Header, zweitem Versionsbyte und allen 434
Paddingbytes exakt überein. Es gibt genau eine abweichende Byteposition:

| Offset | v51 statisch | reales Gerät | Einordnung |
| ---: | ---: | ---: | --- |
| `0x0004` | `0x51` | `0x49` | niederwertiges Byte des 16-Bit-Versionswerts |

Als Little-Endian-Halbwort an Offset 4/5 ergibt sich:

```text
v51-Firmware:  51 00 → 0x0051
reales Gerät:  49 00 → 0x0049
```

## Kontrollfluss nach dem Empfang

Nach dem Empfang wurde der Gerätedeskriptor geschlossen. Es folgten:

- kein weiterer `0x87`-Request,
- kein anderer HID-Befehl,
- kein Retry,
- keine automatische Recovery,
- keine Firmwareaktion.

## Bestätigte Aussage und verbleibende Ableitung

### Direkt bestätigt

- `0x87` ist auf dem realen Gerät ein funktionierender Abfragepfad, der einen
  16-Bit-Versionswert in einer strukturell konstanten 440-Byte-Antwort liefert.
- Die analysierte v51-Firmware liefert statisch `0x0051`.
- Das reale Gerät liefert empirisch `0x0049`.
- Dasselbe reale Gerät meldet im USB-Gerätedeskriptor `bcdDevice 0.49`.
- Für diesen Lauf waren die fünfsekündige Ruhephase und die unmittelbare
  Pre-Write-Queueprüfung leer. Der empfangene Report ist daher deutlich
  belastbarer dem einmaligen Request zuzuordnen als beim ersten Test.

### Weiterhin abgeleitet

Die Formulierung **„auf dem Gerät ist die ASUS-Firmwareversion 49
installiert“** bleibt eine sehr starke, nun empirisch gestützte Ableitung, aber
keine bytegenau bestätigte Firmwareidentität. Es fehlt weiterhin mindestens
eines der folgenden direkten Bindeglieder:

- eine glaubwürdige offizielle v49-Firmwaredatei mit statisch verglichenem
  `0x87`-Handler,
- eine offizielle ASUS-Dokumentation, die `0x0049` und `bcdDevice 0.49`
  ausdrücklich der Paket-/Firmwarebezeichnung v49 zuordnet, oder
- eine unabhängig gesicherte InfoHub-Anzeige „Firmware version 49“ für genau
  dieses Gerät und denselben Zustand.

Direkt bestätigt ist daher präzise **„das Gerät meldet über `0x87` den
Versionswert 49 und über USB die Geräterevision 0.49“**. Die Benennung des
installierten Binärstands als ASUS-Firmware v49 ist daraus mit hoher
Konfidenz abgeleitet.

## Sicherheitsgrenze

Dieser zweite Test ist abgeschlossen. Sein Ergebnis autorisiert keinen
weiteren HID-Write. Während der Dokumentation und Codeanpassung wurde keine
weitere Gerätekommunikation durchgeführt und keine Schreibberechtigung
aktiviert.
