#!/bin/sh
# Installa Kalendae per l'utente corrente (nessun permesso di root necessario).
# Uso: dalla cartella estratta, ./install-linux.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/opt/Kalendae"
mkdir -p "$HOME/.local/opt" "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/512x512/apps"
rm -rf "$DEST"
cp -r "$HERE" "$DEST"
ln -sf "$DEST/Kalendae" "$HOME/.local/bin/Kalendae"
cp "$HERE/kalendae.png" "$HOME/.local/share/icons/hicolor/512x512/apps/kalendae.png"
sed "s|^Exec=.*|Exec=$DEST/Kalendae|" "$HERE/kalendae.desktop" > "$HOME/.local/share/applications/kalendae.desktop"
echo "Kalendae installato. Lo trovi nel menu delle applicazioni."
