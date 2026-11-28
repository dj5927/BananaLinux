#!/usr/bin/env python3
"""PortMaster lifecycle control shared by the touch panel and physical hotkeys."""
import hashlib
import os
import select
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from port_gpu import PortGPU, PortProcesses


def main():
    script = Path(sys.argv[1]).resolve(strict=True)
    data = Path(os.environ.get("BANANA_PORT_DATA", "/data"))
    key = os.environ.get("BANANA_GAME_KEY", str(script))
    ident = hashlib.sha256(key.encode("utf-8", "surrogateescape")).hexdigest()
    folder = data / "banana/logs/ports"
    folder.mkdir(parents=True, exist_ok=True)
    log_path = folder / (ident + ".log")
    if log_path.exists():
        os.replace(log_path, folder / (ident + ".previous.log"))
    (folder / "last-log-path.txt").write_text(str(log_path) + "\n", encoding="utf-8")
    log = log_path.open("ab", buffering=0)
    def note(message):
        log.write((time.strftime("%Y-%m-%d %H:%M:%S") + " [PORT] " + message + "\n").encode("utf-8", "replace"))
    stopping = False
    def stop_signal(sig, frame):
        nonlocal stopping
        stopping = True
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop_signal)
    cmd = os.environ.get("BANANA_RA_CMD")
    pause_file = os.environ.get("BANANA_SA_PAUSE_FILE")
    fd = None
    if cmd:
        try:
            fd = os.open(cmd, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
            if not stat.S_ISFIFO(os.fstat(fd).st_mode):
                os.close(fd)
                fd = None
        except OSError as e:
            note("command channel unavailable: " + str(e))
    lease = os.environ.get("BANANA_DRM_LEASE_FD")
    pass_fds = ()
    if lease:
        try:
            lease_fd = int(lease)
            os.fstat(lease_fd)
            if lease_fd < 3:
                raise ValueError("invalid lease")
            pass_fds = (lease_fd,)
        except (ValueError, OSError) as e:
            note("invalid inherited lease: " + str(e))
            if fd is not None:
                os.close(fd)
            log.close()
            return 1
    child = None
    processes = PortProcesses(note)
    gpu = PortGPU(data,key,note,log,manager=script.name=="PortMaster.sh")
    def cleanup_group():
        processes.cleanup(child)
        if child is not None:
            child.wait(timeout=2)
    note("script=" + str(script))
    note("display=" + ("leased dual screen" if lease else "single screen"))
    buf = b""
    def startup_cancelled():
        nonlocal stopping,buf
        if fd is not None:
            try: buf+=os.read(fd,4096)
            except BlockingIOError: pass
            lines=buf.split(b"\n");buf=lines.pop()[-4096:]
            if any(line.strip()==b"QUIT" for line in lines):stopping=True
        return stopping
    try:
        env=gpu.start(os.environ.copy(),startup_cancelled)
        audio_fix=Path("/usr/lib/banana/ports/libbanana-port-audio.so")
        if script.name.casefold()=="doukutsu-rs.sh" and env.get("BANANA_PORT_AUDIO_RECOVERY","1")=="1" and audio_fix.is_file():
            env["BANANA_PORT_AUDIO_RECOVERY"]="1"
            env["LD_PRELOAD"]=str(audio_fix)+(" "+env["LD_PRELOAD"] if env.get("LD_PRELOAD") else "")
            note("CPAL playback recovery enabled")
        while not stopping:
            child = subprocess.Popen(["/bin/bash", str(script)], cwd=str(script.parent),
                                     stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True, pass_fds=pass_fds, env=env)
            note("launch pid=" + str(child.pid))
            paused = False
            restart = False
            while not stopping and child.poll() is None:
                if fd is None:
                    time.sleep(.1)
                elif select.select([fd], [], [], .1)[0]:
                    try:
                        buf += os.read(fd, 4096)
                    except BlockingIOError:
                        pass
                    lines = buf.split(b"\n")
                    buf = lines.pop()[-4096:]
                    for line in lines:
                        if line.strip() == b"QUIT":
                            stopping = True
                        elif line.strip() == b"RESET":
                            restart = True
                    if stopping or restart:
                        break
                wanted = bool(pause_file and os.path.isfile(pause_file))
                if wanted != paused:
                    if wanted: processes.pause()
                    else: processes.resume()
                    paused = wanted
                    note("paused" if paused else "resumed")
            rc = child.poll()
            note("exit=" + str(rc) + " request=" + ("quit" if stopping else "restart" if restart else "natural"))
            cleanup_group()
            child = None
            if stopping:
                return 0
            if not restart:
                return rc if rc is not None and rc >= 0 else 128 - (rc or 0)
            note("restarting")
        return 0
    except Exception as e:
        note("supervisor error: " + repr(e))
        return 1
    finally:
        try:
            cleanup_group()
            gpu.close()
        finally:
            if fd is not None: os.close(fd)
            log.close()


if __name__ == "__main__":
    try:
        result = main()
    finally:
        # Restore the original one-panel backlight on all normal/error exits.
        dark = os.environ.get("BANANA_PORT_DARK_BACKLIGHT", "")
        if dark.startswith("/sys/class/backlight/") and "/" not in dark[len("/sys/class/backlight/"):]:
            try:
                marker = Path("/run/banana/panel-off")
                if marker.read_text().strip() == dark:
                    marker.unlink()
            except OSError:
                pass
            try:
                Path(dark, "bl_power").write_text("0\n")
            except OSError:
                pass
    sys.exit(result)
