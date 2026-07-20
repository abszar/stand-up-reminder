#!/bin/sh
set -eu

# Regenerates po/stand-up-reminder.pot from the source strings and merges the
# result into every existing catalogue.

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"

version=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n 1)

xgettext \
    --language=Python \
    --keyword=_ \
    --keyword=ngettext:1,2 \
    --from-code=UTF-8 \
    --add-location=file \
    --package-name="Stand Up Reminder" \
    --package-version="$version" \
    --copyright-holder="Stand Up Reminder contributors" \
    --msgid-bugs-address="https://github.com/abszar/stand-up-reminder/issues" \
    --output=po/stand-up-reminder.pot \
    stand_up_reminder/*.py

# The generated header carries a placeholder mailing-list address; the project
# keeps tracked files free of addresses that are not GitHub noreply ones.
sed -i 's|^"Language-Team: LANGUAGE <.*>\\n"$|"Language-Team: LANGUAGE\\n"|' \
    po/stand-up-reminder.pot

for catalogue in po/*.po; do
    [ -e "$catalogue" ] || continue
    msgmerge --quiet --update --backup=none "$catalogue" po/stand-up-reminder.pot
    printf 'updated %s\n' "$catalogue"
done
