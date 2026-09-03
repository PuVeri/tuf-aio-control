# Statische Rekonstruktion des InfoHub-LCD-Refreshworkers

Stand: 2026-09-03

## Umfang und Evidenzgrenze

Untersucht wurde ausschließlich der hostseitige LCD-Refreshpfad von
`ASUS InfoHub.exe` 1.0.0.15 und der unmittelbar angebundene Bildpufferpfad in
`XYUI.dll`. Grundlage waren der aktuelle Projektstand, die vorhandene
Senderanalyse und ein reproduzierbarer, read-only Ghidra-Export aus den bereits
analysierten Projekten. Es gab keine Gerätekommunikation, keinen HID-Write,
keinen neuen Live-Test und keine Ausführung des Windows-Programms.

Der Export ist auf das folgende InfoHub-Image festgelegt:

```text
Program:    ASUS InfoHub.exe
SHA-256:    7eeb0c61904a36f8fab3945209d8472088db8b093250387e3b06228b81d356e0
Image base: 00400000
Language:   x86:LE:32:default
```

Die absoluten Adressen und Offsetnamen in diesem Bericht gelten genau für
dieses Image. Host-Eventnummern werden nicht als Geräteopcodes interpretiert.

## 1. Die beiden offenen Adressanker

### 1.1 `0x0040b103`: Startanker im Dialog-Initializer

`0x0040b103` ist kein Funktionseinstieg, sondern liegt in
`FUN_0040ada0`, dem `OnInitDialog`-Pfad des `DeviceMainDlg`. Die einzige
statische Referenz auf den Funktionseinstieg ist der Datenverweis
`0x0052f860`, also ein MFC-Dispatch-/Vtable-Eintrag. Die Funktion hat keinen
fachlichen Rückgabewert (`void`).

Am Anker beginnt exakt die Initialisierung des eingebetteten Timerobjekts bei
`DeviceMainDlg+0x270`:

```text
if DeviceMainDlg+0x278 == 0:
    +0x280 = 12
    +0x27c = 1
    +0x284 = GetTickCount()
    +0x274 = CreateEventW(NULL, TRUE, FALSE, NULL)
    +0x278 = 1
    _beginthreadex(NULL, 0, 0x00425c10,
                   DeviceMainDlg+0x270, 0, NULL)
```

Die refreshrelevanten Callees sind damit `GetTickCount`, `CreateEventW` und
`_beginthreadex`; `0x00425c10` wird an `0x0040b13c` als Threadfunktion
übergeben. `CreateEventW(..., TRUE, FALSE, ...)` erzeugt ein manuell
zurückzusetzendes, anfangs nicht signalisiertes Event. Dieses Event ist kein
Taktgeber und weckt den Worker nicht auf; es signalisiert nur dessen Ende.

Unmittelbar vor diesem Block ruft der Dialog zusätzlich
`XYUI::MDialog::SetMTimer(this, 0x10)` auf. Später setzt er einen weiteren
Fenstertimer mit ID 200 und 20.000 ms. Beide sind von dem explizit erzeugten
12-ms-Threadtimer zu trennen.

Nach dem Threadstart legt der Initializer die Hostereignisse `0x01`, `0x1b`
und `0x14` in die Workerqueue. Ihre belegten Rollen in dieser Startfolge sind:

- `0x01 -> 0x004151d0`: AutoRun-/UI-Konfiguration;
- `0x1b -> 0x004168d0` und danach `0x004152f0`: HID-Neuerkennung,
  Connection-Gate und Wiederherstellung der UI-/Bildkonfiguration;
- `0x14 -> 0x00416de0`: Softwareversions-/Updateprüfung.

Der `0x1b`-Pfad setzt das Connection-Gate und erzeugt weitere Hostereignisse.
Insbesondere ruft `0x004152f0` am Ende `0x00417f50` auf. Dieser Pfad setzt
`DeviceMainDlg+0x8cc = 3` und stellt `0x1c` in die Workerqueue. Das spätere
Ereignis `0x1c` ruft `0x00416a00` auf und sendet vor dem ersten
Leerlauf-Refresh einen Interface-0-Report mit Controlword `12 01 00 80`; sein
erstes Payloadbyte stammt aus `DeviceMainDlg+0x8dc`, das unmittelbar aus der
gespeicherten Einstellung `led_brightness` geladen und auch an
`LEDModeCtrl::SetBrightness` übergeben wird.

Damit existiert eine reale Interface-0-Aktion in der weiteren
Initialisierungsfolge. Sie ist jedoch weder Bestandteil eines einzelnen
`0x08`-Transfers noch als Abschaltung eines geräteinternen Bildproduzenten
belegt. Die Hostherkunft des Payloads stützt eine Helligkeitsrolle; eine darüber
hinausgehende Gerätebedeutung wird nicht festgelegt.

### 1.2 `0x00425c10`: generischer wiederholender Threadtimer

`0x00425c10` ist der Einstieg von `FUN_00425c10`. Direkte Code-Caller gibt es
nicht, weil die Adresse als `_beginthreadex`-Callback übergeben wird. Zwei
Datenreferenzen sind belegt:

- `0x0040b13c` in `FUN_0040ada0`: LCD-/InfoHub-Worker;
- `0x0041f220` in `FUN_0041f1c0`: zweite Verwendung desselben generischen
  Timerhelfers in einer anderen Komponente.

Seine vollständigen Callees sind `_Xtime_get_ticks`, `__allmul`, `__alldiv`,
`Sleep` und `SetEvent`; der eigentliche Callback wird indirekt über den ersten
Vtable-Slot des übergebenen Objekts gerufen. Für das LCD-Objekt verweist der
Vtable-Eintrag `0x0052f820` auf `0x00414ff0`.

Timerrelativ gilt:

| Offset | Bedeutung im LCD-Objekt | Belegter Wert |
| ---: | --- | ---: |
| `+0x00` | Vtable; Slot 0 ist Callback | `0x00414ff0` |
| `+0x04` | Abschluss-Event | manuell, anfangs nicht signalisiert |
| `+0x08` | Run-Flag | `1` beim Start |
| `+0x0c` | Repeat-Flag | `1` |
| `+0x10` | Zielperiode | `12` ms |
| `+0x14` | Thread-Rückgabewert | Startwert von `GetTickCount()` |

Bei `Repeat-Flag == 0` wird der Callback einmal ausgeführt. Im LCD-Fall ist
das Flag eins. Solange das Run-Flag ungleich null ist, misst der Timer die
Laufzeit eines Callbackaufrufs. Ist diese kleiner als 12 ms, schläft er nur
für die Differenz; andernfalls beginnt die nächste Iteration ohne zusätzlichen
Sleep. Nach Schleifenende setzt er das Abschluss-Event und gibt den beim Start
gespeicherten `GetTickCount()`-Wert zurück. Der `_beginthreadex`-Handle und
dieser Returncode werden im LCD-Startpfad nicht gespeichert oder ausgewertet.

`FUN_00425bc0` ist der zugehörige Stop-/Wait-Helfer: Run-Flag auf null setzen,
höchstens 1000 ms auf das Abschluss-Event warten, Eventhandle schließen und
nullen. Sein einziger statisch direkter Caller ist `0x0041f14f` für die andere
Timerinstanz. Im begrenzten LCD-Pfad wurde kein Call dieses Helfers gefunden.
Auch `DeviceMainDlg`-Teardown `0x0040abf0` enthält keinen Aufruf und löscht das
LCD-Run-Flag nicht. Belegt ist daher der Start und die generische Stopmechanik;
eine explizite saubere Stopkante für genau diese LCD-Instanz ist nicht belegt.
Die praktische Bindung an die InfoHub-Prozess-/Dialoglebensdauer ist stark
gestützt, aber aus diesen Funktionen allein nicht als vollständiger
Lifecycle-Vertrag beweisbar.

## 2. `0x00414ff0` als Zustandsautomat

`0x00414ff0` ist selbst keine Dauerschleife. Es ist ein einzelner
Callbackschritt; die Rückkante liegt in `0x00425c10`.

```text
START: OnInitDialog, falls Run-Flag == 0
  -> Threadtimer mit Zielperiode 12 ms
  -> je Iteration indirekter Aufruf von 0x00414ff0

0x00414ff0:
  wenn Eventqueue nicht leer:
      genau ein Hostereignis entfernen
      dessen Handler ausführen
      ohne JPEG-Aufruf zurückkehren
  sonst:
      timeBeginPeriod(1)
      0x00416bc0(DeviceMainDlg)
      falls seit +0x4bc mindestens 2000 ms vergangen:
          Zeitstempel aktualisieren
          0x0040cf00(DeviceMainDlg)
      timeEndPeriod(1)
      zurückkehren

0x00425c10:
  falls Callbackdauer < 12 ms: Restzeit schlafen
  falls Run-Flag != 0: Rückkante
  sonst: Abschluss-Event setzen und Thread beenden
```

Die Eventqueue liegt workerrelativ bei `+0x210/+0x214`, entsprechend
`DeviceMainDlg+0x480/+0x484`. Pro Iteration wird höchstens ein Eintrag
entfernt. Solange sie nicht leer ist, gibt es auf diesem Tick keinen JPEG-
Transfer. Die Dispatchfälle sind `0x01`, `0x14..0x1f`; ohne weiteren Beleg
sind dies ausschließlich Hostevent-IDs.

Der 2000-ms-Zweig `0x0040cf00` ist kein LCD-Transporttakt. Er erfasst und
verteilt Hardware-/Monitoringwerte, unter anderem über
`SysInfoCtrl` und `LEDModeCtrl::SetHardWareInfo`. Er läuft höchstens einmal pro
zwei Sekunden und erst nach dem JPEG-Sender auf dem betreffenden Idle-Tick.
Seine Werte können einen später von XYUI gerenderten Sensor-/Overlayframe
verändern, lösen aber in `0x0040cf00` selbst keinen HID-Write aus.

### Suppression- und Sendegates

Ein erneuter Aufruf von `0x00416bc0` bedeutet noch nicht zwingend einen
Transfer. Der Sender schreibt nur, wenn alle folgenden Bedingungen erfüllt
sind:

1. die Workerqueue ist beim Callbackstart leer;
2. `DeviceMainDlg+0x4a8 != 0`: `0x004168d0` hat sowohl HID1 als auch HID2
   erfolgreich zugeordnet;
3. `DeviceMainDlg+0x4b0 == 0`: keine Power-Suppression;
4. `LEDModeCtrl::GetLEDData` liefert eine positive gespeicherte JPEG-Länge;
5. der Thread läuft noch.

`DeviceMainDlg+0x4b0` ist genauer als bislang dokumentiert auflösbar.
`FUN_00410fe0` leitet Windows-Nachricht `0x0218` (`WM_POWERBROADCAST`) an
`FUN_004119b0` weiter. Dort setzt `wParam == 4` (`PBT_APMSUSPEND`) das Gate
auf eins; `wParam == 7` oder `0x12` (Resume-Ereignisse) setzen es auf null.
Die normale Sichtbarkeit des InfoHub-Fensters, der ausgewählte Tab und der
konkrete Bildmodus sind keine direkten Transportgates.

Der Sender ist synchron. Jeder komplette JPEG-Transfer läuft innerhalb eines
Callbackaufrufs. Bei einem fehlgeschlagenen Segment wartet InfoHub 100 ms und
versucht genau dieses Segment einmal erneut; ein zweiter Fehlschlag beendet
den Bildtransfer und löst den bereits dokumentierten Interface-0-Fehlerpfad
`FF 01 00 00` aus. Diese Fehlerwartezeit verlängert die Iteration, statt einen
zweiten parallelen Refresh zu erzeugen.

## 3. Exakte Refreshstrategie

### Transporttakt

Die Zielperiode beträgt **12 ms pro Callbackstart**, entsprechend nominell
etwa **83,3 Workeraufrufen pro Sekunde**. Das ist weder eine harte Obergrenze
noch eine garantierte 83,3-Hz-JPEG-Rate:

- ein Queueereignis verbraucht einen Tick ohne JPEG;
- ein fehlendes JPEG oder ein Gate führt zu keinem Write;
- dauert der synchrone vollständige Transfer weniger als 12 ms, schläft der
  Timer bis zum Periodenende;
- dauert er mindestens 12 ms, startet die nächste Iteration unmittelbar nach
  Rückkehr, also mit einer tatsächlichen Periode von mindestens der
  Callback-/Transferdauer;
- Scheduling und ein möglicher 100-ms-Fehlerretry verlängern sie weiter.

Der bislang offene 2000-ms-Wert ist ausschließlich das Monitoringintervall,
nicht der JPEG-Refresh.

### Wiederverwendung und Neuerzeugung des JPEGs

`XYUI.dll:0x10052030`, `LEDModeCtrl::GetLEDData`, erzeugt kein JPEG. Es nullt
den InfoHub-Zielpuffer, sperrt die Critical Section bei `LEDModeCtrl+0x180`
und kopiert bei positiver Länge die aktuellen Bytes aus
`LEDModeCtrl+0x1b8`; die Länge kommt aus `+0x1bc`. Weder Puffer noch Länge
werden dabei konsumiert oder gelöscht.

Folglich sendet jeder berechtigte Idle-Tick das **aktuell gespeicherte,
bereits encodierte JPEG erneut**. Zwischen zwei Producerupdates sind es
dieselben Bytes. Eine JPEG-Neuerzeugung vor jedem Transportrefresh findet
nicht statt.

Die Bildproduktion besitzt einen getrennten Takt:

- `XYUI.dll:0x10058100`, `LEDModeCtrl::OnControlTimer`, prüft über
  `QueryPerformanceCounter` das Feld `LEDModeCtrl+0x2a0`;
- der Konstruktor initialisiert dieses Intervall mit 30 ms;
- für GIF liest `SetFileImage` die Framedauer und begrenzt das Intervall nach
  unten auf 16 ms;
- für andere Medien können quellenspezifische Intervalle gesetzt werden;
- nach Fortschalten von Datei-/Frame-/Auswahlzustand ruft der Pfad bei
  `LEDModeCtrl+0x1a0 == 1` `DrawHideControl` bei `0x10052930` auf;
- `DrawHideControl` rendert den aktuellen 320x320-Inhalt einschließlich
  Datei, Clock und Overlays und encodiert ihn erneut als JPEG.

Bei einem statischen Einzelbild bleibt die visuelle Quelle gleich. XYUI kann
sie im Producer-Takt erneut rendern und encodieren; der Transport benötigt
dies aber nicht und sendet in jedem Fall den zuletzt fertig gespeicherten
JPEG-Puffer. Bei GIF/Video wechselt der Producer den aktuellen Frame, während
der Transportworker stets den jeweils letzten vollständigen JPEG-Stand holt.

Damit gilt für die Modi:

- Der Transportrefresh ist nicht auf einen bestimmten Bild-, GIF-, Clock-
  oder Sensormodus beschränkt.
- Er läuft solange der InfoHub-Worker aktiv ist und die oben genannten Gates
  offen sind.
- UI-/Datei-/Animationszustand bestimmt den Inhalt des gespeicherten JPEGs,
  nicht den 12-ms-Sendemechanismus.
- Sensorwerte werden hostseitig höchstens alle 2000 ms erneuert und erst über
  einen späteren XYUI-Renderlauf in das JPEG übernommen.

## 4. Interface 0 und der interne Default-Produzent

Die Herstellerstrategie entspricht nach der geforderten Trennung
**Variante A**:

> InfoHub hält den aktuellen Hostframe sichtbar, indem es vollständige
> Interface-1-`0x08`-JPEG-Transfers wiederholt.

Variante B ist nicht belegt. Die statische Writerübersicht enthält zwar
separate Interface-0-Aktionen:

- während der Initialisierung gelangt die Workerqueue, wie oben rekonstruiert,
  einmal zu `12 01 00 80` mit dem gespeicherten `led_brightness`-Byte;
- andere UI-/Zustandsaktionen können `0x10`, `0x12` oder den separaten
  Sleep-Pfad `0x1f` senden;
- nach zwei fehlgeschlagenen HID2-Writes kann `FF 01 00 00` folgen.

Keiner dieser Befunde zeigt eine Deaktivierung des internen Boot-/
Objektproduzenten. Insbesondere gibt es keinen Interface-0-Befehl unmittelbar
vor oder nach **jedem** erfolgreichen JPEG-Refresh, kein hostseitiges
„bereits committed“-Protokoll und keinen Interface-1-IN-Read. Der reine Stop-
Helfer `0x00425bc0` sendet ebenfalls keinen Gerätebefehl. Die beim Start
beobachtete `0x12`-Aktion reicht ohne eine belegte Gerätewirkung nicht aus,
Variante C zu behaupten.

Der Hostpfad belegt damit ein fortlaufendes Überstimmen, nicht ein Abschalten
des internen Produzenten. Dass derselbe Frame durch wiederholte spätere
Commits sichtbar gehalten wird, ist direkt aus Worker, Sender und nicht
konsumierendem JPEG-Puffer ableitbar.

## 5. Bedeutung für den beobachteten Default-Fallback

Der eigene Linux-Pfad überträgt genau einen Frame. Dieser wird auf dem realen
v49-Gerät erfolgreich decodiert und sichtbar committed. Er behauptet das
Display danach nicht erneut.

Die vorhandene Deviceanalyse belegt für v51, dass ein erfolgreicher
`0x08`-Frame nicht durch einen eigenen Displaytimeout zurückgerollt wird,
sondern bis zum nächsten Ringcommit sichtbar bleibt. Der aktive interne
Boot-/Objektproduzent kann einen solchen späteren Commit liefern; `0x08`
deaktiviert ihn nicht. Das beobachtete spätere ASUS-Defaultbild passt daher am
engsten zu einem neuen internen Framecommit.

InfoHub verhindert denselben sichtbaren Endzustand nicht durch einen
belegten Holdmodus. Es gewinnt die Display-Ownership praktisch immer wieder
zurück, indem es bei jeder berechtigten Idle-Iteration erneut `0x08` sendet.
Unser Default-Fallback ist deshalb kein Hinweis auf einen fehlgeschlagenen
ersten JPEG-Commit oder eine nicht implementierte GIF-Dekodierung. Er ist die
erwartbare Folge davon, dass unser Einmalpfad im Gegensatz zu InfoHub keinen
zeitlichen Ownership-/Refreshmechanismus besitzt.

Diese Rekonstruktion ist noch keine Freigabe für einen eigenen periodischen
Sender. Vor einer Implementierung müssen der wiederholte Transferpfad gegen
Queue, Decoder-Lease, Transferdauer, Fehlerabbruch und die v49-Laufzeitgrenze
gesondert sicherheitsbewertet werden. Eine echte GIF-Animation erfordert
zusätzlich Producer-/Frametiming und eine kontrollierte Stopstrategie.

## 6. Reproduzierbarer Export

`research/ghidra-scripts/ExportInfoHubRefreshTriage.java` bleibt sinnvoll und
wurde für diesen begrenzten Pfad vervollständigt. Das Skript:

- validiert Programmname, SHA-256 und Image-Base vor dem Export;
- verlangt genau einen Ausgabepfad und überschreibt keine vorhandene Datei;
- bricht ab, wenn ein Target keiner Funktion zugeordnet werden kann;
- exportiert Targets, Caller, Callees, Instruktionen samt Referenzen und
  Decompilertext;
- schreibt ausschließlich die angegebene Textausgabe und ist für
  `-readOnly -noanalysis` vorgesehen.

Der aktuelle Targetsatz dokumentiert und exportiert:

```text
0040b103  Dialoginitialisierung und Startanker
0040abf0  Dialogteardown/Lifetime
00410fe0  Window-Message-/WM_POWERBROADCAST-Dispatcher
004119b0  Power-Suppression-Gate
0040cf00  2000-ms-Monitoringtask
004148d0  separater Interface-0-0x1f-Sleep-Pfad
00414ff0  LCD-Worker
004151d0  initiales Hostevent 0x01
004152f0  Konfigurationsaufbau nach HID-Erkennung
004168d0  Hostevent 0x1b/HID-Erkennung und Connection-Gate
00416a00  Hostevent 0x1c/Interface-0-0x10-/0x12-Pfad
00416bc0  Interface-1-0x08-JPEG-Sender
00416de0  initiales Hostevent 0x14
00417f50  Bild-/UI-Konfiguration und Queueing von 0x1c
00425bc0  generischer Stop-/Wait-Helfer
00425c10  generischer Threadtimer und Rückkante
```

Beispiel für einen reproduzierbaren read-only Lauf:

```text
refresh_tmp=$(mktemp -d /tmp/tuf-infohub-refresh.XXXXXX)
env XDG_CONFIG_HOME="$refresh_tmp/config" \
  /home/l/HeartdriveLAB/shared/tools/ghidra/ghidra_12.1_PUBLIC/support/analyzeHeadless \
  research/ghidra-projects infohub-1.0.0.15-ghidra12-1 \
  -process "ASUS InfoHub.exe" -readOnly -noanalysis \
  -scriptPath research/ghidra-scripts \
  -postScript ExportInfoHubRefreshTriage.java "$refresh_tmp/infohub-refresh.txt"
```

Die Exportdatei ist ein temporäres Analyseprodukt und wird nicht im
Repository benötigt; Bericht und gegatetes Skript halten den reproduzierbaren
Befund fest.

## Ergebnis

Die zwei offenen Anker sind geschlossen. `0x0040b103` startet innerhalb des
Dialog-Initializers einen wiederholenden 12-ms-Threadtimer;
`0x00425c10` stellt dessen Rückkante, Laufzeitkompensation und Endsignal bereit.
`0x00414ff0` verarbeitet entweder genau ein Hostereignis oder sendet im
Leerlauf den zuletzt gespeicherten JPEG-Puffer erneut. JPEG-Transport und
JPEG-Produktion sind getrennte Takte. InfoHub überstimmt den weiterhin nicht
belegt deaktivierten internen Produzenten durch fortlaufende `0x08`-Commits.
Das erklärt, warum ein eigener einmaliger Frame später dem ASUS-Defaultbild
weicht.
