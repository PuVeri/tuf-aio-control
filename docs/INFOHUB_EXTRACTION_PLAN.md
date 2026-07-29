# Sicherer Extraktionsplan für den ASUS-InfoHub-Installer

Stand: 2026-07-29, Europe/Berlin.

Ziel ist die vollständige, rein statische Extraktion von
`research/extracted/infohub-v1.0.0.15/ASUS-InfoHub-TUF-1.0.0.15.exe`.
Die ASUS-Datei wird dabei nur als Eingabe eines Extraktors gelesen und niemals
als Programm gestartet.

## Ausgangsdatei und bestätigte Formatgrenzen

| Merkmal | Beobachteter Wert |
| --- | --- |
| Dateigröße | 90.476.632 Byte |
| SHA-256 | `b7d867a13e8918be09675883330a801c6e3dfff2568afd32c3c18193e0ef9164` |
| PE-Typ | PE32 GUI, Intel i386, 11 Sektionen |
| Inno-Kennung | `Inno Setup Setup Data (6.4.0.1)` |
| Inno-Kennung im PE-Stub | Dateioffset 698.348 |
| weitere Inno-Kennung | Dateioffset 89.366.446 |
| PE-Overlay laut 7-Zip | Offset 883.200, Länge 89.580.200 Byte |
| Ressourcennachlauf laut 7-Zip | `.rsrc_1`, Offset 882.748, Länge 452 Byte |
| Authenticode-Bereich | Offset 90.463.400, Länge 13.232 Byte |

Der PE-Overlaybereich endet rechnerisch bei Offset 90.463.400 und damit genau
am Beginn des Authenticode-Bereichs. Das bestätigt seine äußere Lage, aber
nicht, dass der gesamte Overlaybereich ein einzelner komprimierter Datenstrom
ist. Die interne Dateiliste, Datenblockgrenzen, Kompressionsparameter und
Prüfsummen können erst von einem 6.4-kompatiblen Inno-Parser zuverlässig
bestimmt werden.

## Geprüfte vorhandene Werkzeuge

| Werkzeug | Version | Ergebnis | Sicherheitsbewertung |
| --- | --- | --- | --- |
| `innoextract` | Fedora `1.9-19.fc44`; Programm meldet 1.9 und Support bis 6.0.5 | Erkennt 6.4.0.1, warnt über unbekannte Headerfelder und bricht beim Setup-Header ab | sicher und statisch, für diesen Installer nicht kompatibel |
| `7z` | `26.02-1.fc44` | Listet PE-Sektionen, Ressourcen, Zertifikat und den rohen Overlaybereich `[0]`; keine Inno-Dateiliste | sicher für PE-/Ressourcenanalyse, keine vollständige Inno-Extraktion |
| `lsar`/`unar` | RPM `1.10.8-15.fc44`, Programme melden 1.10.7 | Format wird nicht erkannt | sicher, aber ungeeignet |
| GNU `objdump`/`objcopy` | binutils `2.46.1-1.fc44` | PE-Sektionen, Imports und Ressourcenbereiche zugänglich | sicher für PE-Ebene; keine Inno-Containerlogik |
| `strings` | GNU binutils | Bestätigt Inno-Version und eingebettete Kennungen | nur Metadatengewinn |

Nicht installiert sind `cmake`, ein C++-Compiler, Free Pascal/Delphi,
`cabextract`, `wrestool`, `binwalk` und `unblob`. Keines davon würde allein
die fehlende Inno-6.4-Headerunterstützung lösen.

## Aktueller Supportstand

### Fedora

Fedora 44 und Fedora Rawhide führen weiterhin `innoextract 1.9`; die
Paketänderungen sind Rebuilds und keine neue Upstream-Version. Eine Installation
aus den bereits eingerichteten Fedora-Quellen würde daher keine zusätzliche
6.4-Kompatibilität bringen:

<https://packages.fedoraproject.org/pkgs/innoextract/innoextract/>

### innoextract-Upstream

Der aktuelle Upstream-Stand nennt Unterstützung bis Inno Setup 6.3.3. Damit
reicht auch der gegenwärtige Entwicklungszweig nicht für eine verlässlich
vollständige 6.4.0.1-Extraktion:

<https://github.com/dscharrer/innoextract>

`innoextract` ist grundsätzlich die bevorzugte Linux-Architektur: Open Source,
zlib-Lizenz, native Ausführung und keine Ausführung eingebetteter Skripte.
Eine lokal gepatchte Variante wäre aber erst nach Codeprüfung,
reproduzierbarem Build und Tests gegen bekannte 6.4-Testinstaller vertretbar.

### innounp

Die gepflegte GPL-Variante von Jürgen Rathlev unterstützt inzwischen Inno
Setup 6.4 und neuere Versionen. Sie kann Dateien auflisten, testen und
extrahieren, ist jedoch mit Delphi als Windows-Konsolenprogramm gebaut:

<https://www.rathlev-home.de/tools/download/innounp.htm>

Unter den aktuellen Vorgaben darf sie auf diesem Linux-System nicht über Wine,
VM oder Emulation ausgeführt werden. Eine Nutzung wäre nur auf einem
vorhandenen nativen Windows-Analysehost oder nach einer geprüften nativen
Portierung zulässig. Dabei würde ausschließlich `innounp`, nicht der
ASUS-Installer, ausgeführt.

## Bewertete Extraktionswege

### A. Aktuelles lokales `innoextract`

Nicht geeignet. Der Parser verliert bereits in den Setup-Headern die
Synchronisation. Eine Extraktion trotz Warnungen wäre nicht vollständig und
könnte Pfade, Größen oder Datenblöcke falsch zuordnen.

### B. 7-Zip-Ressourcen- und Overlayextraktion

Nur teilweise geeignet. PE-Ressourcen und der rohe Overlaybereich ließen sich
in einen neuen Ordner kopieren. Das rekonstruiert aber weder Installationspfade
noch einzelne Nutzdateien und ist deshalb keine vollständige InfoHub-
Extraktion. Der große rohe Block wird nicht vorschnell als bestimmter
Kompressionscontainer bezeichnet.

### C. Manuelle Containeranalyse

Technisch möglich, aber nicht minimal. Sie müsste mindestens folgende Teile
der Inno-6.4-Quellen korrekt nachbilden:

- Setup-Laderoffset und Headerprüfungen,
- serialisierte 6.4-Headerstrukturen und Versionsfelder,
- Datei- und Datenentabellen,
- Slice-/Chunkgrenzen,
- LZMA-, zlib- oder bzip2-Dekompression entsprechend den Headerflags,
- Integritätsprüfung und sichere Pfadnormalisierung.

Manuelles Signature-Carving ohne diese Metadaten kann eingebettete Einzeldateien
finden, belegt aber weder Vollständigkeit noch korrekte Dateigrenzen.

### D. Gepflegtes `innounp` auf nativem Windows

Der derzeit kürzeste bereits implementierte Weg. Vor der Extraktion müssen
Quellarchiv, veröffentlichte Prüfsumme beziehungsweise Signatur und Quellcode
geprüft werden. Danach zunächst nur listen und testen:

```text
innounp.exe -v -m ASUS-InfoHub-TUF-1.0.0.15.exe
innounp.exe -t -m ASUS-InfoHub-TUF-1.0.0.15.exe
```

Erst nach Prüfung aller ausgegebenen Pfade erfolgt die Extraktion in einen
neuen, leeren Zielordner:

```text
innounp.exe -x -m -a -dInfoHub-1.0.0.15-extracted ASUS-InfoHub-TUF-1.0.0.15.exe
```

Kein `-y` verwenden: Ein unerwarteter vorhandener Zielpfad soll zum Abbruch
führen und nicht überschrieben werden.

### E. Native Linux-Portierung oder innoextract-Patch

Langfristig der beste reproduzierbare Repository-Workflow, derzeit aber kein
minimaler Sofortweg. Der aktuelle Rechner besitzt weder Buildsystem noch
Compiler. Außerdem unterstützt der Upstream selbst 6.4 noch nicht. Ein
entsprechender Patch braucht eine gesonderte Code- und Werkzeugfreigabe.

## Empfohlenes Vorgehen

1. Keine partielle 7-Zip-Overlayextraktion als vollständiges Ergebnis
   behandeln.
2. Bevorzugt auf eine geprüfte `innoextract`-Version mit ausdrücklichem
   6.4-Support warten oder einen kleinen, reviewbaren Upstream-Patch erstellen.
3. Falls die Analyse vorher benötigt wird, nach menschlicher Freigabe die
   aktuelle GPL-`innounp`-Version auf einem bereits vorhandenen nativen
   Windows-Analysehost einsetzen. Weder Installer noch extrahierte Dateien
   starten.
4. Erst eine ausführliche Inhaltsliste erzeugen. Absolute Pfade,
   Laufwerkspfade, UNC-Pfade, `..`, Links und Namenskollisionen ablehnen.
5. In einen neuen Zielordner extrahieren, anschließend Anzahl, Typ, Größe und
   SHA-256 jeder Datei inventarisieren.
6. Extrahierte PE-, DLL-, Konfigurations- und Mediendateien ausschließlich mit
   statischen Werkzeugen auf USB/HID, `0b05:1c7b`, MI/COL, Reportgrößen,
   Bildformate und Protokollstrings untersuchen.

## Installations- und Freigabebedarf

Es gibt derzeit **keinen Fedora-Installationsbefehl**, der auf diesem System
eine bestätigte Inno-6.4-Unterstützung bereitstellt. Das bereits installierte

```text
sudo dnf install innoextract
```

würde nur die schon vorhandene Version 1.9 installieren und löst den Blocker
nicht. Der Befehl wurde nicht ausgeführt.

Für den nativen Linux-Quellbau wären mindestens CMake, ein C++-Compiler,
Boost-Entwicklungsdateien und XZ-Entwicklungsdateien nötig; eine Installation
ist erst sinnvoll, wenn ein geprüfter 6.4-fähiger Quellstand feststeht. Dafür
ist eine gesonderte menschliche Freigabe erforderlich. Ebenso benötigen
Download, Prüfung und Ausführung von `innounp` auf einem nativen Windows-Host
eine ausdrückliche Freigabe.

## Ergebnis dieser Untersuchung

Mit den vorhandenen Werkzeugen war keine sichere vollständige Extraktion
möglich. Deshalb wurde kein neuer Unterordner unter `research/extracted/`
angelegt und keine Teilmenge als InfoHub-Nutzdateien ausgegeben. Es wurden
ausschließlich statische Listen-, Header-, String- und Versionsabfragen
durchgeführt. Keine ASUS-Datei wurde ausgeführt und kein USB-/HID-Gerät
geöffnet.

