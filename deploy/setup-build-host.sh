#!/usr/bin/env bash
# Toolchain setup for the OpenFeedback Android SDK build.
# Runs on the private build host (172.16.38.110): JDK 17 + Android SDK 35.
set -euo pipefail

SDK_ROOT="${OF_SDK_ROOT:-$HOME/android-sdk}"
DL="$HOME/.of-dl"
mkdir -p "$DL" "$SDK_ROOT/cmdline-tools"

echo "=== [1/5] fetching Android command-line tools ==="
if [ ! -x "$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" ]; then
  cd "$DL"
  curl -fsSL -o cmdline-tools.zip \
    https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
  rm -rf "$DL/cmdline-tools"
  unzip -q cmdline-tools.zip -d "$DL"
  mkdir -p "$SDK_ROOT/cmdline-tools"
  mv "$DL/cmdline-tools" "$SDK_ROOT/cmdline-tools/latest"
fi
echo "sdkmanager: $("$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" --version)"

echo "=== [2/5] accepting licenses ==="
yes | "$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK_ROOT" --licenses >/dev/null 2>&1 || true

echo "=== [3/5] installing platform-tools, platforms;android-35, build-tools;35.0.0 ==="
"$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK_ROOT" \
  "platform-tools" "platforms;android-35" "build-tools;35.0.0"

echo "=== [4/5] JDK 17 (matches both host apps' JVM target) ==="
if ! update-alternatives --query java 2>/dev/null | grep -q '17'; then
  echo "123456" | sudo -S apt-get install -y -q openjdk-17-jdk-headless >/dev/null 2>&1 || \
    echo "WARN: apt install of openjdk-17 failed (may already be present)"
fi
ls /usr/lib/jvm 2>/dev/null || true

echo "=== [5/5] writing env file ==="
cat > "$HOME/.of-build-env" <<EOF
export ANDROID_HOME=$SDK_ROOT
export ANDROID_SDK_ROOT=$SDK_ROOT
export PATH=$SDK_ROOT/cmdline-tools/latest/bin:$SDK_ROOT/platform-tools:\$PATH
export JAVA_HOME=\$(ls -d /usr/lib/jvm/java-17-openjdk* 2>/dev/null | head -1)
export GRADLE_USER_HOME=$HOME/.gradle
EOF
cat "$HOME/.of-build-env"

echo "=== DONE ==="
ls "$SDK_ROOT"
