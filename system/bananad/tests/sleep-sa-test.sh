#!/bin/sh
# bananad's sleep, tested without an RG DS: bananad runs in its own mount and PID namespaces against a made-up
# /sys (the battery, the LEDs, the backlights, the RTC, /sys/power) and /dev/input (FIFOs that carry real
# struct input_event records). /sys/power/state is a FIFO: bananad's write of "mem" blocks until the test reads it,
# which is the handheld being asleep; the test decides what the world looks like when it "wakes". A stand-in game
# (its process group must be stopped while asleep) and a stand-in banana-ui (it must get SIGUSR1 after a wake).
#
#   sudo system/bananad/tests/sleep-test.sh        (root: it mounts in a private namespace; nothing outside changes)
#   sleep-test.sh --build <dir>                      only the programs, into <dir> (for a runner of its own, then --inside)
set -e
HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOTFS=$(cd "$HERE/../rootfs" && pwd)
if [ "$1" != --inside ]; then
    if [ "$1" = --build ]; then W=$2; mkdir -p "$W"; else W=$(mktemp -d); fi
    # All test files live on private tmpfs mounts. Do not flush unrelated host
    # builds/disks: real sync() can exceed fixture deadlines while packaging.
    printf 'void __wrap_sync(void) {}\n' > "$W/sync-stub.c"
    cc -O2 -Wl,--wrap=sync -Wl,--wrap=fopen -o "$W/bananad" "$HERE/bananad.c" "$W/sync-stub.c" "$HERE/tests/no-children-wrap.c"
    cc -O2 -o "$W/banana-ui" -x c - <<'EOF'
#include <signal.h>
#include <stdio.h>
#include <unistd.h>
static void on(int s) { FILE *f = fopen("/run/test/ui-signals", "a"); if (f) { fprintf(f, "SIGUSR1\n"); fclose(f); } }
int main(void) { signal(SIGUSR1, on); for (;;) pause(); }
EOF
    # stand-in emulators for Power off after sleeping, one program under each name bananad looks for (drastic,
    # bananads, retroarch): what reaches it (SIGUSR1, SIGTERM, the lines on its stdin) in /run/test/<name>.log, then
    # "saved" a moment later and it quits, on a signal or on RetroArch's QUIT
    cc -O2 -o "$W/drastic" -x c - <<'EOF'
#include <fcntl.h>
#include <libgen.h>
#include <stdlib.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
static volatile sig_atomic_t got;
static void on(int s) { got = s; }
static const char *name;
static void say(const char *m) { char p[128]; snprintf(p, sizeof p, "/run/test/%s.log", name); FILE *f = fopen(p, "a"); if (f) { fprintf(f, "%s\n", m); fclose(f); } }
int main(int argc, char **argv)
{
	(void)argc; name = basename(argv[0]);
	signal(SIGUSR1, on); signal(SIGTERM, on);
	fcntl(0, F_SETFL, fcntl(0, F_GETFL) | O_NONBLOCK);
	char buf[512]; size_t have = 0;
	for (;;) {
		if (got) {
			say(got == SIGUSR1 ? "USR1" : "TERM"); usleep(300000);
			const char *rf = getenv("TEST_RESUME");	/* the resume state, when the test wants one written */
			if (got == SIGUSR1 && rf && *rf) { FILE *f = fopen(rf, "w"); if (f) { fputs("state", f); fclose(f); } }
			say("saved"); return 0;
		}
		ssize_t r = read(0, buf + have, sizeof buf - 1 - have);
		if (r > 0) {
			have += r; buf[have] = 0;
			char *nl;
			while ((nl = strchr(buf, '\n'))) {
				*nl = 0; say(buf);
				int quit = !strcmp(buf, "QUIT");
				memmove(buf, nl + 1, strlen(nl + 1) + 1); have = strlen(buf);
				if (quit) { usleep(300000); say("saved"); return 0; }
			}
		}
		usleep(20000);
	}
}
EOF
    cp "$W/drastic" "$W/bananads"; cp "$W/drastic" "$W/retroarch"; cp "$W/drastic" "$W/bananafront"
    [ "$1" = --build ] && exit 0
    mkdir -p /data 2>/dev/null || true
    exec unshare -m -p -f --mount-proc sh "$0" --inside "$W" "$ROOTFS"
fi

# ---- inside: pid 1 is this shell, so bananad's "shut down" (SIGUSR2 to init) comes here ------------------------
W=$2 ROOTFS=$3
POWEROFF=0
trap 'POWEROFF=1' USR2
# (a kernel without power management, as a container's VM: no /sys/power to mount over, so a made-up /sys of our own)
[ -d /sys/power ] || { mount -t tmpfs none /sys; mkdir -p /sys/power /sys/class; }
mount -t tmpfs none /sys/power
mount -t tmpfs none /sys/class
mount -t tmpfs none /dev/input 2>/dev/null || { mkdir -p /dev/input; mount -t tmpfs none /dev/input; }
mount -t tmpfs none /run
mount -t tmpfs none /data
mkdir -p /etc/banana && mount -t tmpfs none /etc/banana && cp -r "$ROOTFS/etc/banana/." /etc/banana/
mkdir -p /run/banana /run/test /data/banana/logs /sys/class/rtc/rtc0 /sys/class/power_supply/battery
echo Battery > /sys/class/power_supply/battery/type
echo Discharging > /sys/class/power_supply/battery/status
echo 50 > /sys/class/power_supply/battery/capacity
: > /sys/class/rtc/rtc0/wakealarm
echo "s2idle [deep]" > /sys/power/mem_sleep
echo 0 > /sys/power/pm_async
for l in green:power red:status amber:charging; do mkdir -p /sys/class/leds/$l; : > /sys/class/leds/$l/trigger; : > /sys/class/leds/$l/brightness; done
for b in backlight0 backlight1; do mkdir -p /sys/class/backlight/$b; echo 255 > /sys/class/backlight/$b/max_brightness; echo 200 > /sys/class/backlight/$b/brightness; echo 0 > /sys/class/backlight/$b/bl_power; done
mkfifo /sys/power/state /dev/input/event0
exec 3<>/dev/input/event0       # a writer that stays, so bananad's poll doesn't see a hang-up
mkfifo /run/test/touch; exec 4<>/run/test/touch     # the stand-in touchscreen bananad reads unpolled (BANANAD_TEST_TOUCH)
echo 0 > /run/test/lid

pass=0 fail=0
ok() { pass=$((pass + 1)); echo "  ok: $*"; }
bad() { fail=$((fail + 1)); echo "  FAIL: $*"; }
# an input event: type code value (then a SYN_REPORT)
ev() { python3 -c "
import struct, sys
t, c, v = (int(x) for x in sys.argv[1:4])
sys.stdout.buffer.write(struct.pack('llHHi', 0, 0, t, c, v) + struct.pack('llHHi', 0, 0, 0, 0, 0))" "$@" >&3; }
EV_SW=5 SW_LID=0 EV_KEY=1 KEY_POWER=116
# is bananad blocked writing "mem" (asleep)? wait up to 3 s
# (blocked opening the FIFO: its wait channel is wait_for_partner)
asleep() { for i in $(seq 30); do [ "$(cat /proc/$BD/wchan 2>/dev/null)" = wait_for_partner ] && return 0; sleep 0.1; done; return 1; }
wake() { head -c 3 /sys/power/state > /dev/null; sleep 0.3; }       # read "mem": the write returns, it is awake
gstate() { awk '{print $3}' /proc/$GAME/stat; }
start() {   # start [bananad.conf lines]
    echo "s2idle [deep]" > /sys/power/mem_sleep     # the kernel's file always lists both
    printf '%s\n' "autosleep_minutes = 0" "sleep_check_hours = 0" "$@" > /data/banana/bananad.conf
    BANANAD_TEST_LID=/run/test/lid BANANAD_TEST_TOUCH=/run/test/touch "$W/bananad" & BD=$!
    sleep 0.5
}
stop() { kill $BD 2>/dev/null; wait $BD 2>/dev/null || true; }

"$W/banana-ui" & UI=$!
setsid sleep 600 & GAME=$!
sleep 0.2
echo "$GAME $(awk '{print $22}' /proc/$GAME/stat)" > /run/banana/game.pid

kill $GAME; wait $GAME 2>/dev/null || true
cat > /run/test/sa.py <<'PY'
import os,signal,time
from pathlib import Path
pids=[]
def worker(name,paused=False):
    p=os.fork()
    if p: return p
    os.setsid()
    if name=='engine':
        sub=os.fork()
        if not sub:
            os.setsid()
            name='renderer'
        else: Path('/run/test/renderer.pid').write_text(str(sub))
    Path('/run/test/'+name+'.pid').write_text(str(os.getpid()))
    if paused: os.kill(os.getpid(),signal.SIGSTOP)
    n=0
    while True:
        n+=1
        Path('/run/test/'+name+'.ticks').write_text(str(n))
        time.sleep(.02)
pids=[worker('engine'),worker('paused',True)]
Path('/run/test/launcher.pid').write_text(str(os.getpid()))
while True: time.sleep(.05)
PY
setsid python3 /run/test/sa.py & GAME=$!
for i in $(seq 50); do [ -f /run/test/paused.pid ] && [ -f /run/test/renderer.ticks ] && break; sleep .02; done
ENGINE=$(cat /run/test/engine.pid); RENDERER=$(cat /run/test/renderer.pid); PAUSED=$(cat /run/test/paused.pid)
echo "$GAME $(awk '{print $22}' /proc/$GAME/stat)" > /run/banana/game.pid
setsid sleep 600 & OTHER=$!
state() { awk '{print $3}' /proc/$1/stat; }
all_stopped() { [ "$(state $GAME)" = T ] && [ "$(state $ENGINE)" = T ] && [ "$(state $RENDERER)" = T ]; }
playing() { [ "$(state $GAME)" != T ] && [ "$(state $ENGINE)" != T ] && [ "$(state $RENDERER)" != T ]; }
start

echo 'SA 1: lid suspend freezes launcher, setsid engine and setsid renderer'
echo 1 > /run/test/lid; ev $EV_SW $SW_LID 1
asleep && ok 'kernel suspend requested on lid close' || bad 'no suspend'
all_stopped && ok 'all SA sessions stopped' || bad 'SA tree still running'
a=$(cat /run/test/engine.ticks); b=$(cat /run/test/renderer.ticks); sleep .15
[ "$a" = "$(cat /run/test/engine.ticks)" ] && [ "$b" = "$(cat /run/test/renderer.ticks)" ] && ok 'both game counters frozen' || bad 'counter advanced while asleep'
[ "$(state $OTHER)" != T ] && ok 'unrelated process unaffected' || bad 'unrelated process stopped'
echo 0 > /run/test/lid; wake
playing && ok 'all previously playing sessions resumed' || bad 'SA did not resume'
[ "$(state $PAUSED)" = T ] && ok 'pre-paused engine remains paused' || bad 'pre-paused engine was resumed'

echo 'SA 2: short power button pauses whole tree and resumes'
sleep 1.1; ev $EV_KEY $KEY_POWER 1; ev $EV_KEY $KEY_POWER 0
asleep && ok 'power button requested kernel suspend' || bad 'power sleep missing'
all_stopped && ok 'power sleep stopped SA tree' || bad 'power only blanked display'
wake
playing && ok 'power wake resumed SA tree' || bad 'no power resume'

echo 'SA 3: recover missed lid event using kernel state polling'
sleep 1.1; echo 1 > /run/test/lid
asleep && ok 'missed lid event recovered' || bad 'kernel lid state ignored'
all_stopped && ok 'tree frozen after missed edge' || bad 'missed edge did not pause'
echo 0 > /run/test/lid; wake

echo 'SA 4: charger sleep stops game while charging light stays on'
mkdir -p /sys/class/power_supply/charger
echo USB > /sys/class/power_supply/charger/type; echo 1 > /sys/class/power_supply/charger/online
echo 1 > /run/test/lid; ev $EV_SW $SW_LID 1; sleep .7
all_stopped && ok 'charger dark state freezes whole SA tree' || bad 'SA playing in dark charger state'
echo 0 > /run/test/lid; sleep .7
playing && ok 'charger lid wake resumes SA tree' || bad 'charger resume failed'
rm -rf /sys/class/power_supply/charger

echo 'SA 5: kernel suspend failure keeps game stopped until intentional wake'
stop; rm -f /sys/power/state; mkdir /sys/power/state
start
echo 1 > /run/test/lid; ev $EV_SW $SW_LID 1
sleep 1
all_stopped && ok 'kernel failure does not run invisible game/audio' || bad 'game runs after suspend failure'
grep -q 'suspend unavailable: game paused' /data/banana/logs/sleep.log && ok 'kernel failure logged explicitly' || bad 'missing failure log'
echo 0 > /run/test/lid; sleep .7
playing && ok 'intentional wake resumes failed-suspend fallback' || bad 'fallback wake failed'
[ "$(state $PAUSED)" = T ] && ok 'paused state still preserved across all cycles' || bad 'paused state lost'
stop
kill -CONT $PAUSED; kill $GAME $ENGINE $RENDERER $PAUSED $OTHER $UI 2>/dev/null || true
echo "SA sleep test: $pass passed, $fail failed"
[ $fail = 0 ]