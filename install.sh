#!/bin/sh
# Installs Dictate for whoever runs this: a `wispr` command, a menu-bar
# Dictate.app in ~/Applications, and (optionally) a login item. Safe to
# re-run any time — it regenerates everything from the current repo location.
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_BIN="$REPO_DIR/.venv/bin"

echo "Installing dependencies with uv..."
(cd "$REPO_DIR" && uv sync)

echo "Installing 'wispr' command to ~/.local/bin..."
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/wispr" << EOF
#!/bin/sh
# Start Dictate (local Wispr Flow clone). Safe to run anytime: if it's
# already running, the second copy exits immediately.
exec uv run --project "$REPO_DIR" wispr
EOF
chmod +x "$HOME/.local/bin/wispr"

echo "Building Dictate.app in ~/Applications..."
APP="$HOME/Applications/Dictate.app"
mkdir -p "$APP/Contents/MacOS"
cat > "$APP/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Dictate</string>
    <key>CFBundleDisplayName</key><string>Dictate</string>
    <key>CFBundleIdentifier</key><string>com.dictate.app</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>CFBundleExecutable</key><string>dictate</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSUIElement</key><true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Dictate records your speech while you hold Right Command, transcribes it on-device, and types it for you. Audio never leaves this Mac.</string>
</dict>
</plist>
EOF
cat > "$APP/Contents/MacOS/dictate" << EOF
#!/bin/zsh
# launchd/Finder launches don't have Homebrew on PATH; parakeet-mlx needs ffmpeg
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
exec "$VENV_BIN/dictate" >> "\$HOME/Library/Logs/dictate.log" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/dictate"
codesign --force -s - "$APP" 2>&1 | grep -v "replacing existing signature" || true

echo ""
echo "Done. Start it with:  wispr   (or: open -a Dictate)"
echo ""
echo "First launch will ask for Microphone, Accessibility, and Input"
echo "Monitoring permissions -- approve them, then relaunch."
echo ""
read -p "Also start Dictate automatically at login? [y/N] " answer
if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$HOME/Library/LaunchAgents/com.dictate.app.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.dictate.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-a</string>
        <string>$APP</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF
    echo "Installed login item. Remove anytime with:"
    echo "  rm ~/Library/LaunchAgents/com.dictate.app.plist"
fi
