# Werkzeugplan für die vertiefte statische Extraktion

Stand: 2026-07-29, Europe/Berlin.

Dieser Plan bereitet die vertiefte Extraktion der bereits gesicherten
ASUS-InfoHub- und Firmwarepakete vor. Er autorisiert weder eine
Paketinstallation noch die Extraktion selbst. Die Paketprüfung erfolgte mit
DNF5 ausschließlich gegen bereits auf dem System eingerichtete Repositories.
Es wurde kein `sudo` verwendet und nichts installiert.

## System- und Repositorykontext

- System: Ultramarine Linux 44 (Plasma Edition), Fedora 44-basiert
- Paketverwaltung: DNF5 5.4.2.1
- einschlägige bereits aktivierte Quellen:
  - `fedora` — Fedora 44 - x86_64,
    `/etc/yum.repos.d/fedora.repo`
  - `updates` — Fedora 44 - x86_64 - Updates,
    `/etc/yum.repos.d/fedora-updates.repo`
  - `rpmfusion-nonfree` — RPM Fusion for Fedora 44 - Nonfree,
    `/etc/yum.repos.d/rpmfusion-nonfree.repo`

Für den minimalen Plan werden nur Pakete aus dem Fedora-Basisrepository
`fedora` benötigt. RPM Fusion Nonfree ist zwar bereits eingerichtet, wird aber
nicht benötigt.

## Minimal benötigte Werkzeuge

| Werkzeug | Paket | Quelle | verfügbare/installierte Version | Zweck | zusätzliche oder proprietäre Quelle |
| --- | --- | --- | --- | --- | --- |
| `innoextract` | `innoextract` | `fedora` | `1.9-19.fc44.x86_64`, nicht installiert | Inno-Setup-Inhaltsliste und Extraktion des InfoHub-Installers ohne dessen Ausführung | nein; zlib-Lizenz, offizielles Fedora-Paket |
| `lsar`, `unar` | `unar` | `fedora` | RPM `1.10.8-15.fc44.x86_64`, bereits installiert; Programme melden `1.10.7` | RARv5-Inhaltsliste, Integritätstest und reine Extraktion | nein; Fedora-Paketbeschreibung nennt RARv5 ausdrücklich, LGPLv2+ |

`unar` ist damit das empfohlene RAR5-fähige reine Extraktionswerkzeug.
Proprietäres `unrar` ist für diesen Plan nicht erforderlich.

### Minimaler Installationsbefehl

Auf dem aktuellen System fehlt nur `innoextract`:

```text
sudo dnf install innoextract
```

Dieser Befehl ist lediglich für eine spätere menschlich freigegebene
Installation dokumentiert. Er wurde nicht ausgeführt.

Für eine reproduzierbare Einrichtung auf einem vergleichbaren Fedora-44-System,
auf dem `unar` noch fehlt:

```text
sudo dnf install innoextract unar
```

## Bewertete Alternativen

| Werkzeug | Paket | Quelle | Version | Bewertung | proprietäre oder zusätzliche Quelle |
| --- | --- | --- | --- | --- | --- |
| `unrar` | `unrar` | `rpmfusion-nonfree` | `7.1.7-3.fc44.x86_64` | RAR5-fähig, aber unnötig, weil das freie und bereits installierte `unar` genügt | ja: RPM Fusion Nonfree; bereits eingerichtet, Paketlizenz laut DNF „Freeware with further limitations“ |
| `unrar`-Wrapper | `unrar` | `fedora` | `0.3.3-2.fc44.x86_64` | Wrapper für `unrar-free`; kein Vorteil gegenüber dem ausdrücklich RARv5-fähigen `unar` | nein, aber nicht empfohlen |
| `bsdtar` | `bsdtar` | `updates` | `3.8.7-1.fc44.x86_64` | allgemeines Archivwerkzeug; für diesen RAR5-Fall nicht nötig | nein |

Die Empfehlung vermeidet proprietäre Werkzeuge und benötigt keine neue
Paketquelle.

## Optionale Werkzeuge

| Werkzeug | Paket | Quelle | Version | Zweck | zusätzliche oder proprietäre Quelle |
| --- | --- | --- | --- | --- | --- |
| `cabextract` | `cabextract` | `fedora` | `1.11-10.fc44.x86_64` | statisches Auflisten und Extrahieren eingebetteter Microsoft-CAB-Dateien, falls solche nach der ersten Extraktion gefunden werden | nein |
| `wrestool` | `icoutils` | `fedora` | `0.32.3-20.fc44.x86_64` | Auflisten und Extrahieren von PE-Ressourcen wie Versionsdaten, Manifesten, Icons und Binärressourcen | nein |

Beide sind derzeit nicht installiert. Sie sind für die erste sichere
Extraktionsstufe nicht nötig und sollen nur nach einem konkreten Fund
nachinstalliert werden:

```text
sudo dnf install cabextract icoutils
```

Auch dieser Befehl wurde nicht ausgeführt.

## Erneute Integritätsprüfung der Originale

Die Originaldateien wurden am 2026-07-29 erneut ausschließlich gelesen:

| Originaldatei | lokal berechneter SHA-256 | Ergebnis |
| --- | --- | --- |
| `research/downloads/original/ASUS_InfoHub_Software_TUF_GAMING_LC_III_360_ARGB_LCD_v1.0.0.15.zip` | `0d7124d700b07d1f49315d77aa15473f01c42c1492f2e8cece845f19c32d2a21` | stimmt mit Manifest und ASUS-Wert überein |
| `research/downloads/original/ASUS_InfoHub_Firmware_TUF_GAMING_LC_III_360_ARGB_LCD_v51.rar` | `267b1477374d28fca01be92b2ff11748591560d30c1a1392bf9d06493a43bfd8` | stimmt mit Manifest und ASUS-Wert überein |

Die Archive wurden nicht verändert, überschrieben, erneut extrahiert oder
ausgeführt.

## Sicherheitsgrenzen

- Installation und Extraktion benötigen jeweils eine neue ausdrückliche
  menschliche Freigabe.
- Keine ASUS-EXE, DLL, MSI, Skriptdatei oder Firmwarekomponente ausführen.
- Kein Wine, keine VM und keine Emulation verwenden.
- Originale unter `research/downloads/original/` nur lesend öffnen.
- Vor jeder Extraktion zuerst eine Inhaltsliste erzeugen und separat unter
  `research/reports/` sichern.
- Absolute Pfade, Windows-Laufwerkpfade, UNC-Pfade, `..`-Komponenten,
  symbolische Links und sonstige Ausbrüche aus dem Zielverzeichnis ablehnen.
- Für jede Stufe einen neuen, leeren, eindeutig benannten Unterordner unter
  `research/extracted/` verwenden.
- Niemals erzwungen überschreiben. Bei vorhandenen Zielen abbrechen; bei
  `unar` später ausdrücklich `-force-skip` verwenden.
- Keine rekursive automatische Extraktion verschachtelter Archive; jede Stufe
  separat inventarisieren und prüfen.
- Nach jeder Extraktion Dateitypen, Größen und SHA-256-Prüfsummen erfassen,
  bevor eine weitere Stufe geöffnet wird.
- Keine USB-/HID-Gerätepfade öffnen und keinerlei Daten oder Firmware an das
  Gerät senden.
- `package.json` und `package-lock.json` unverändert lassen.

## Vorgesehene Extraktionsschritte nach Freigabe

Die folgenden Befehlsformen sind ein Plan, keine aktuelle Ausführung.
Zielverzeichnisse müssen unmittelbar vorher als neu und leer bestätigt werden.

### 1. InfoHub-Inno-Setup

1. SHA-256 des Original-ZIP und des bereits abgeleiteten Installers erneut
   prüfen.
2. Mit `innoextract --list` ausschließlich die Inhaltsstruktur des
   `ASUS-InfoHub-TUF-1.0.0.15.exe` erfassen.
3. Die Liste manuell und automatisiert auf unsichere Pfade und Links prüfen.
4. Einen neuen Zielordner, beispielsweise
   `research/extracted/infohub-inno-v1.0.0.15/`, anlegen.
5. Mit `innoextract --extract --output-dir <neuer-zielordner> <installer>`
   ausschließlich dorthin extrahieren.
6. Die extrahierten Dateien mit `find`, `file`, `stat` und `sha256sum`
   inventarisieren. Nichts davon ausführen.

### 2. Firmware-RAR5

1. SHA-256 des Original-RAR erneut prüfen.
2. Mit `lsar -L -no-recursion <rar>` eine ausführliche, nicht rekursive
   Inhaltsliste erfassen; optional mit `lsar -t` die Archivinhalte testen.
3. Pfade und Eintragstypen wie oben prüfen. Bei Unsicherheit abbrechen.
4. Einen neuen Zielordner, beispielsweise
   `research/extracted/firmware-v51/`, anlegen.
5. Mit
   `unar -no-recursion -force-skip -output-directory <neuer-zielordner> <rar>`
   ausschließlich dorthin extrahieren.
6. Alle Ergebnisse inventarisieren und hashen. Eine gefundene Firmware-Updater-
   EXE nur statisch untersuchen und niemals starten.

### 3. Optionale Folgestufen

- Nur bei tatsächlich gefundenen CAB-Dateien zunächst `cabextract -l`
  verwenden, Pfade prüfen und danach in einen neuen Unterordner extrahieren.
- Mit `wrestool -l` PE-Ressourcen zunächst nur auflisten; benötigte Ressourcen
  als separate abgeleitete Dateien unter `research/extracted/` sichern.
- Weitere verschachtelte Archive jeweils als eigene, erneut freizugebende
  Extraktionsstufe behandeln.

Nach der Werkzeuginstallation ist vor jeder Extraktion erneut anzuhalten, falls
Werkzeugausgabe, Dateipfade oder Formate von diesem Plan abweichen.
