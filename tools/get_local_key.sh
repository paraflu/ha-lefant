#!/usr/bin/env bash
# Lefant M1 — recover the device's local key on a PC, without rooting a phone.
#
# What it does, in order:
#   1. prepares an Android emulator that is BOTH rootable and able to run the
#      app's arm64-only native code;
#   2. installs the official Lefant app (base APK + splits) if missing;
#   3. runs frida-server as root and attaches the getLocalKey hook;
#   4. leaves you to log in and open the vacuum screen — the key prints here.
#
# Requirements (checked below): Android SDK with cmdline-tools, platform-tools
# and emulator; a JDK; frida-tools; an XAPK or a directory with the app splits.
#
# Env knobs:
#   ANDROID_HOME   default: $HOME/Android/Sdk
#   AVD_NAME       default: Lefant_Root_API35
#   API            default: 35
#   XAPK           path to the .xapk (or an already-extracted directory)
#   HEADLESS=1     no window (then you cannot log in: only for setup debugging)
set -euo pipefail

ANDROID_HOME=${ANDROID_HOME:-$HOME/Android/Sdk}
export ANDROID_HOME
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"

AVD_NAME=${AVD_NAME:-Lefant_Root_API35}
API=${API:-35}
IMAGE="system-images;android-${API};google_apis;x86_64"
PKG=com.yunshi.robotlife
WORK=${WORK:-$HOME/.cache/lefant-key}
FRIDA=${FRIDA:-$(command -v frida || true)}

die() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

step "prerequisiti"
for tool in adb emulator avdmanager sdkmanager; do
  command -v "$tool" >/dev/null || die "manca $tool — installa Android SDK cmdline-tools/platform-tools/emulator"
done
command -v java >/dev/null || die "manca java (serve a sdkmanager)"
[ -n "$FRIDA" ] || die "manca frida — pip install frida-tools"
echo "adb/emulator/java ok; frida $("$FRIDA" --version)"

mkdir -p "$WORK"

step "immagine di sistema $IMAGE"
if [ ! -d "$ANDROID_HOME/system-images/android-$API/google_apis/x86_64" ]; then
  yes | sdkmanager --licenses >/dev/null 2>&1 || true
  sdkmanager "$IMAGE" || die "download immagine fallito"
fi
# Le immagini Play Store sono build 'user' e rifiutano adb root: serve google_apis.
grep -q 'ro.build.type=userdebug' \
  "$ANDROID_HOME/system-images/android-$API/google_apis/x86_64/build.prop" \
  || die "immagine non userdebug: adb root non funzionera'"
grep -q 'libndk_translation' \
  "$ANDROID_HOME/system-images/android-$API/google_apis/x86_64/build.prop" \
  || echo "ATTENZIONE: nessuna traduzione ARM in questa immagine (l'APK e' arm64-only)"
echo "immagine ok (userdebug + traduzione ARM)"

step "AVD $AVD_NAME"
if ! avdmanager list avd 2>/dev/null | grep -q "Name: $AVD_NAME"; then
  echo no | avdmanager create avd -n "$AVD_NAME" -k "$IMAGE" -d pixel_6 --force
fi
echo "avd ok"

step "chiusura emulatori gia' attivi"
# Un emulatore gia' in ascolto impedisce l'avvio del nuovo e farebbe agganciare
# Frida all'istanza sbagliata (tipicamente una headless, senza finestra).
if adb devices | grep -q emulator; then
  adb emu kill >/dev/null 2>&1 || true
  for _ in $(seq 1 15); do adb devices | grep -q emulator || break; sleep 2; done
  adb devices | grep -q emulator && die "emulatore ancora attivo: chiudilo a mano"
fi
rm -rf /run/user/$(id -u)/avd/running/* 2>/dev/null || true

step "avvio emulatore"
WINDOW_FLAG=()
if [ "${HEADLESS:-0}" != "1" ]; then
  if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    die "nessun DISPLAY: lancia da un terminale della sessione grafica, o usa HEADLESS=1"
  fi
else
  WINDOW_FLAG=(-no-window)
fi
# -qemu -cpu host e' obbligatorio: senza AES-NI nel guest la traduzione ARM
# aborta in libthingmmkv.so ("CHECK failed: host_platform::kHasAES").
setsid nohup emulator -avd "$AVD_NAME" -no-audio -no-boot-anim -no-snapshot \
  -memory 2048 -cores 2 -gpu swiftshader_indirect "${WINDOW_FLAG[@]}" \
  -qemu -cpu host > "$WORK/emulator.log" 2>&1 < /dev/null &

for _ in $(seq 1 60); do
  sleep 5
  [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
done
[ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] \
  || die "boot fallito: vedi $WORK/emulator.log (RAM libera? servono ~4 GB)"

step "root nel guest"
adb root >/dev/null 2>&1 || true
sleep 4
adb shell id 2>/dev/null | grep -q 'uid=0' \
  || die "adb root non attivo: immagine non userdebug?"
adb shell 'grep -q -m1 aes /proc/cpuinfo' 2>/dev/null \
  || die "il guest non vede AES-NI: manca -qemu -cpu host"
echo "uid=0 e AES ok"

step "app $PKG"
if ! adb shell pm list packages 2>/dev/null | grep -q "$PKG"; then
  [ -n "${XAPK:-}" ] || die "app non installata: passa XAPK=/percorso/file.xapk"
  SPLITS="$WORK/splits"
  if [ -d "$XAPK" ]; then SPLITS="$XAPK"; else
    mkdir -p "$SPLITS"
    python3 - "$XAPK" "$SPLITS" <<'PY'
import sys
from pathlib import Path
from zipfile import ZipFile
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
want = {'com.yunshi.robotlife.apk', 'config.arm64_v8a.apk',
        'config.en.apk', 'config.xhdpi.apk'}
with ZipFile(src) as z:
    for name in z.namelist():
        if name in want and not (dst / name).exists():
            (dst / name).write_bytes(z.read(name))
print(sorted(p.name for p in dst.iterdir()))
PY
  fi
  ( cd "$SPLITS" && adb install-multiple -r -g ./*.apk ) || die "installazione fallita"
fi
adb shell pm list packages 2>/dev/null | grep -q "$PKG" || die "app non installata"
echo "app presente"

step "frida-server"
ABI=$(adb shell getprop ro.product.cpu.abi | tr -d '\r')
VERSION=$("$FRIDA" --version)
SRV="$WORK/frida-server-$VERSION-$ABI"
if [ ! -x "$WORK/frida-server" ]; then
  URL="https://github.com/frida/frida/releases/download/$VERSION/frida-server-$VERSION-android-$ABI.xz"
  echo "scarico $URL"
  curl -fL --retry 5 -o "$WORK/frida-server.xz" "$URL"
  unxz -f "$WORK/frida-server.xz"
  chmod +x "$WORK/frida-server"
fi
adb push "$WORK/frida-server" /data/local/tmp/frida-server >/dev/null
adb shell 'chmod 755 /data/local/tmp/frida-server' || true
adb shell 'pkill -f /data/local/tmp/frida-server' >/dev/null 2>&1 || true
setsid nohup adb shell '/data/local/tmp/frida-server -D' \
  > "$WORK/frida-server.log" 2>&1 < /dev/null &
sleep 6
FRIDA_PS="$(dirname "$FRIDA")/frida-ps"
if [ -x "$FRIDA_PS" ]; then
  timeout 30 "$FRIDA_PS" -U >/dev/null 2>&1 \
    || die "frida-server non risponde: vedi $WORK/frida-server.log"
else
  adb shell 'ps -A | grep -q frida-server' \
    || die "frida-server non risponde: vedi $WORK/frida-server.log"
fi
echo "frida-server $VERSION attivo"

step "avvio app e aggancio"
adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
PID=""
for _ in $(seq 1 45); do
  sleep 2
  PID=$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')
  [ -n "$PID" ] && break
done
[ -n "$PID" ] || die "app non avviata"
echo "app attiva (pid $PID)"

cat <<'EOT'

  >>> NELLA FINESTRA DELL'EMULATORE <<<

  1. Completa la schermata paese/lingua.
  2. Accedi con il TUO account Lefant, la stessa regione del robot.
  3. NON rimuovere, riassociare o resettare il robot.
  4. Apri la schermata di controllo dell'M1.

  Compare qui:
      [M1]   devId    = ...
      [M1]   localKey = ...       (16 caratteri)

  Poi verifica con:
      export LEFANT_LOCAL_KEY='...'
      .venv/bin/python tools/probe_robot.py --host <ip> --device-id <devId> --dump-json

  Ctrl+C per uscire: l'app resta aperta.

EOT

# attach (non spawn) e nessuna pipe a valle: se la pipe si chiude, la REPL di
# frida termina subito e sembra "morta".
exec "$FRIDA" -U -p "$PID" -l "$(dirname "$0")/frida_get_local_key.js"
