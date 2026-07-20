#!/bin/sh
set -eu

user_data_root=${XDG_DATA_HOME:-"$HOME/.local/share"}
user_config_root=${XDG_CONFIG_HOME:-"$HOME/.config"}
app_install_root="$user_data_root/stand-up-reminder"

systemctl --user stop stand-up-reminder.service >/dev/null 2>&1 || true
rm -f "$user_config_root/autostart/stand-up-reminder.desktop"
rm -f "$user_config_root/systemd/user/stand-up-reminder.service"
rm -f "$user_data_root/applications/stand-up-reminder.desktop"
rm -f "$user_data_root/icons/hicolor/scalable/apps/stand-up-reminder-symbolic.svg"
rm -f "$user_data_root/icons/hicolor/scalable/status/stand-up-reminder-symbolic.svg"
rm -f "$HOME/.local/bin/stand-up-reminder"
rm -rf "$app_install_root"
systemctl --user daemon-reload
