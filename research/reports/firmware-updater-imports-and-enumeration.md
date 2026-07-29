# Firmware-Updater: Imports und HID-Aufzählung

Stand: 2026-07-29. Quelle ist ausschließlich die statische Disassembly von
`research/extracted/firmware-v51/WW11_320x320_2.8inch_v51_TUF_20250626.exe`
(SHA-256 `037b581f2bd5bc95db7db1a6f68d25d7ac2c19afe9fa09888851f0d6e448fb65`).

## Beobachtete Fakten

- Relevante Imports:
  - `HID.DLL`: `HidD_GetAttributes`, `HidD_GetPreparsedData`,
    `HidP_GetCaps`, `HidD_FreePreparsedData`
  - `SETUPAPI.dll`: `SetupDiGetClassDevsW`,
    `SetupDiGetDeviceInterfaceDetailW`, `SetupDiEnumDeviceInterfaces`,
    `SetupDiDestroyDeviceInfoList`
  - `KERNEL32.dll`: `CreateFileW`, `ReadFile`, `WriteFile`, `CancelIo`,
    `GetOverlappedResult`, `WaitForMultipleObjects`, `Sleep`,
    `GetTickCount`, `CloseHandle`
- Der Aufzählungspfad liegt im Bereich `0x40ba93` bis `0x40be9c`.
  `SetupDiGetClassDevsW` erhält die GUID an `0x5c21a0`, Flags `0x12` und
  keinen Enumerator. Danach wird mit einem bei null beginnenden Index
  `SetupDiEnumDeviceInterfaces` aufgerufen. Der Interface-Data-Block wird mit
  Größe `0x1c` initialisiert.
- `SetupDiGetDeviceInterfaceDetailW` wird zuerst mit null Zielpuffer zur
  Größenermittlung und danach mit einem allokierten Puffer aufgerufen. Dessen
  erstes DWORD wird vor dem zweiten Aufruf auf `6` gesetzt.
- Jeder Detailpfad wird im Bereich `0x40b670` ff. mit dem UTF-16-Regex
  `hid#vid_([\da-zA-Z]{4})&pid_([\da-zA-Z]{4})(&rev_([\da-zA-Z]){4})?(&mi_([\da-zA-Z]){2})?(&col([\da-zA-Z]){2})?`
  ausgewertet. Die erfassten Hexfelder werden in numerische Werte überführt
  und in einer internen Gerätebeschreibung gespeichert.
- Die Routine vergleicht mindestens einen ausgewerteten 32-Bit-Wert gegen eine
  vom Aufrufer gelieferte Werteliste. Die genaue Belegung dieser Liste ist aus
  dem Ausschnitt nicht sicher benennbar.
- Ein Kandidat wird mit `CreateFileW` geöffnet; danach werden
  `HidD_GetAttributes`, `HidD_GetPreparsedData` und `HidP_GetCaps` aufgerufen.
  Bei erfolgreichem `HidP_GetCaps` (`NTSTATUS 0x00110000`) werden die beiden
  ersten 16-Bit-Werte der Caps-Struktur in der internen Beschreibung
  gespeichert. Preparsed Data und Handle werden anschließend freigegeben.
- `SetupDiDestroyDeviceInfoList` wird am Ende aufgerufen.

## Abgeleitete Zusammenhänge

- Der Code implementiert eine generische HID-Aufzählung: Interface-GUID →
  SetupAPI-Detailpfad → Pfadparser → optionaler Filter → HID-Attribute und
  Caps.
- VID, PID, optional REV, MI und COL werden syntaktisch erkannt. Welche davon
  die konkrete Zielauswahl tatsächlich einschränken, ist nicht belegt.

## Hypothesen

- Die vom Aufrufer gelieferte Werteliste könnte zugelassene VID/PID- oder
  kombinierte Gerätekennungen enthalten. Das ist noch nicht belegt.
- MI und COL könnten nur als Metadaten gespeichert und nicht zur Auswahl
  verwendet werden.

## Unbekannt

- Konkrete Ziel-VID/PID, MI- oder COL-Werte im Aufrufpfad.
- Verhalten bei mehreren passenden Geräten und genaue Sortierung.
- Direkte Zuordnung zu Interface 0 oder 1 des untersuchten ASUS-Geräts.

