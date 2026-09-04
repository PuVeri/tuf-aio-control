# Lokale Linux-v0.1-Installation

Stand: 2026-09-04

## Ergebnis und Grenze

Die produktive Laufzeit ist nun vom Entwicklungsrepository getrennt. Dieses
Ticket hat ausschließlich Packaging, Logpfad, Dokumentation und Offline-Tests
verändert. Es wurden weder Benutzerdateien real installiert noch udev-Regeln
aktiviert, Geräte geöffnet, HID-Reports geschrieben oder Live-Tests
ausgeführt. Transportprotokoll und Production-Safety-Gates blieben unverändert.

## Installationslayout

Der bewusste Aufruf von `packaging/manage-user-installation.sh install`
erzeugt im Standardfall:

```text
~/.local/share/tuf-aio-control/
  .managed-installation
  app/
    discover_device.py
    gui_refresh_factory.py
    image_pipeline.py
    lcd_refresh.py
    lcd_runtime_safety.py
    lcd_transport.py
    refresh_diagnostics.py
    system_sensors.py
    telemetry.py
    tuf_aio_gui.py
~/.local/bin/tuf-aio-control
~/.local/share/applications/tuf-aio-control.desktop
~/.config/autostart/tuf-aio-control.desktop  # nur optional
```

Der Dateisatz kommt aus `packaging/runtime-files.txt`. Er enthält weder Tests,
Research, Dokumentation, Captures noch die manuellen HID-Testwerkzeuge. Alle
Dateien sind echte Kopien. Die installierte Anwendung bleibt deshalb
funktionsfähig, wenn HeartdriveLAB verschoben oder nicht eingehängt ist.

## Launcher und Desktopintegration

Der Launcher bestimmt den Programmbaum aus
`${XDG_DATA_HOME:-$HOME/.local/share}` und startet
`app/tuf_aio_gui.py` mit `/usr/bin/python3 -B`. Er reicht Argumente unverändert
weiter, sodass Normalstart und `--background` denselben installierten Prozess
verwenden. Er enthält keinen beim Build eingesetzten Repositorypfad.

Die normale Desktopdatei öffnet die installierte App. Die optionale
Autostartdatei ruft denselben Launcher mit `--background` auf. Beide Dateien
werden mit dem sicheren absoluten Launcherpfad unter `$HOME/.local/bin`
generiert und sind mit einem Verwaltungsmarker versehen. App-Autostart und die
persistente, standardmäßig ausgeschaltete LCD-Autostartoption bleiben getrennt.

## Install-, Update- und Uninstall-Semantik

- `install` prüft Python, PySide6 und Pillow lokal, verweigert vorhandene
  Kernziele und installiert einen vollständigen Programmbaum.
- `update` akzeptiert nur verwaltete Ziele, baut zuerst einen vollständigen
  neuen Programmbaum auf und tauscht dann die alte Kopie aus. Der vorhandene
  Autostartzustand bleibt erhalten; wiederholte Updates erzeugen keine zweite
  Installation.
- `uninstall` entfernt nur verwalteten Programmbaum, Launcher und
  Desktopdateien. QSettings und Logs bleiben bestehen.
- `enable-autostart` und `disable-autostart` ändern nur die verwaltete
  Benutzer-Autostartdatei.

Es existiert kein Purge-Modus. Datenverlust durch einen versehentlichen
Uninstall ist damit ausgeschlossen. Der Installer enthält keine
Privilegieneskalation und berührt `/etc` nicht.

## Runtime-State und Einstellungen

Neue JSONL-Sessions verwenden
`$XDG_STATE_HOME/tuf-aio-control/`. Ist `XDG_STATE_HOME` nicht als absoluter
Pfad gesetzt, fällt die Anwendung auf
`~/.local/state/tuf-aio-control/` zurück. Injizierte temporäre Testpfade bleiben
möglich. Die bestehende Rotation von 2 MiB je Datei, drei Backups und höchstens
20 Runtime-Dateien bleibt unverändert.

QSettings verwendet weiterhin Organisation `HeartDriveLab` und Anwendung
`tuf-aio-control`. Installer und Updater schreiben nicht in diese
Konfigurationsbasis und löschen sie nicht. Weder Runtime-Logs noch
Konfiguration werden in den installierten Programmbaum oder das Repository
geschrieben.

## Abhängigkeiten

Es wurden keine neuen Runtime-Abhängigkeiten eingeführt. Die App benötigt:

- `/usr/bin/python3` und dessen Standardbibliothek,
- PySide6 für GUI, Tray und QSettings,
- Pillow für Bilddecodierung, Komposition und JPEG-Erzeugung.

Offline geprüft wurden Python 3.14.7, PySide6 6.11.2 und Pillow 12.3.0. Die
beiden Python-Pakete sind in `packaging/runtime-requirements.txt` fixiert. Der
Installer lädt oder installiert sie nicht, sondern prüft nur ihre vorhandene
Importierbarkeit durch `/usr/bin/python3`.

## Getrennte udev-Installation

`packaging/99-tuf-aio-control.rules` bleibt unverändert im Repository. Sie
gewährt nur `0b05:1c7b`, Interface 1, Gruppe `input`, Modus `0660` Schreibzugriff;
Interface 0 bleibt bei `0640`, `0b05:19af` bleibt unberührt. Eine spätere Kopie
nach `/etc/udev/rules.d/99-tuf-aio-control.rules` ist eine eigenständige,
explizit zu bestätigende Administratoraktion.

## GIF-Status

GIF kann geladen und vorbereitet werden. Die separate Pipeline kann Frames,
Framedauern und Loop-Metadaten verarbeiten. Eine echte GIF-Liveanimation auf
dem LCD ist dennoch nicht implementiert oder bestätigt. Der aktive v0.1-GUI-
und LCD-Pfad behandelt GIF weiterhin als Standbild und verwendet Frame 0.

## Offline-Prüfung

Die Packaging-Tests installieren ausschließlich unter temporär gesetzten
`HOME`-/XDG-Pfaden. Sie prüfen Dateimanifest, fehlende Symlinks und
Repositoryreferenzen, Launcherargumente, Desktop-/Autostartziele,
wiederholbares Update, bewahrte Settings/Logs, Standard-Uninstall,
Autostartumschaltung, fehlende Privilegieneskalation und die enge udev-Regel.
Zusätzlich werden XDG-State- und Fallback-Logpfad sowie ein injizierter
temporärer Logpfad geprüft. Kein installierter GUI-Prozess wird gestartet.
Die vollständige Offline-Suite bestand mit 210 Tests. `sh -n`, `compileall`,
`desktop-file-validate` für beide erzeugten Dateien und `git diff --check`
waren ebenfalls erfolgreich.
