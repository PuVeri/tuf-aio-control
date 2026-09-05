# Lokale Linux-v0.1-Installation

Die produktive Anwendung wird als eigenständige Kopie in XDG-Benutzerpfade
installiert. Sie benötigt danach weder das HeartdriveLAB-Repository noch einen
Symlink dorthin. Der Installer verändert keine udev-Regeln und benötigt keine
Root-Rechte.

## Runtime-Abhängigkeiten

Die Laufzeit besteht aus `/usr/bin/python3`, `PySide6` und `Pillow`; alle
weiteren Python-Imports stammen aus der Standardbibliothek oder den elf in
`runtime-files.txt` aufgeführten Projektmodulen. Test-, Forschungs- und
Dokumentationsdateien sowie die Hardware-Testprogramme werden nicht kopiert.

Der gegenwärtig offline geprüfte Satz ist Python 3.14.7, PySide6 6.11.2 und
Pillow 12.3.0. Die beiden Python-Pakete stehen in
`runtime-requirements.txt`. Sie werden bewusst nicht vom App-Installer aus dem
Netz geladen. Sie müssen vorher für `/usr/bin/python3` über die
Linux-Distribution oder, sofern die Distribution Benutzerpakete erlaubt, so
bereitgestellt werden:

```text
/usr/bin/python3 -m pip install --user -r packaging/runtime-requirements.txt
/usr/bin/python3 -c 'import PIL, PySide6; print(PIL.__version__, PySide6.__version__)'
```

Der Installer führt nur den zweiten, rein lokalen Importcheck aus.

## Installieren und aktualisieren

Aus dem Entwicklungsrepository:

```text
packaging/manage-user-installation.sh install
packaging/manage-user-installation.sh install --autostart
packaging/manage-user-installation.sh update
packaging/manage-user-installation.sh uninstall
```

`install` verweigert vorhandene Zielpfade. `update` akzeptiert nur eine durch
diesen Installer markierte Installation, ersetzt den Programmbaum durch einen
frisch erzeugten, vollständigen Stand und aktualisiert Launcher und
Desktopdateien. Ein vorhandener verwalteter Login-Autostart bleibt beim Update
aktiv. Alternativ lässt er sich getrennt schalten:

```text
packaging/manage-user-installation.sh enable-autostart
packaging/manage-user-installation.sh disable-autostart
packaging/manage-user-installation.sh autostart-status
```

Die Statusabfrage gibt exakt `enabled` oder `disabled` aus. Wiederholtes
Aktivieren und Deaktivieren ist idempotent. `install` aktiviert Autostart ohne
das ausdrücklich angegebene `--autostart` nicht. `update` erhält einen
aktivierten oder deaktivierten Zustand; `--autostart` ist dabei eine explizite
Aktivierungsentscheidung.

Das resultierende Standardlayout ist:

```text
~/.local/share/tuf-aio-control/app/       kopierte Python-Laufzeit
~/.local/bin/tuf-aio-control              ausführbarer Launcher
~/.local/share/applications/tuf-aio-control.desktop
~/.config/autostart/tuf-aio-control.desktop   optional
~/.local/state/tuf-aio-control/           Runtime-/Diagnoselogs
```

`XDG_DATA_HOME`, `XDG_CONFIG_HOME` und `XDG_STATE_HOME` ersetzen die
entsprechenden Standardbasen. Der Launcher verwendet ebenfalls
`XDG_DATA_HOME` und reicht alle Argumente weiter. Damit funktionieren sowohl
`tuf-aio-control` als auch `tuf-aio-control --background` ohne absoluten Pfad
ins Entwicklungsrepository.

`uninstall` entfernt ausschließlich die markierte Anwendung, den Launcher und
die beiden verwalteten Desktopdateien. QSettings unter der XDG-Konfigurations-
basis (Organisation `HeartDriveLab`, Anwendung `tuf-aio-control`) und Logs
unter der XDG-State-Basis bleiben erhalten. Einen automatischen Purge gibt es
absichtlich nicht.

## Desktop- und LCD-Autostart

Der optionale Desktop-Autostart ruft den installierten Launcher mit
`--background` auf. Er startet den Tray-Prozess, nicht automatisch den
LCD-Refresh. Dafür existiert die getrennte, standardmäßig ausgeschaltete
Anwendungsoption `LCD beim Programmstart automatisch starten`. Auch bei deren
Aktivierung bleiben sämtliche Production-Safety-Gates aktiv; es gibt keinen
Retry oder Reconnect.

Ein per-user Kernel-Lock wird vor `QApplication` erworben. Läuft bereits eine
Instanz, endet ein weiterer normaler oder durch den Desktop-Autostart
ausgelöster Prozess, bevor Tray, Timer, Refreshworker oder HID-Handle erzeugt
werden.

## Manueller V1-Autostart-Abnahmetest

1. Autostart mit `packaging/manage-user-installation.sh enable-autostart`
   aktivieren und mit `autostart-status` prüfen.
2. Abmelden und erneut anmelden oder neu starten.
3. Prüfen, dass genau ein Tray-Icon und kein Hauptfenster erscheint.
4. Prüfen, dass die installierte App ohne HeartdriveLAB-Repository läuft.
5. Bei ausgeschalteter Option `LCD beim Programmstart automatisch starten`
   prüfen, dass das LCD nicht automatisch startet und kein dauerhafter GIF-,
   Sensor- oder Transportbetrieb beginnt.
6. Bei eingeschalteter Option prüfen, dass ausschließlich die bestehende
   LCD-Autostartlogik verwendet wird.
7. Die App über Tray → Beenden sauber schließen.

## Permanente Interface-1-Berechtigung

`99-tuf-aio-control.rules` bleibt eine getrennte Vorlage. Sie passt nur auf
hidraw-Knoten des Geräts `0b05:1c7b`: beide Interfaces erhalten für Gruppe
`input` höchstens `0640`, ausschließlich `ID_USB_INTERFACE_NUM==01` erhält
`0660`. Interface 0 bleibt gruppen-read-only und `0b05:19af` wird nicht
erfasst.

Der Benutzerinstaller installiert diese Datei nicht und ruft weder
Privilegienwerkzeuge noch udev auf. Eine spätere, separat bestätigte
Administratoraktion darf sie nach
`/etc/udev/rules.d/99-tuf-aio-control.rules` kopieren und die Regeln neu laden.

## GIF-Status in v0.1

Die Bildpipeline lädt GIF-Dateien einmalig und cached Frames, Dauern sowie
Loop-Metadaten. Die GUI kann diese Frames über den gemeinsamen Preview-/LCD-
Kompositionspfad animieren. Die Funktion ist offline implementiert, aber noch
nicht am realen LCD validiert. Animierte Inhalte verwenden ein
transportgeführtes serielles Pacing ohne feste App-seitige FPS-Grenze.
