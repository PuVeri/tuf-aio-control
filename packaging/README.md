# Linux-Desktopintegration

## Benutzer-Autostart

`tuf-aio-control-autostart.desktop` startet die Anwendung beim Desktop-Login mit
`--background`. Dadurch läuft dieselbe Anwendung als Tray-Prozess, ohne das
Fenster anfänglich anzuzeigen. App-Autostart startet nicht automatisch den
LCD-Refresh: Dafür existiert die getrennte, standardmäßig ausgeschaltete
GUI-Option `LCD beim Programmstart automatisch starten`.

Die Repositorydatei installiert sich nicht selbst. Eine bewusste
Benutzerinstallation beziehungsweise Entfernung erfolgt aus dem Projektroot:

```text
packaging/manage-user-autostart.sh install
packaging/manage-user-autostart.sh uninstall
```

Das Skript überschreibt keine vorhandene Zieldatei und entfernt nur eine mit
seinem Projektmarker versehene Datei.

Das Hilfsskript schreibt ausschließlich
`${XDG_CONFIG_HOME:-$HOME/.config}/autostart/tuf-aio-control.desktop` und setzt
den absoluten aktuellen Projektpfad ein. Wird das Repository verschoben, muss
die Benutzerdatei erneut installiert werden.

## Permanente Interface-1-Berechtigung

`99-tuf-aio-control.rules` ist die vorbereitete permanente udev-Regel. Sie
passt ausschließlich auf hidraw-Knoten des Geräts `0b05:1c7b`. Zunächst setzt
sie beide Interfaces für die Gruppe `input` auf `0640`; eine zweite,
zusätzliche Bedingung setzt ausschließlich
`ID_USB_INTERFACE_NUM==01` auf `0660`. Interface 0 bleibt damit für die Gruppe
read-only. Das getrennte Gerät `0b05:19af` wird nicht erfasst.

Die Anwendung installiert die Regel nicht und ruft weder `sudo` noch udev auf.
Eine spätere bewusste Administratorinstallation muss zunächst sicherstellen,
dass keine ungeprüfte Zieldatei überschrieben wird:

```text
sudo test ! -e /etc/udev/rules.d/99-tuf-aio-control.rules
sudo install -o root -g root -m 0644 \
  packaging/99-tuf-aio-control.rules \
  /etc/udev/rules.d/99-tuf-aio-control.rules
sudo udevadm verify /etc/udev/rules.d/99-tuf-aio-control.rules
sudo udevadm control --reload-rules
```

Danach wird das Gerät bevorzugt neu verbunden. Vor jedem LCD-Start müssen die
dynamisch erkannten Interfacewerte und Modusbits geprüft werden. Die
Production-Safety-Gates der Anwendung bleiben unabhängig von Unix-Rechten
vollständig aktiv; es gibt keinen Reconnect oder automatischen Retry.
