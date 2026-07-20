#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
user_data_root=${XDG_DATA_HOME:-"$HOME/.local/share"}
user_config_root=${XDG_CONFIG_HOME:-"$HOME/.config"}
app_install_root="$user_data_root/stand-up-reminder"

install -d "$app_install_root/stand_up_reminder" "$HOME/.local/bin"
install -d "$user_data_root/applications"
install -d "$user_data_root/icons/hicolor/scalable/apps"
install -d "$user_data_root/icons/hicolor/scalable/status"
install -d "$user_config_root/autostart" "$user_config_root/systemd/user"

for app_source in "$project_root"/stand_up_reminder/*.py; do
    install -m 0644 "$app_source" "$app_install_root/stand_up_reminder/"
done
install -m 0755 "$project_root/data/stand-up-reminder-launcher" \
    "$HOME/.local/bin/stand-up-reminder"
install -m 0644 "$project_root/data/stand-up-reminder.desktop" \
    "$user_data_root/applications/stand-up-reminder.desktop"
install -m 0644 "$project_root/data/stand-up-reminder-autostart.desktop" \
    "$user_config_root/autostart/stand-up-reminder.desktop"
install -m 0644 "$project_root/data/stand-up-reminder.service" \
    "$user_config_root/systemd/user/stand-up-reminder.service"
install -m 0644 "$project_root/data/stand-up-reminder-symbolic.svg" \
    "$user_data_root/icons/hicolor/scalable/apps/stand-up-reminder-symbolic.svg"
install -m 0644 "$project_root/data/stand-up-reminder-symbolic.svg" \
    "$user_data_root/icons/hicolor/scalable/status/stand-up-reminder-symbolic.svg"

gtk-update-icon-cache -f -t "$user_data_root/icons/hicolor" >/dev/null 2>&1 || true
update-desktop-database "$user_data_root/applications" >/dev/null 2>&1 || true
systemctl --user daemon-reload
systemctl --user restart stand-up-reminder.service
