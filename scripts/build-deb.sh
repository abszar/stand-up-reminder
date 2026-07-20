#!/bin/sh
set -eu

# Builds a system-wide Debian package into dist/. The packaged layout differs
# from scripts/install.sh: files live under /usr, and the user service is
# provided as a system-wide user unit that starts at each graphical login.

project_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"

version=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n 1)
app_id=io.github.abdelali.StandUpReminder
architecture=all
package_name=stand-up-reminder
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT

install -d "$staging/DEBIAN"
install -d "$staging/usr/bin"
install -d "$staging/usr/lib/$package_name/stand_up_reminder"
install -d "$staging/usr/lib/systemd/user"
install -d "$staging/usr/share/applications"
install -d "$staging/usr/share/doc/$package_name"
install -d "$staging/usr/share/icons/hicolor/scalable/apps"
install -d "$staging/usr/share/icons/hicolor/scalable/status"
install -d "$staging/etc/xdg/autostart"

for module in stand_up_reminder/*.py; do
    install -m 0644 "$module" "$staging/usr/lib/$package_name/stand_up_reminder/"
done

if command -v msgfmt >/dev/null 2>&1; then
    for catalogue in po/*.po; do
        [ -e "$catalogue" ] || continue
        language=$(basename "$catalogue" .po)
        message_dir="$staging/usr/lib/$package_name/locale/$language/LC_MESSAGES"
        install -d "$message_dir"
        msgfmt --output-file "$message_dir/$package_name.mo" "$catalogue"
    done
fi

cat > "$staging/usr/bin/$package_name" <<'LAUNCHER'
#!/bin/sh
set -eu

cd /usr/lib/stand-up-reminder
exec /usr/bin/python3 -m stand_up_reminder "$@"
LAUNCHER
chmod 0755 "$staging/usr/bin/$package_name"

sed 's|ExecStart=%h/.local/bin/stand-up-reminder|ExecStart=/usr/bin/stand-up-reminder|' \
    data/stand-up-reminder.service \
    > "$staging/usr/lib/systemd/user/$package_name.service"
chmod 0644 "$staging/usr/lib/systemd/user/$package_name.service"

install -m 0644 data/stand-up-reminder.desktop \
    "$staging/usr/share/applications/$app_id.desktop"
install -m 0644 data/stand-up-reminder-autostart.desktop \
    "$staging/etc/xdg/autostart/$package_name.desktop"
install -m 0644 data/stand-up-reminder-symbolic.svg \
    "$staging/usr/share/icons/hicolor/scalable/apps/stand-up-reminder-symbolic.svg"
install -m 0644 data/stand-up-reminder-symbolic.svg \
    "$staging/usr/share/icons/hicolor/scalable/status/stand-up-reminder-symbolic.svg"
install -m 0644 LICENSE "$staging/usr/share/doc/$package_name/copyright"

cat > "$staging/DEBIAN/control" <<CONTROL
Package: $package_name
Version: $version
Section: utils
Priority: optional
Architecture: $architecture
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1
Recommends: gnome-shell-extension-appindicator, gir1.2-gsound-1.0
Maintainer: Abdelali Bourassine <abszar@users.noreply.github.com>
Homepage: https://github.com/abszar/stand-up-reminder
Description: Reminder to take a standing break at a regular interval
 Stand Up Reminder prompts you to take a short standing break after each
 work interval. It runs as a GTK application with a top-bar indicator and
 an always-on-top break window, and can snooze, skip, or pause reminders.
CONTROL

cat > "$staging/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e

if [ "$1" = "configure" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
    fi
    systemctl --global daemon-reload || true
fi

exit 0
POSTINST
chmod 0755 "$staging/DEBIAN/postinst"

cat > "$staging/DEBIAN/prerm" <<'PRERM'
#!/bin/sh
set -e

if [ "$1" = "remove" ] || [ "$1" = "upgrade" ]; then
    systemctl --global disable stand-up-reminder.service >/dev/null 2>&1 || true
fi

exit 0
PRERM
chmod 0755 "$staging/DEBIAN/prerm"

install -d dist
package_file="dist/${package_name}_${version}_${architecture}.deb"
dpkg-deb --root-owner-group --build "$staging" "$package_file" >/dev/null
printf 'built %s\n' "$package_file"
