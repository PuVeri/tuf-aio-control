# Plan für einen passiven ASUS-LCD-Referenzcapture

Stand: 2026-09-02

## Zweck und Sicherheitsgrenze

Dieser Plan beschreibt einen späteren Mitschnitt genau einer bewusst
ausgelösten, legitimen Bildübernahme durch ASUS InfoHub. Er führt jetzt keinen
Capture aus, kommuniziert nicht mit USB- oder HID-Geräten und installiert keine
Software. Der spätere Herstellertransfer ist selbst ein schreibender
LCD-Vorgang; der Mitschnitt fügt ihm keine eigenen USB-Anfragen oder HID-Writes
hinzu.

Zielgerät ist ausschließlich `0b05:1c7b`, reales Gerät mit bislang
beobachtetem `bcdDevice 0.49`. Das getrennte AURA-RGB-Gerät `0b05:19af` gehört
nicht zum LCD-Protokoll, wird nicht an eine VM durchgereicht und wird nicht in
die Protokollauswertung aufgenommen.

Die empfohlene Methode ist **Variante A, native Windows-Maschine mit USBPcap**.
Sie bildet die Herstellerumgebung ohne Virtualisierungsreset und ohne
Gast-Scheduling ab. Variante B ist technisch sinnvoll, wenn nur eine bereits
vorbereitete Windows-VM zur Verfügung steht oder die Prozessisolation wichtiger
als unverfälschtes Timing ist. Ihre Zeitmessung ist nicht gleichwertig.

## 1. Bereits bekannte Zielstruktur

| Funktion | Interface | Endpoint | Drahtreport |
| --- | ---: | ---: | ---: |
| kleine Befehle OUT | 0 | `0x01` | 440 Byte |
| kleine Antworten IN | 0 | `0x82` | 440 Byte |
| JPEG-Segmente OUT | 1 | `0x03` | 1024 Byte |
| Start-/Annahmenachricht IN | 1 | `0x84` | 16 Byte |
| Enumeration/HID-Setup | beide | `0x00` | Control-URBs |

Interface 1 hat keinen HID Report ID. Auf EP `0x03` sind deshalb genau 1024
Byte zu erwarten: vier Byte Controlword ab Drahtbyte 0, danach 1020
Segmentbyte. Der Windows-HID-Anwendungspuffer ist eine andere Ebene. Microsoft
verlangt bei einer unnummerierten Collection im ersten Pufferbyte den Wert
null; die korrekte Länge ist `HIDP_CAPS.OutputReportByteLength`. Ein USB-Capture
kann dieses von HIDClass entfernte Hostbyte nicht sehen. Er kann nur, aber
vollständig, die 1024 Drahtbyte bestätigen. Siehe
[HidD_SetOutputReport](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidsdi/nf-hidsdi-hidd_setoutputreport),
[Sending HID Reports](https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/sending-hid-reports)
und Microsofts
[HClient-Beispiel](https://github.com/microsoft/Windows-driver-samples/blob/main/hid/hclient/report.c).

Das ist für die Auswertung wichtig: Ein im Capture mit `08` beginnender
1024-Byte-Buffer ist kein Beleg, dass InfoHub auf seiner `WriteFile`-Grenze das
führende Nullbyte weggelassen hat. Das API-Nullbyte befindet sich schlicht
nicht auf EP `0x03`. Aus Descriptor und dokumentierter Windows-HID-Grenze
folgt als erwarteter Anwendungspuffer `00 || 1024-Byte-Report`, also 1025 Byte;
der Wire-Capture bestätigt davon ausschließlich den 1024-Byte-Gerätereport.

## 2. Gemeinsame Vorbereitung beider Varianten

Alle Installations- und Einrichtungsarbeiten erfolgen in einem getrennten
Vorbereitungstermin, nicht unmittelbar vor dem Referenzvorgang.

### 2.1 Festzuhaltende Versionen und Dateien

- Windows-Version und Build;
- ASUS InfoHub genau aus dem bereits archivierten offiziellen Paket
  `ASUS_InfoHub_Software_TUF_GAMING_LC_III_360_ARGB_LCD_v1.0.0.15.zip`;
- SHA-256 des ZIPs:
  `0d7124d700b07d1f49315d77aa15473f01c42c1492f2e8cece845f19c32d2a21`;
- Wireshark-, USBPcap- und gegebenenfalls Hypervisorversion samt
  Installationsdatei-Hash;
- SHA-256, Länge und JPEG-Metadaten des Referenzbilds;
- Datum, Zeitzone und Rechnername des Captures.

USBPcap `1.5.4.0` ist die Mindestversion dieses Plans. Laut
[offiziellen USBPcap-Releases](https://github.com/desowin/usbpcap/releases)
konnten ältere Versionen nach bestimmten `SET INTERFACE`-/`SET CONFIGURATION`-
Folgen falsche Endpointinformationen protokollieren. Wireshark soll aus dem
offiziellen stabilen Windows-Paket stammen; die tatsächlich verwendete Version
wird festgehalten. Die Wireshark-Windows-Pakete können USBPcap optional
mitinstallieren, siehe
[Wireshark-Installationsdokumentation](https://www.wireshark.org/docs/wsug_html_chunked/ChBuildInstallWinInstall.html).

USBPcap installiert einen Filtertreiber. Falls danach ein Neustart nötig ist,
wird normal neu gebootet. Die von USBPcap angebotene Funktion zum sofortigen
Neustart aller USB-Geräte wird nicht benutzt; schon der
[USBPcap-Quelltext](https://github.com/desowin/usbpcap/blob/master/USBPcapCMD/cmd.c)
warnt dabei vor möglichem Datenverlust.

### 2.2 Referenzbild

Vor dem Capture liegt genau eine unveränderliche Datei bereit:

```text
320 x 320 Pixel
vollflächig neutrales Mittelgrau, keine Transparenz, kein Text, kein Verlauf
JPEG SOF0, 8 Bit, Baseline Sequential
JFIF/Y′CbCr 4:2:0, Standard-Huffman-Codierung
genau ein Bild, keine Animation und kein Mehrbildcontainer
Dateilänge > 1020 Byte und <= 204000 Byte
Dateilänge modulo 1020 != 0
```

Die Längenbedingungen stellen sicher, dass es mindestens ein Folgesegment und
einen echten Schlussblocksuffix gibt. Das Bild wird vorab mit einem
reproduzierbaren Encoder erzeugt und nicht erst in InfoHub bearbeitet. Encoder,
Optionen, exakte Länge und SHA-256 werden neben dem Capture abgelegt. Eine
InfoHub-interne Neucodierung bleibt möglich und ist gerade Gegenstand des
Captures; deshalb wird das rekonstruierte JPEG später byteweise mit der
Quelldatei verglichen.

Mittelgrau ist gegenüber reinem Schwarz oder Weiß vorzuziehen: Es bleibt eine
einfache Vollfläche, vermeidet aber eine mögliche Sonderbehandlung vollständig
schwarzer beziehungsweise leer wirkender Bilder. Falls InfoHub dieses JPEG
nicht direkt akzeptiert, wird **nicht während des Captures** spontan auf ein
anderes Format gewechselt. Der Lauf wird ohne Bildaktion beendet und erst nach
einer neuen Planung wiederholt.

### 2.3 Ausschluss unerwünschter Herstelleraktionen

Vor dem Start von InfoHub gelten gleichzeitig:

1. Der Rechner beziehungsweise Windows-Gast ist vollständig offline. Sowohl
   WLAN als auch Ethernet sind getrennt; nur ein UI-Schalter in InfoHub reicht
   nicht.
2. Automatische Starts von Armoury Crate, Aura, OpenRGB und anderer ASUS-/RGB-
   Software sind für den Lauf deaktiviert. Kein zweiter Prozess darf das LCD
   öffnen.
3. Das getrennte Firmwarepaket v51 und dessen Updater-EXE befinden sich nicht
   in der ausführbaren Testumgebung und werden keinesfalls gestartet.
4. In InfoHub wird weder eine Update-, Firmware-, Gerätewartungs- noch
   Einstellungsseite geöffnet. Erscheint ein Updatezwang oder startet ein
   Updater-Kindprozess, wird **kein Bild angewendet** und der Lauf beendet.
5. Es werden keine Sensorseite, Rotation, Helligkeit, Animation, Slideshow,
   GIF-Funktion oder andere LCD-Einstellung verändert.
6. Es gibt genau einen Anwenderauslöser für das vorbereitete Bild und keinen
   Retry. Bei fehlendem Commit wird nur weiter aufgezeichnet.

Optional läuft Microsoft Process Monitor mit einem engen Filter auf InfoHub
und seine Kindprozesse. Sein Zweck ist nur, Prozessstarts, Imagepfade und die
zeitliche Prozessaktivität zu sichern und damit einen unerwarteten Updater zu
erkennen. Es ist kein Ersatz für USBPcap und liefert nicht zuverlässig den
HID-Nutzpuffer. Process Monitor unterstützt nichtdestruktive Filter, Prozess-
details, Stacks und native Logdateien, siehe
[Microsoft Sysinternals Process Monitor](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon).

Ein VM-Snapshot schützt nur Windows-Dateien und -Konfiguration. Er kann **keine
Änderung des physischen AIO-Geräts zurückrollen**.

## 3. Variante A: native Windows-Maschine

### 3.1 Benötigte Werkzeuge

- Windows 10/11 x64 auf der Maschine, an der das reale AIO angeschlossen ist;
- ASUS InfoHub `1.0.0.15` aus dem oben bezeichneten, gehashten Paket;
- Wireshark mit TShark, Capinfos und USBPcap `>= 1.5.4.0`;
- PowerShell `Get-FileHash` für Artefakthashes;
- optional Process Monitor für die Prozessspur;
- optional eine unabhängige Kamera für den groben sichtbaren Commitzeitpunkt.

Es wird kein Hardware-USB-Analyzer benötigt. USBPcap ist eine
Host-Stack-Aufzeichnung von URBs, nicht von einzelnen physischen USB-
Transaktionen. Für dieses Ziel ist die URB-Ebene passend: Windows reicht einen
1024-Byte-HID-Report als einen Transfer weiter. USBPcap `1.4.1.0` und neuer
zeichnet für Bulk-/Interrupttransfers sowohl FDO→PDO als auch PDO→FDO auf;
das ist in den
[USBPcap-Releasenotes](https://github.com/desowin/usbpcap/releases)
dokumentiert.

### 3.2 Geräte- und Captureauswahl

1. Im USBPcap-Gerätebaum wird der Root Hub bestimmt, unter dem
   `VID_0B05&PID_1C7B` hängt.
2. Erfasst wird der **aktuelle USB-Geräteadressfilter nur dieses Geräts**,
   nicht pauschal der gesamte Root Hub.
3. Zusätzlich wird „new devices“ aktiviert, damit ein unerwarteter Reset und
   eine Wiederanmeldung mit neuer Adresse sichtbar bleiben. Während des kurzen
   Laufs darf kein anderes USB-Gerät an- oder abgesteckt werden.
4. `Inject descriptors` bleibt aktiviert. Dadurch kann der Capture selbst die
   Zuordnung Adresse ↔ `0b05:1c7b` und `bcdDevice` tragen.
5. `0b05:19af` wird im USBPcap-Gerätebaum ausdrücklich **nicht** ausgewählt.
   Auch weitere ASUS-, AURA-, Eingabe- oder Massenspeichergeräte werden nicht
   ausgewählt.

USBPcap verwendet einen Filter pro Root Hub und unterstützt eine Bitmaske
einzelner Geräteadressen; Adresse null dient zum Erfassen neu angeschlossener
Geräte. Das ist direkt in der
[USBPcap-Headerdefinition](https://raw.githubusercontent.com/desowin/usbpcap/master/USBPcapDriver/include/USBPcap.h)
dokumentiert. Die Adresse ist nur für diesen Lauf stabil. Maßgeblich bleibt der
injizierte VID/PID-Deskriptor, nicht eine alte Adressnummer.

### 3.3 Vollständige URBs und Zeitstempel

Die USBPcap-extcap-Einstellungen lauten:

```text
capture source:   der ermittelte \\.\USBPcapN-Root-Hub
devices:          nur aktuelle Adresse von 0b05:1c7b
new devices:      ein
inject descriptors: ein
snapshot length:  mindestens 4096 Byte
capture buffer:   mindestens 32 MiB
output:           pcapng, keine Ringrotation
```

Der größte benötigte Datensatz umfasst USBPcap-Pseudoheader plus 1024 Byte;
4096 Byte Snaplen lässt dafür Reserve. Nach dem Lauf wird für jedes Ziel-URB
geprüft, dass `captured length == original length`, die erwartete
`dataLength` vollständig vorliegt und Submit sowie Completion dieselbe IRP-ID
tragen. OUT-Nutzdaten liegen im Submit-Datensatz, IN-Nutzdaten im
Completion-Datensatz. Beide Datensätze werden **gepaart, nie aneinandergehängt**.
Der USBPcap-Header definiert IRP-ID, Status, Richtung, Bus, Adresse, Endpoint,
Transferart und Datenlänge bytegenau
([Captureformat-Header](https://raw.githubusercontent.com/desowin/usbpcap/master/USBPcapDriver/include/USBPcap.h)).

Wireshark speichert standardmäßig pcapng; eine Konvertierung in ein einfacheres
Format kann Zeitauflösung und Metadaten verlieren. Das Original-pcapng bleibt
deshalb unverändert, erhält sofort einen SHA-256 und wird nur über Arbeitskopien
ausgewertet. Siehe
[Wireshark-Dateiformate](https://www.wireshark.org/docs/wsug_html_chunked/ChIOSaveSection.html)
und
[Wireshark-Zeitstempel](https://www.wireshark.org/docs/wsug_html_chunked/ChAdvTimestamps.html).

### 3.4 Ablauf auf nativer Maschine

1. Windows vollständig starten, aber InfoHub und andere ASUS-/RGB-Anwendungen
   noch nicht öffnen. Für belastbare Aussagen zu `config+0x108` darf seit dem
   Boot kein anderer Hostprozess das Zielgerät konfiguriert haben.
2. Netzwerkzustand „offline“, Prozessliste, Dateihashes, Uhrzeit und sichtbares
   Ausgangsbild protokollieren.
3. Optional Process-Monitor- und Kameraaufzeichnung starten.
4. USBPcap mit obigen Einstellungen starten. Fünf Sekunden Vorlauf ohne
   Herstelleraktion aufzeichnen.
5. InfoHub starten. Dadurch umfasst der Capture auch mögliche
   Initialisierungsbefehle auf Interface 0, insbesondere Command `0x19`.
6. Warten, bis die Oberfläche stabil ist. Kein UI-Element außer dem Weg zum
   statischen Bild betätigen. Ein Firmwarehinweis beendet den Lauf ohne
   Bildaktion.
7. Das vorab gehashte 320×320-JPEG auswählen und genau die eine UI-Aktion
   ausführen, die InfoHub zur Übernahme verwendet. Falls bereits die
   Dateiauswahl den Transfer auslöst, wird kein zusätzlicher Apply-Klick
   ausgeführt.
8. Zeitpunkt der UI-Aktion und des sichtbaren Displaywechsels notieren. Bei
   Erfolg 30 Sekunden ohne weitere Aktion weiterlaufen lassen. Bleibt der
   Commit aus, 60 Sekunden ab der Aktion aufzeichnen, aber weder erneut klicken
   noch das Bild nochmals auswählen.
9. Zuerst den USB-Capture stoppen und als pcapng sichern, dann optionale
   Prozess-/Videoaufzeichnungen stoppen. Erst danach InfoHub schließen.
10. Capture, Referenzbild, Prozesslog und Notizdatei hashen. Das Original nicht
    in Wireshark neu speichern oder mit einem Displayfilter verkleinern.

„Genau ein Bild“ meint eine einzige bewusste Herstelleraktion. Sendet InfoHub
beim Start selbst einen alten Frame oder retried es autonom, wird das nicht
verdeckt: Der kontinuierliche Originalcapture bleibt vollständig und jeder
`0x08`-Transfer wird separat ausgewiesen. Für die strenge Ein-Transfer-
Referenz ist der Lauf nur dann gültig, wenn insgesamt genau eine vollständige
`0x08`-Gruppe vorliegt. Andernfalls beantwortet er weiterhin die Startup- und
Timeoutfragen, ist aber kein minimaler Ein-Transfer-Referenzlauf.

## 4. Variante B: Windows-VM mit USB-Passthrough

### 4.1 Wann die VM-Variante sinnvoll ist

Sie ist vertretbar, wenn eine fertig eingerichtete Windows-VM vorhanden ist,
der Hypervisor einzelne USB-Geräte anhand VID/PID filtern kann und InfoHub das
Ziel am virtuellen xHCI-Controller unverändert erkennt. Sie ist nicht die erste
Wahl für Latenzaussagen: Anheften an die VM verursacht mindestens eine
Ab-/Wiederanmeldung, und Gast-Scheduling kann Zeitabstände verändern.

Oracle VirtualBox 7.2 dokumentiert xHCI für alle USB-Geschwindigkeiten bis USB
3.0 und gerätespezifische Filter anhand Vendor ID, Product ID, Revision und
Seriennummer. Nicht passende Geräte bleiben beim Host
([VirtualBox User Manual, USB Device Filters](https://download.virtualbox.org/virtualbox/7.2.4/UserManual.pdf)).
Ein anderer Hypervisor ist nur geeignet, wenn er dieselben Eigenschaften
nachweisbar bietet.

### 4.2 Benötigte Werkzeuge

- Linux-Host mit bereits vorhandenem Hypervisor und per-device USB-Passthrough;
- offline vorbereiteter Windows-10/11-Gast und Snapshot vor InfoHub-Ausführung;
- im Gast dieselben InfoHub-, Wireshark- und USBPcap-Versionen wie in Variante A;
- optional auf dem Linux-Host Wireshark/Dumpcap und Kernel-`usbmon` für einen
  zweiten, physischen URB-Zeitstrahl;
- Hashwerkzeuge auf Host und Gast;
- optional Kamera beziehungsweise Process Monitor wie bei Variante A.

`usbmon` meldet URB-Submission, Callback und Fehler samt URB-ID, Bus, Adresse,
Endpoint, Länge, erfasster Länge und Zeitstempel. Es weist zugleich darauf hin,
dass Daten trotz einer von null verschiedenen Länge gekürzt sein können;
Snaplen und `len_cap` müssen daher geprüft werden. Siehe die
[Linux-Kernel-Dokumentation zu usbmon](https://docs.kernel.org/next/usb/usbmon.html).

### 4.3 Passthrough- und Capturekonfiguration

1. Die VM erhält einen xHCI-Controller und genau einen positiven USB-Filter:
   Vendor `0b05`, Product `1c7b`, nach Möglichkeit zusätzlich Revision/Port/
   Seriennummer. Es wird kein leerer ASUS-Vendorfilter angelegt.
2. Für `0b05:19af` existiert **kein** positiver Filter. Das Gerät verbleibt am
   Host. Dasselbe gilt für Tastatur, Maus, Massenspeicher und alle anderen
   ASUS-/AURA-Geräte.
3. Netzwerkadapter des Gasts sind vor dem Start von InfoHub getrennt; Shared
   Clipboard, Drag-and-drop und unnötige Shared Folders sind aus.
4. Nach dem Anheften wird gewartet, bis `0b05:1c7b` im Gast stabil enumeriert
   ist. Während des Captures wird es weder gelöst noch erneut angeheftet.
5. Im Gast erfasst USBPcap nur die virtuelle Adresse des Zielgeräts, wieder mit
   Deskriptorinjektion, New-Device-Erfassung, Snaplen mindestens 4096 und
   mindestens 32 MiB Buffer. Da der virtuelle Root Hub nur das Ziel enthält,
   ist dies zugleich die sauberste Trennung von `19af`.
6. Optional startet auf dem Host **vor dem Passthrough** ein zweiter Capture
   auf dem konkreten `usbmonN`-Bus mit Snaplen mindestens 4096 und pcapng-
   Ausgabe. Dieser zeigt den physischen Zeitstrahl einschließlich des
   Passthrough-Resets. Nach Möglichkeit liegt das Ziel auf einem Bus ohne
   Tastatur oder Massenspeicher.

Ein Host-`usbmonN`-Capture kann andere Geräte desselben physischen Busses
enthalten. Er bleibt deshalb optional und wird offline auf die während der
Enumeration belegte Bus-/Geräteadresse von `0b05:1c7b` reduziert. Er ersetzt
nicht den sauberen USBPcap-Capture aus dem Gast. Das RGB-Gerät `0b05:19af` wird
auch dann nicht analysiert oder in die abgeleitete Ziel-pcapng übernommen.

### 4.4 Zeitbasis und Ablauf

Der Ablauf im Gast ist identisch mit Abschnitt 3.4. Der Gast-USBPcap-Zeitstrahl
ist maßgeblich für die Reihenfolge aus Sicht von Windows/InfoHub. Falls ein
Host-`usbmon`-Capture existiert, ist dieser maßgeblich für die physische
Geräteseite. Beide werden nicht über die Rechneruhren, sondern über die
eindeutige Folge aus erstem/letztem `0x08`-Controlword und Payloadhash
korreliert.

Die VM-Variante wird verworfen, wenn:

- InfoHub das virtuelle Gerät nicht eindeutig erkennt;
- der Report auf EP `0x03` nicht als vollständige 1024-Byte-URB erscheint;
- USBPcap oder usbmon Payloadkürzungen beziehungsweise Drops melden;
- während des Bildtransfers ein weiterer Passthrough-Reset auftritt;
- mehr als die dokumentierten Virtualisierungslatenzen oder autonome Retries
  auftreten;
- eine Updateanforderung erscheint.

Ein Snapshot wird erst nach dem Stoppen aller Captures zurückgesetzt. Er ist
nur ein Mittel zur Wiederherstellung des Gasts, keine Schutzmaßnahme für die
Gerätefirmware.

## 5. Exakter minimaler Referenzvorgang

Der gemeinsame, prüfbare Vorgang lautet:

```text
Vorlauf:       5 s, keine Benutzeraktion
Software:      genau ASUS InfoHub 1.0.0.15, offline
Quelle:        ein vorab gehashtes, statisches 320x320-SOF0-JPEG,
               vollflächig Mittelgrau, L mod 1020 != 0
Aktion:        genau eine Bildübernahme, kein Retry
Begleitaktion: keine Animation, Rotation, Helligkeit, Sensor-/LCD-Einstellung
Nachlauf:      30 s nach sichtbarem Commit;
               ohne Commit 60 s nach der einzigen Aktion
Ende:          Capture stoppen, dann erst InfoHub schließen
```

Zu notieren sind die einzige UI-Aktionszeit, der sichtbare Commitzeitpunkt
beziehungsweise „kein Commit bis Ende“, sämtliche Dialoge und der Zustand des
Displays vor und nach dem Lauf. Es wird kein eigener Statusbefehl gesendet.
Nur die von InfoHub selbst erzeugten IN-/OUT-Transfers werden erfasst.

## 6. Offline-Auswertungsschema

### 6.1 Unveränderte Primärartefakte

Für jeden Lauf werden mindestens abgelegt:

```text
capture-original.pcapng
capture-original.pcapng.sha256
reference-320-gray.jpg
reference-320-gray.jpg.sha256
capture-notes.txt
tool-versions.txt
optional: procmon.pml, video
optional VM: host-usbmon-original.pcapng
```

Das Original bleibt unverändert. Anzeige- und Exportfilter werden nur auf eine
Arbeitskopie angewandt. `capinfos` dokumentiert Dateiformat, Zeitspanne,
Paketanzahl und vorhandene Interface-Statistiken.

### 6.2 Identität und URB-Gruppierung

1. In den injizierten beziehungsweise echten Device Descriptors alle Instanzen
   mit `idVendor=0x0b05`, `idProduct=0x1c7b` bestimmen; `bcdDevice`, Bus und
   Geräteadresse ausgeben.
2. Alle anderen Geräte verwerfen, insbesondere `0b05:19af`.
3. Zielereignisse nach Endpoint gruppieren: `00`, `01`, `82`, `03`, `84`.
4. Submit und Completion anhand `usb.irp_id` paaren. Transferart, Status,
   angeforderte/tatsächliche Länge, `captured/original length` und beide
   Zeitstempel erhalten.
5. Für OUT den Payload aus Submit, für IN aus Completion nehmen. Das
   Submit-/Completion-Paar ist ein URB, nicht zweimal Payload.
6. Ungepaarte, gekürzte oder fehlerhafte URBs markieren. Ein am Anfang oder
   Ende des Zeitfensters lediglich ausstehender IN-Read ist ein dokumentierter
   Randeffekt, nicht automatisch ein Capturefehler. Jeder payloadtragende URB
   und jedes EP-`0x03`-OUT-Segment muss dagegen vollständig zuordenbar sein.

Wireshark stellt dafür unter anderem `usb.bus_id`, `usb.device_address`,
`usb.endpoint_address`, `usb.transfer_type`, `usb.urb_id`, `usb.urb_len`,
`usb.data_len`, `usb.urb_status` und `usb.capdata` bereit, siehe
[USB Display Filter Reference](https://www.wireshark.org/docs/dfref/u/usb.html).

### 6.3 Rekonstruktion von Interface 1 OUT

Für jeden vollständigen 1024-Byte-Report auf EP `0x03`:

```text
cw      = uint32_le(report[0:4])
command = cw & 0xff
first   = (cw >> 31) & 1
field23 = (cw >> 8) & 0x7fffff
block   = report[4:1024]            # immer exakt 1020 Byte
```

Eine `0x08`-Gruppe beginnt mit `first=1`; `field23` ist dann `N`. Danach
müssen bei gleichem Command genau die Indizes `1..N-1` folgen. Ausgegeben
werden:

- rohe vier Controlwordbytes und Little-Endian-Wert jedes Reports;
- Submit- und Completionframe/-zeit jedes URBs;
- `N`, physische Reportanzahl, Reihenfolge, Lücken und Duplikate;
- der vollständige erste und letzte 1024-Byte-Report;
- `assembled = block[0] || ... || block[N-1]`, Länge exakt `N*1020`;
- SHA-256 jedes Blocks und des zusammengesetzten Payloads.

### 6.4 JPEG und Schlussblocksuffix

Der zusammengesetzte Payload wird als JPEG-Markerstrom, nicht durch eine bloße
Bytefolgensuche, geparst. `ff 00`-Stuffing und Restartmarker innerhalb der
Scandaten dürfen nicht als EOI gelten. Auszugeben sind:

- SOI-Offset, erwartet `0`;
- Markerliste und insbesondere SOF-Typ, Precision, 320×320,
  Komponenten/Sampling;
- Offset des syntaktischen `ff d9`;
- `jpeg_length = eoi_offset + 2` bei SOI an Offset null;
- `suffix = assembled[eoi_offset+2 : N*1020]`;
- exakte Suffixlänge, vollständiger Suffixhexstring, Bytehäufigkeiten und
  SHA-256;
- Bytevergleich `assembled[0:jpeg_length]` gegen die gehashte Quelldatei.

Damit wird nicht angenommen, dass ASUS nullt. Ein vollständig mit `00`
gefüllter Suffix wäre ein Captureergebnis. Nicht-nullte Altbytes, `ff`-Fill,
ein wiederholtes EOI oder jede andere Folge würden ebenso unverändert
festgehalten.

### 6.5 Interface 1 IN und Zeitfolge

Jeder vollständige 16-Byte-Report auf EP `0x84` wird als Zeitstempel plus 16
rohe Byte ausgegeben, nicht nur Reports mit `08 81`. Für jede `0x08`-Gruppe
werden mindestens berechnet:

```text
t_last_out_submit
t_last_out_complete
t_08_81_complete - t_last_out_complete
t_weitere_ep84_complete - t_08_81_complete
t_sichtbarer_commit - t_08_81_complete   # nur grob, aus externer Notiz/Video
```

Zu prüfen sind Anzahl und Position von `08 81`, Bytes 2..15, alternative
Byte-1-Werte, Reports vor dem letzten Segment und spätere Busy-/Ready-/Done-/
Fehlermuster. Ein schon vorab ausstehender IN-Submit ist normal; für die
Gerätenachricht ist dessen Completion mit den 16 Datenbyte maßgeblich.

USB-Reihenfolge kann zeigen, dass InfoHub vor einer nächsten Aktion einen
IN-Report abwartet. Sie beweist ohne Prozessinstrumentierung nicht, ob der
Anwendungsthread semantisch auf `08 81` blockiert. Ebenso bleibt `08 81` nach
der statischen Analyse eine Start-/Annahmenachricht und kein Decoder-Done.

### 6.6 Interface 0 und Timeout

Alle 440-Byte-Reports auf EP `0x01` und `0x82` werden analog mit
4+436-Segmentierung rekonstruiert und in derselben Zeitbasis einsortiert.
Besonders auszuweisen sind:

- jeder OUT-Commandwert vor, während und nach dem JPEG-Transfer;
- Command `0x19`: erstes Payload-DWORD Little Endian als beobachteter neuer
  Wert für `config+0x108`;
- Abstand des letzten `0x19` zum Abschluss des Interface-1-Transfers;
- mögliche Commands `0x08`/`0x09` und alle Antworten;
- Sicherheitsalarm bei updater-/persistenznahen Commands `0x02`, `0x0a..0x0d`,
  `0x1b`, `0x1c`, `0x1f`, `0x45`, `0x86`, `0x88`, `0xfe`, `0xff`.

Ein während des vollständigen InfoHub-Laufs beobachtetes `0x19` belegt die
Änderung und ihren Wert. Sein Ausbleiben belegt nur, dass InfoHub den Wert in
diesem Capture nicht änderte. Es liest weder den zuvor bestehenden Wert noch
den internen Countdown `0x001315c4`; dessen Wandzeiteinheit kann ein Wire-
Capture höchstens indirekt eingrenzen.

### 6.7 Ereignistimeline und Gültigkeitskriterien

Die Abschlussauswertung enthält eine nach Zeit sortierte Tabelle aus:

```text
InfoHub-Start / UI-Aktion (Notiz)
alle Interface-0-OUT/IN-Befehle
erstes Interface-1-0x08-Segment
jedes Folgesegment
Completion des letzten OUT-URB
jedes Interface-1-IN, insbesondere 08 81
sichtbarer Commit beziehungsweise Timeout (Notiz/Video)
weitere USB-Ereignisse und Capture-Ende
```

Ein minimaler Referenzlauf ist nur akzeptiert, wenn:

- der Descriptor im Capture `0b05:1c7b` und das reale v49-Gerät eindeutig
  belegt;
- keine Payloadkürzung, kein Drop und kein fehlerhafter Ziel-URB vorliegt;
- genau ein vollständiger, geordneter `0x08`-Transfer vorhanden ist;
- jedes EP-`0x03`-OUT exakt 1024 Byte und der letzte Block vollständig ist;
- SOI, syntaktisches EOI und der gesamte Suffix bestimmbar sind;
- alle EP-`0x84`-IN-Reports vollständig 16 Byte besitzen;
- kein autonomer Retry, kein Firmwareupdate und kein gefährlicher Begleitpfad
  beobachtet wurde.

Falls InfoHub beim Start zusätzliche `0x08`-Transfers sendet, bleibt der
Capture für Herstellersequenz und Timeout wertvoll, erfüllt aber nicht das
strenge Ein-Transfer-Kriterium. Nichts wird aus dem Original entfernt, um ihn
künstlich gültig erscheinen zu lassen.

## 7. Vorbereitetes Offline-Werkzeug

`research/tools/analyze_lcd_reference_capture.py` verarbeitet ausschließlich
gespeicherte klassische USBPcap-pcap- oder pcapng-Dateien mit Linktyp 249. Es
verwendet nur die Python-Standardbibliothek, kennt keinen Live-Capture-Modus,
öffnet kein USB-/HID-Gerät und importiert keine entsprechende Bibliothek.

Beispiel nach einem späteren Capture:

```text
python3 -B research/tools/analyze_lcd_reference_capture.py \
  capture-original.pcapng \
  --out-dir /tmp/tuf-aio-reference-analysis
```

Bei fehlendem injiziertem Device Descriptor kann die aus Wireshark ermittelte
Adresse ausdrücklich angegeben werden:

```text
python3 -B research/tools/analyze_lcd_reference_capture.py \
  capture-original.pcapng --device BUS:ADDRESS
```

Das Werkzeug:

- erkennt `0b05:1c7b` aus Device Descriptors oder einer expliziten Adresse;
- paart USBPcap-Submit/Completion über IRP-ID;
- gruppiert Endpoints und beide Interfaces;
- dekodiert alle Controlwords und rekonstruiert `0x08`;
- parst JPEG bis zum syntaktischen EOI;
- schreibt rekonstruiertes JPEG und Suffix getrennt;
- gibt sämtliche EP-`0x84`-Reports und Zeitabstände aus;
- rekonstruiert Interface-0-Transfers und markiert `0x19` sowie gefährliche
  Commands;
- bewertet die formalen Gültigkeitskriterien in `analysis.json`.

Der optionale Host-`usbmon`-Capture der VM ist ein getrenntes Zusatzartefakt.
Er wird mit Wireshark/TShark anhand Bus, Adresse, Endpoint, URB-ID und Payload
verglichen; das vorbereitete Skript verarbeitet bewusst nur die primäre
USBPcap-Struktur.

## 8. Welche Fragen der Capture beantwortet

Bei einem gültigen nativen Lauf werden beantwortet:

1. tatsächliche 1024-Byte-Drahtstruktur auf Interface 1/EP `0x03`, Command an
   Byte 0 und Fehlen eines Draht-Report-ID-Bytes;
2. sämtliche ASUS-`0x08`-Controlwords, `N`, reale Reihenfolge und Anzahl;
3. vollständiger erster und letzter 1020-Byte-Payloadblock;
4. SOI/EOI-Position, tatsächliche JPEG-Eigenschaften und jeder Suffixbyte nach
   EOI;
5. alle realen 16-Byte-IN-Reports des v49-Geräts, `08 81`, alternative Werte
   und deren Abstand zum letzten OUT;
6. alle während derselben InfoHub-Sitzung beobachteten Interface-0-Befehle,
   insbesondere ein mögliches `0x19` samt neuem `config+0x108`-Wert;
7. autonome Retries, Resets/Reenumeration und sichtbares Commitverhalten des
   realen v49-Geräts;
8. ob InfoHub das Eingabe-JPEG unverändert übernimmt oder neu codiert.

Nicht allein durch diesen Wire-Capture beweisbar sind:

- der konkrete erste Nullbyteinhalt im privaten InfoHub-`WriteFile`-Puffer;
  Windows-HID-Semantik verlangt null, auf USB existiert dieses Byte nicht;
- eine allgemeine Paddingregel aus nur einer Restlänge oder die Toleranz
  anderer Suffixe;
- ein interner Decoderabschluss, wenn das Gerät dafür keine spätere
  USB-Nachricht sendet;
- die exakte Wandzeiteinheit von `0x001315c4` oder ein bereits vor Capturebeginn
  gesetzter `config+0x108`-Wert;
- vollständige Gleichheit der nicht beobachtbaren v49-Firmwareinternas mit dem
  statisch analysierten v51-Image.

Damit ist Variante A die geeignete Entscheidungsgrundlage für einen späteren
minimalen JPEG-Test. Variante B kann Bytes, Segmentierung und Nachrichten
ebenfalls klären, ihre Latenzen und Resetbedingungen müssen jedoch als
virtualisiert gekennzeichnet bleiben.
