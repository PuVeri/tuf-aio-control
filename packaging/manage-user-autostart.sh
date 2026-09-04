#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_directory/.." && pwd)
template="$script_directory/tuf-aio-control-autostart.desktop"
autostart_directory=${XDG_CONFIG_HOME:-"$HOME/.config"}/autostart
target="$autostart_directory/tuf-aio-control.desktop"

case "${1:-}" in
    install)
        mkdir -p -- "$autostart_directory"
        if [ -e "$target" ]; then
            printf 'Refusing to overwrite existing file: %s\n' "$target" >&2
            exit 1
        fi
        temporary=$(mktemp "$autostart_directory/.tuf-aio-control.XXXXXX")
        trap 'rm -f -- "$temporary"' EXIT HUP INT TERM
        escaped_root=$(printf '%s' "$project_root" | sed 's/[&|]/\\&/g')
        sed "s|@PROJECT_ROOT@|$escaped_root|g" "$template" >"$temporary"
        chmod 0644 "$temporary"
        mv -- "$temporary" "$target"
        trap - EXIT HUP INT TERM
        ;;
    uninstall)
        if [ ! -e "$target" ]; then
            exit 0
        fi
        if ! grep -q '^X-TufAioControl-Managed=true$' "$target"; then
            printf 'Refusing to remove unmanaged file: %s\n' "$target" >&2
            exit 1
        fi
        rm -- "$target"
        ;;
    *)
        printf 'Usage: %s install|uninstall\n' "$0" >&2
        exit 2
        ;;
esac
