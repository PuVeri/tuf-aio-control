#!/bin/sh
set -eu

managed_desktop='X-TufAioControl-Managed=true'
managed_app='tuf-aio-control-user-installation-v0.1'

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_directory/.." && pwd)
manifest="$script_directory/runtime-files.txt"
launcher_source="$script_directory/tuf-aio-control-launcher"
desktop_template="$script_directory/tuf-aio-control.desktop.in"
autostart_template="$script_directory/tuf-aio-control-autostart.desktop"

: "${HOME:?HOME is required}"
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
case "$HOME" in /*) ;; *) printf 'HOME must be an absolute path\n' >&2; exit 1 ;; esac
case "$data_home" in /*) ;; *) data_home="$HOME/.local/share" ;; esac
case "$config_home" in /*) ;; *) config_home="$HOME/.config" ;; esac
application_directory="$data_home/tuf-aio-control"
binary_directory="$HOME/.local/bin"
launcher="$binary_directory/tuf-aio-control"
desktop_directory="$data_home/applications"
desktop_file="$desktop_directory/tuf-aio-control.desktop"
autostart_directory="$config_home/autostart"
autostart_file="$autostart_directory/tuf-aio-control.desktop"

usage() {
    printf 'Usage: %s install [--autostart] | update [--autostart] | uninstall | enable-autostart | disable-autostart\n' "$0" >&2
    exit 2
}

is_managed_desktop() {
    [ -f "$1" ] && grep -Fqx "$managed_desktop" "$1"
}

require_managed_file() {
    file=$1
    description=$2
    if ! is_managed_desktop "$file"; then
        printf 'Refusing to replace unmanaged %s: %s\n' "$description" "$file" >&2
        exit 1
    fi
}

require_managed_installation() {
    if [ ! -f "$application_directory/.managed-installation" ] ||
       [ "$(sed -n '1p' "$application_directory/.managed-installation")" != "$managed_app" ]; then
        printf 'No managed TUF AIO Control installation found: %s\n' "$application_directory" >&2
        exit 1
    fi
    if [ ! -f "$launcher" ] || ! grep -Fqx '# X-TufAioControl-Managed: true' "$launcher"; then
        printf 'Refusing to replace unmanaged launcher: %s\n' "$launcher" >&2
        exit 1
    fi
    require_managed_file "$desktop_file" 'desktop file'
}

check_runtime() {
    if [ ! -x /usr/bin/python3 ]; then
        printf 'Missing runtime: /usr/bin/python3\n' >&2
        exit 1
    fi
    if ! /usr/bin/python3 -c 'import PIL, PySide6' 2>/dev/null; then
        printf 'Missing Python runtime dependencies: PySide6 and/or Pillow\n' >&2
        printf 'See packaging/runtime-requirements.txt and packaging/README.md.\n' >&2
        exit 1
    fi
}

render_desktop() {
    template=$1
    target=$2
    escaped_launcher=$(printf '%s' "$launcher" | sed 's/[&|]/\\&/g')
    temporary=$(mktemp "$target.XXXXXX")
    sed "s|@LAUNCHER@|$escaped_launcher|g" "$template" >"$temporary"
    chmod 0644 "$temporary"
    mv -- "$temporary" "$target"
}

stage_application() {
    stage=$1
    mkdir -p -- "$stage/app"
    while IFS= read -r relative || [ -n "$relative" ]; do
        case "$relative" in
            ''|'#'*) continue ;;
            src/*.py) ;;
            *)
                printf 'Unsafe runtime manifest entry: %s\n' "$relative" >&2
                exit 1
                ;;
        esac
        source_file="$project_root/$relative"
        if [ ! -f "$source_file" ]; then
            printf 'Missing runtime source: %s\n' "$source_file" >&2
            exit 1
        fi
        install -m 0644 -- "$source_file" "$stage/app/$(basename -- "$relative")"
    done <"$manifest"
    printf '%s\n' "$managed_app" >"$stage/.managed-installation"
}

install_desktop_files() {
    enable_autostart=$1
    mkdir -p -- "$binary_directory" "$desktop_directory"
    install -m 0755 -- "$launcher_source" "$launcher"
    render_desktop "$desktop_template" "$desktop_file"
    if [ "$enable_autostart" = true ]; then
        mkdir -p -- "$autostart_directory"
        if [ -e "$autostart_file" ] && ! is_managed_desktop "$autostart_file"; then
            printf 'Refusing to replace unmanaged autostart file: %s\n' "$autostart_file" >&2
            exit 1
        fi
        render_desktop "$autostart_template" "$autostart_file"
    fi
}

install_application() {
    enable_autostart=$1
    check_runtime
    for target in "$application_directory" "$launcher" "$desktop_file"; do
        if [ -e "$target" ]; then
            printf 'Refusing to overwrite existing path: %s\n' "$target" >&2
            exit 1
        fi
    done
    if [ -e "$autostart_file" ]; then
        printf 'Refusing to overwrite existing path: %s\n' "$autostart_file" >&2
        exit 1
    fi
    mkdir -p -- "$data_home"
    stage=$(mktemp -d "$data_home/.tuf-aio-control.install.XXXXXX")
    trap 'rm -rf -- "$stage"' EXIT HUP INT TERM
    stage_application "$stage"
    mv -- "$stage" "$application_directory"
    trap - EXIT HUP INT TERM
    install_desktop_files "$enable_autostart"
}

update_application() {
    requested_autostart=$1
    check_runtime
    require_managed_installation
    enable_autostart=$requested_autostart
    if [ -e "$autostart_file" ]; then
        require_managed_file "$autostart_file" 'autostart file'
        enable_autostart=true
    fi
    mkdir -p -- "$data_home"
    stage=$(mktemp -d "$data_home/.tuf-aio-control.update.XXXXXX")
    backup=$(mktemp -d "$data_home/.tuf-aio-control.backup.XXXXXX")
    rmdir -- "$backup"
    rollback_update() {
        if [ ! -e "$application_directory" ] && [ -e "$backup" ]; then
            mv -- "$backup" "$application_directory"
        fi
        rm -rf -- "$stage"
        if [ -e "$application_directory" ] && [ -e "$backup" ]; then
            rm -rf -- "$backup"
        fi
    }
    trap rollback_update EXIT HUP INT TERM
    stage_application "$stage"
    mv -- "$application_directory" "$backup"
    if ! mv -- "$stage" "$application_directory"; then
        mv -- "$backup" "$application_directory"
        exit 1
    fi
    rm -rf -- "$backup"
    trap - EXIT HUP INT TERM
    install_desktop_files "$enable_autostart"
}

enable_autostart() {
    require_managed_installation
    mkdir -p -- "$autostart_directory"
    if [ -e "$autostart_file" ] && ! is_managed_desktop "$autostart_file"; then
        printf 'Refusing to replace unmanaged autostart file: %s\n' "$autostart_file" >&2
        exit 1
    fi
    render_desktop "$autostart_template" "$autostart_file"
}

disable_autostart() {
    if [ ! -e "$autostart_file" ]; then
        return
    fi
    require_managed_file "$autostart_file" 'autostart file'
    rm -- "$autostart_file"
}

uninstall_application() {
    require_managed_installation
    disable_autostart
    rm -rf -- "$application_directory"
    rm -- "$launcher" "$desktop_file"
    printf 'Application removed. QSettings and runtime logs were preserved.\n'
}

command=${1:-}
[ "$#" -gt 0 ] || usage
shift
autostart=false
if [ "$#" -gt 0 ]; then
    if [ "$#" -eq 1 ] && [ "$1" = '--autostart' ]; then
        autostart=true
    else
        usage
    fi
fi

case "$command" in
    install) install_application "$autostart" ;;
    update) update_application "$autostart" ;;
    uninstall)
        [ "$#" -eq 0 ] || usage
        uninstall_application
        ;;
    enable-autostart)
        [ "$#" -eq 0 ] || usage
        enable_autostart
        ;;
    disable-autostart)
        [ "$#" -eq 0 ] || usage
        disable_autostart
        ;;
    *) usage ;;
esac
