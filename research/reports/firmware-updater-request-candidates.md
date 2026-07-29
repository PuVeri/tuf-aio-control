# Firmware-Updater: statische Rekonstruktion von Anfragekandidaten

Stand: 2026-07-29, Europe/Berlin

## Umfang und Evidenz

Untersucht wurde ausschließlich die Disassembly von
`research/extracted/firmware-v51/WW11_320x320_2.8inch_v51_TUF_20250626.exe`
(SHA-256
`037b581f2bd5bc95db7db1a6f68d25d7ac2c19afe9fa09888851f0d6e448fb65`).
Die Datei wurde nicht ausgeführt. Es wurde kein USB- oder HID-Gerät geöffnet
und nichts an ein Gerät gesendet.

Virtuelle Adressen sind Adressen im PE-Abbild. „Transportwert“ und
„Steuerbyte“ beschreiben nur beobachtete Positionen; sie behaupten keine
unbelegte Befehlssemantik.

## Belegte Funktionsketten

### Segmentiertes Schreiben

```text
Upgradeablauf 0x402a90...
  -> Transportaufbau 0x402460
     -> 0x400 Byte: Steuerbytes 0 und 1, bis 0x3fe Datenbytes ab Offset 2
     -> I/O-Helfer 0x40b380
        -> führendes Nullbyte plus 0x400 Byte
        -> WriteFile
```

`0x402460` setzt Byte 0 aus dem letzten Stackargument. Byte 1 enthält beim
ersten Segment Bit 7 und einen 7-Bit-Wert. Folgesegmente löschen Bit 7 und
erhöhen den Wert. Der Datenbereich wird vor dem Kopieren genullt. Für eine
leere Ein-Segment-Übertragung ergibt der Kontrollfluss `Wert, 0x81`.

```text
4024a5  lea  ecx,[esi+edx+0x3fd] ; Segmentanzahl aus zwei Datenlängen
4024c2  mov  ecx,0x1             ; mindestens ein Segment
4024c7  mov  al,[ebp+0x14]       ; Byte 0
4024ca  or   cl,0x80             ; erstes Segment
4024d2  mov  [ebp-0x40f],cl      ; Byte 1
4024e0  mov  [ebp-0x410],al      ; Byte 0
4024cd  push 0x3fe               ; Datenbereich wird genullt
```

Der untere Helfer stellt ein zusätzliches Nullbyte voran:

```text
4025b2  push 0x400
4025bd  lea  eax,[ebp-0x410]
4025be  lea  ecx,[esi+1]
4025c2  mov  byte ptr [esi],0
4025c4  call 0x47f150            ; 0x400 Byte nach Puffer+1
4025e1  call 0x40b380
```

### Segmentiertes Lesen

```text
Upgradeablauf
  -> 0x4027c0
     -> 0x40b4e0 -> ReadFile
     -> entfernt das führende Byte der 0x401-Byte-Ablage
     -> prüft Transportbyte 0 und Segmentfolge in Byte 1
     -> kopiert Daten ab Transportoffset 2
```

Der höhere Helfer versucht bis zu dreimal zu lesen. Der untere I/O-Pfad nutzt
Overlapped-I/O und wartet im Pending-Fall höchstens `0xbb8` = 3000 ms.

```text
40291e  movzx edx,byte ptr [ebp-0x414] ; empfangenes Byte 0
402925  cmp   edx,[ebp+0x0c]           ; erwarteter Wert
402928  jne   0x402a4a                 ; Fehler
40292e  mov   al,[ebp-0x413]           ; Byte 1
402934  test  al,al
402936  jns   0x4029b4
402944  and   eax,0x7f
```

Bei `0x45`, `0x86` und `0x09` fordert der Aufrufer vier Datenbytes an, die ab
Transportoffset 2 kopiert werden. Beim `0x45`-Pfad wird das resultierende
DWORD zusätzlich gegen null geprüft. Eine erfolgreiche Antwortkonstante ist
nicht vorhanden.

### Direktes 0x400-Byte-Schreiben

`0x40c230` kopiert exakt `0x400` Byte aus dem Aufruferpuffer hinter ein
führendes Nullbyte und ruft `0x40b380` auf. Es ergänzt nicht die zwei
Steuerbytes des segmentierten Helfers.

```text
40c289  call 0x469379       ; 0x401 Byte
40c293  push 0x400
40c298  push ecx            ; Quellpuffer
40c299  lea  edx,[edi+1]
40c29d  mov  byte ptr [edi],0
40c2a0  call 0x47f150
40c2b3  call 0x40b380
```

## Kandidaten, Antwort und Risiko

### A: leerer segmentierter Austausch mit `0x45`

```text
... UI-Text „Wiping configuration“ ...
402d0e  push 0x45
402d10  push 0
402d11  push 0
402d12  push 0
402d17  call 0x402460

402d24  push 4
402d26  push 0
402d27  push 0
402d28  push 0x45
402d2a  push device
402d31  call 0x4027c0
402d3e  cmp  dword ptr [response],0
```

Vollständig bekannte WriteFile-Ablage:

```text
Offset  Inhalt
0x000   00                         führendes HID-Ablagebyte
0x001   45                         Transportbyte 0
0x002   81                         erstes/einziges Segment
0x003
 ...    00                         genullter Datenbereich
0x400
```

Die tatsächliche Write-Länge stammt aus den HID-Caps. Bei einem dort nicht
akzeptierten Wert verwendet der Helfer `0x401`. Das ist daher
Pufferkapazität/Fallback-Länge, nicht ohne Caps-Kontext eine universelle
Reportlänge.

Erwartete höhere Antwortstruktur:

```text
Transportoffset  Inhalt
0x00             45                 muss dem erwarteten Wert entsprechen
0x01             Segmentsteuerbyte  Bit 7/Folgewert wird ausgewertet
0x02..0x05       vier Datenbytes     Wert unbekannt; als DWORD != 0 verlangt
```

**Risiko: hoch, verworfen.** Der kleinste belegte Anfragekörper steht direkt
hinter „Wiping configuration“. Eine reine Statusabfrage ist nicht belegt; der
Kontext spricht für eine zustandsändernde Löschoperation.

### B: Firmwareblock mit `0x86`

`0x402e22` übergibt acht Metadatenbytes und einen auf `0x8000` Byte
aufgefüllten Firmwareblock an `0x402460`. `0x402e45` erwartet danach Byte 0
gleich `0x86` und vier Datenbytes.

**Risiko: kritisch, verworfen.** Bestätigter Firmwaretransfer.

### C: Abschlussstruktur mit `0x09`

```text
Transportoffset  Bytes (Little Endian)
0x00             09
0x01             81
0x02..0x05       00 00 10 00
0x06..0x09       dc 13 03 00
0x0a..0x0d       01 00 00 00
danach            00 ...
```

Die anschließende Lesefunktion erwartet Byte 0 `0x09` und vier Datenbytes.
Der UI-Kontext nennt den Schritt „write upgrade completion flag“.

**Risiko: kritisch, verworfen.** Das Paket gehört zum Setzen des
Upgrade-Abschlussflags.

### D: leerer segmentierter Wert `0x02`

Direkt nach dem Abschlussaustausch erzeugt `0x402460` ohne Daten:

```text
00 02 81 00 00 ...                 0x401-Byte-Ablage
```

Danach folgt keine Protokollantwort, sondern eine Reenumerationswartephase.

**Risiko: kritisch, verworfen.** Reset, Abschluss oder Moduswechsel sind mit
dem Kontext vereinbar; eine harmlose Bedeutung ist nicht belegt.

### E: direkte Rohpakete mit `88 01 00 80`

Vor dem Boot-Warten:

```text
0x400-Byte-Quellpuffer: 88 01 00 80 01 00 ... 00
WriteFile-Ablage:       00 88 01 00 80 01 00 ... 00
```

```text
402b19  mov dword ptr [buffer],0x80000188
402b21  mov byte ptr [buffer+4],0x01
402b26  call memset(...,0,0x3fb)
402b33  call 0x40c230
... anschließend Boot-Warteschleife ...
```

Nach Transfer, Completion-Flag und Reenumerationswartephase:

```text
0x400-Byte-Quellpuffer: 88 01 00 80 00 00 ... 00
WriteFile-Ablage:       00 88 01 00 80 00 00 ... 00
```

**Risiko: kritisch, beide verworfen.** Der erste Aufruf liegt am
Boot-Übergang, der zweite ausschließlich im Post-Upgrade-Abschluss. Eine
Status- oder Versionssemantik ist nicht belegt.

## Vergleich

Alle beobachteten Schreibformen gehören demselben Upgradeablauf an; ein
belegter normaler Betriebsmoduspfad fehlt.

| Merkmal | `0x45` | `0x86` | `0x09` | `0x02` | Rohpakete |
| --- | ---: | ---: | ---: | ---: | --- |
| segmentierter Helfer | ja | ja | ja | ja | nein |
| Daten | 0 Byte | 8 Byte Metadaten + bis 0x8000 Byte | 12 Byte | 0 Byte | feste 0x400 Byte |
| gepaarter Read | ja | je Block | ja | nein | nein |
| erwartetes Byte 0 | `0x45` | `0x86` | `0x09` | – | – |
| Antwortdaten | 4 Byte | 4 Byte | 4 Byte | – | – |
| Kontext | Konfiguration löschen | Firmware | Completion | Reenumeration | Boot/Abschluss |

Eine transportseitige Prüfsumme wurde nicht erkannt. Die acht Metadatenbytes
des `0x86`-Pfads enthalten rechnerisch verknüpfte Werte, werden mangels
vollständig rekonstruierter Semantik nicht als Prüfsumme bezeichnet.

## Interface- und Versionsgrenzen

### Beobachtete Fakten

- Der I/O-Objektaufbau besitzt getrennte Lese- und Schreibhandles für denselben
  SetupAPI-Gerätepfad.
- Die Transportpuffer sind `0x400` Byte groß.
- Linux-Deskriptoren belegen für Interface 1 1024 Byte Output und 16 Byte
  Input.
- Die Windows-Pfadauswertung kann VID, PID sowie optional MI und COL erfassen.
- In den untersuchten Aufrufern gibt es keine sichtbare Versionsstring-,
  Geräte-ID- oder Bootloaderversion-Auswertung.

### Ableitung

Die 1024-Byte-Outputgröße macht Interface 1 zum plausiblen Transportinterface.
Nicht direkt belegt ist, dass das ausgewählte Windows-Handle MI 01 oder dem
Linux-Interface 1 entspricht.

### Unbekannt

- MI/COL des ausgewählten Handles.
- Erfolgreiche Vier-Byte-Antwortwerte und deren Semantik.
- Eine sichere Status-, Versions- oder Geräteabfrage.
- Ob weitere indirekt erreichte Protokollpfade existieren.

## Ergebnis und Testempfehlung

Es wurde **kein ungefährlicher, belegter Anfragebefehl** gefunden. Der
strukturell kleinste Kandidat ist `0x45`, doch sein Löschkontext schließt ihn
als Testkandidaten aus.

Ein kontrollierter Einzeltest ist auf dieser Evidenz **nicht vertretbar**.
Zuvor fehlen mindestens ein passiv aufgezeichneter legitimer
Status-/Versionsaustausch, eine direkte Interfacezuordnung, ein bekannter
erfolgreicher Antwortwert und eine von Upgradefunktionen unabhängige
Aufrufkette.
