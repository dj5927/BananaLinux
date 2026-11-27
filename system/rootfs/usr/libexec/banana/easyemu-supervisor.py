#!/usr/bin/env python3
"""BananaOS standalone PPSSPP/Flycast launcher. Data-only runtime, leased display.

No driver is force unloaded; never modify the original ROM. An installed
runtime is pinned to the manifest supplied in the firmware. The supervisor
owns the GPU switch, child group, menu marker and persistent launch log.
"""
import configparser
import fcntl
import hashlib
import json
import os
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path


def read_conf(path):
    out = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.lstrip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return out


def settings(data, system, key):
    defaults = read_conf(data / "banana/emulator-defaults.conf")
    games = read_conf(data / "banana/rpg-per-game.conf")
    prefix = key.encode("utf-8", "surrogateescape").hex() + "."
    def get(k):
        return games.get(prefix + k) or defaults.get(system + "." + k) or "auto"
    return {k: get(k) for k in ("resolution", "frameskip", "fast_loading")}


def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def valid_bundle(runtime, manifest):
    if not (runtime / ".ready").is_file():
        return False
    if (runtime / ".ready").read_text().strip() != manifest["sha256"]:
        return False
    return all((runtime / p).is_file() for p in (
        "psp/PPSSPPSDL", "dreamcast/flycast", "lib/libmali.so.1",
        "lib/mali.json", "mali_kbase.ko"))


def recover_bundle_from_ota(data, manifest, archive, log, cancelled, progress):
    """Old OTA installers retain the downloaded tar; recover only the pinned runtime."""
    ver = manifest.get("ota_version", "")
    if not re.fullmatch(r"[0-9.]+", ver):
        return False
    name = archive.name
    for folder in (data / "banana/updates", data / "updates"):
        for board in ("rgds", "rgds-plus", "universal"):
            stem = "banana-" + board + "-" + ver + ".update"
            package = folder / (stem + ".tar")
            if not package.is_file():
                continue
            temp = archive.with_suffix(".ota-part")
            try:
                with tarfile.open(package, "r:") as tf:
                    # Only a single regular file of the manifest's exact size is accepted.
                    member = tf.getmember(stem + "/" + name)
                    if not member.isfile() or member.size != manifest["size"]:
                        raise RuntimeError("invalid embedded runtime")
                    log("recovering runtime from OTA " + package.name)
                    with tf.extractfile(member) as src, temp.open("wb") as dst:
                        done = 0
                        while True:
                            if cancelled():
                                raise InterruptedError("runtime recovery cancelled")
                            chunk = src.read(1024 * 1024)
                            if not chunk:
                                break
                            dst.write(chunk)
                            done += len(chunk)
                            progress("copying", str(min(100, done * 100 // member.size)) + "%")
                progress("verifying", "")
                if temp.stat().st_size != manifest["size"] or sha256(temp) != manifest["sha256"]:
                    raise RuntimeError("embedded runtime checksum mismatch")
                os.replace(temp, archive)
                log("embedded runtime checksum verified")
                return True
            except InterruptedError:
                raise
            except (OSError, KeyError, tarfile.TarError, RuntimeError) as e:
                log("OTA runtime recovery failed: " + repr(e))
            finally:
                temp.unlink(missing_ok=True)
    return False


def install_bundle(data, manifest, log, cancelled=lambda: False, progress=lambda phase, detail: None):
    version = manifest["version"]
    digest = manifest["sha256"]
    size = manifest["size"]
    url = manifest["url"]
    if (not re.fullmatch(r"[0-9.]+", version) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or not isinstance(size, int) or not 0 < size < 300_000_000
            or not url.startswith("https://github.com/dj5927/BananaLinux/releases/download/")):
        raise RuntimeError("invalid firmware runtime manifest")
    parent = data / "banana/easyemu/runtime"
    parent.mkdir(parents=True, exist_ok=True)
    dest = parent / version
    if valid_bundle(dest, manifest):
        log("using installed runtime " + version)
        return dest
    archive = data / "updates" / ("banana-easyemu-" + version + ".tar.gz")
    archive.parent.mkdir(parents=True, exist_ok=True)
    def archive_ok():
        return archive.is_file() and archive.stat().st_size == size and sha256(archive) == digest
    if not archive_ok():
        recover_bundle_from_ota(data, manifest, archive, log, cancelled, progress)
    if not archive_ok():
        log("runtime missing; downloading pinned bundle " + version)
        temp = archive.with_suffix(".part")
        temp.unlink(missing_ok=True)
        try:
            deadline = time.monotonic() + 200
            # Curl's ordinary --retry does not retry DNS failure (exit 6).
            # Use bounded explicit retries and preserve the panel while preparing.
            for attempt in range(3):
                progress("downloading", "0%")
                downloader = subprocess.Popen(["curl", "-fL", "--connect-timeout", "15",
                                "--max-time", "60", "-o", str(temp), url],
                               stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                try:
                    while downloader.poll() is None:
                        if cancelled():
                            raise InterruptedError("runtime download cancelled")
                        if time.monotonic() >= deadline:
                            raise TimeoutError("runtime download timed out")
                        have = temp.stat().st_size if temp.exists() else 0
                        progress("downloading", str(min(100, have * 100 // size)) + "%")
                        time.sleep(.1)
                    code = downloader.returncode
                finally:
                    if downloader.poll() is None:
                        downloader.kill()
                        downloader.wait()
                if not code:
                    break
                log("runtime download attempt " + str(attempt + 1) + " failed: " + str(code))
                if code not in (6, 7, 18, 28, 52, 55, 56, 92) or attempt == 2:
                    raise RuntimeError("runtime download failed: " + str(code))
                temp.unlink(missing_ok=True)
                for _ in range(30):
                    if cancelled(): raise InterruptedError("runtime download cancelled")
                    if time.monotonic() >= deadline: raise TimeoutError("runtime download timed out")
                    time.sleep(.1)
            progress("verifying", "")
            if temp.stat().st_size != size or sha256(temp) != digest:
                raise RuntimeError("runtime archive checksum mismatch")
            os.replace(temp, archive)
        finally:
            temp.unlink(missing_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=parent))
    try:
        with tarfile.open(archive, "r:gz") as tf:
            members = tf.getmembers()
            if len(members) > 10000 or sum(m.size for m in members) > 500_000_000:
                raise RuntimeError("oversized runtime bundle")
            for m in members:
                p = Path(m.name)
                if p.is_absolute() or ".." in p.parts or not (m.isfile() or m.isdir()):
                    raise RuntimeError("unsafe runtime member " + m.name)
            for i, m in enumerate(members):
                if cancelled():
                    raise InterruptedError("runtime install cancelled")
                tf.extract(m, staging, filter="data")
                progress("installing", str((i + 1) * 100 // max(1, len(members))) + "%")
        for exe in ("psp/PPSSPPSDL", "dreamcast/flycast"):
            (staging / exe).chmod(0o755)
        (staging / ".ready").write_text(digest + "\n")
        if not valid_bundle(staging, manifest):
            raise RuntimeError("runtime files missing")
        if dest.exists():
            shutil.rmtree(dest)
        os.replace(staging, dest)
        log("runtime checksum verified and installed " + version)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return dest


def ini_set(path, updates):
    # Preserve native comments/unknown keys, including repeated sections.
    # PPSSPP writes a UTF-8 BOM when saving its own INI files.
    # Decode it before comparing section headers; never append a duplicate section.
    text = path.read_text(encoding="utf-8-sig", errors="replace") if path.exists() else ""
    lines = text.splitlines()
    for section, keys in updates.items():
        start = next((i for i, line in enumerate(lines) if line.strip() == "[" + section + "]"), -1)
        if start < 0:
            lines += ["", "[" + section + "]"]
            start = len(lines) - 1
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        for k, v in keys.items():
            found = [i for i in range(start + 1, end)
                     if lines[i].split("=", 1)[0].strip() == k and "=" in lines[i]]
            if found:
                lines[found[-1]] = k + " = " + str(v)
            else:
                lines.insert(end, k + " = " + str(v))
                end += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".banana-new")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def psp_korean_defaults(ini, ctrl, fresh_ini=False, fresh_ctrl=False):
    """Migrate only the requested defaults, once; later native edits are kept."""
    marker = ini.parent / ".banana-korean-defaults-1"
    migrate = not marker.is_file()
    if not (migrate or fresh_ini or fresh_ctrl):
        return
    # The shipped SDL DB exposes the printed Nintendo layout:
    # A:b1 B:b0 X:b2 Y:b3. PPSSPP's SDL keycodes are 189,190,191,188.
    # Keep unrelated keyboard/pad bindings, and remove the four old pad-face
    # bindings before assigning their requested PSP counterparts.
    if migrate or fresh_ctrl:
        cfg = configparser.ConfigParser(interpolation=None, strict=False)
        cfg.optionxform = str
        cfg.read(ctrl, encoding="utf-8-sig")
        face = {"Circle": "10-189", "Cross": "10-190",
                "Triangle": "10-191", "Square": "10-188"}
        old = set(face.values())
        updates = {}
        for key, mapping in face.items():
            others = [s.strip() for s in cfg.get("ControlMapping", key, fallback="").split(",")
                      if s.strip() and s.strip() not in old]
            updates[key] = ",".join([mapping, *others])
        ini_set(ctrl, {"ControlMapping": updates})
    if migrate or fresh_ini:
        ini_set(ini, {"General": {"Language": "ko_KR", "UIScaleFactor": "-5"},
                      "SystemParam": {"ButtonPreference": "0"}})
    temp = marker.with_suffix(".new")
    temp.write_text("1\n", encoding="utf-8")
    os.replace(temp, marker)


def repair_dc_mapping(path):
    """Flycast stops reading a bind list at the first missing index."""
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    cfg = configparser.ConfigParser(interpolation=None, strict=False)
    cfg.optionxform = str
    cfg.read_string(text)
    if cfg.getint("emulator", "version", fallback=1) < 3:
        return
    start = next((i for i, line in enumerate(lines) if line.strip() == "[digital]"), -1)
    if start < 0:
        return
    end = next((i for i in range(start+1,len(lines)) if lines[i].strip().startswith("[")), len(lines))
    binds = []
    extra = []
    for line in lines[start+1:end]:
        match = re.match(r"\s*bind(\d+)\s*=\s*(.+?)\s*$", line)
        if match:
            binds.append((int(match.group(1)), match.group(2)))
        else:
            extra.append(line)
    values = [v for _,v in sorted(binds)]
    # The shipped v20-v22 mapping omitted bind5. If Flycast saved the
    # incomplete mapping, recover only the exact stock prefix.
    stock = {"0:btn_a","1:btn_b","2:btn_y","3:btn_x","9:btn_start"}
    backup = path.with_suffix(path.suffix + ".banana-v22-backup")
    if not backup.exists() and cfg.get("emulator","mapping_name",fallback="") == "RG DS Plus EasyCast" and set(values) == stock and len(values) == len(stock):
        values += ["13:btn_dpad1_up","14:btn_dpad1_down","15:btn_dpad1_left","16:btn_dpad1_right",
                   "4:btn_trigger_left","5:btn_trigger_right"]
    if sorted(binds) == list(enumerate(values)):
        return
    if not backup.exists():
        shutil.copyfile(path, backup)
    lines[start+1:end] = [f"bind{i} = {v}" for i,v in enumerate(values)] + extra
    temp = path.with_suffix(path.suffix + ".banana-new")
    temp.write_text("\n".join(lines)+"\n", encoding="utf-8")
    os.replace(temp,path)


def configure(runtime, user, system, opts, leased):
    env = os.environ.copy()
    env.update(HOME=str(user / "home"), XDG_CONFIG_HOME=str(user / "config"),
               XDG_DATA_HOME=str(user / "data"), SDL_VIDEODRIVER="kmsdrm",
               SDL_KMSDRM_FIRST="DSI-2", SDL_KMSDRM_REQUIRE_DRM_MASTER="0",
               EASYPSP_DRM="1", EASYCAST_DRM_PRESENT="1",
               EASYPSP_KEEP_OTHER_SCREEN="1", EASYCAST_KEEP_OTHER_SCREEN="1",
               EASYPSP_RESTART_CODE="75", EASYCAST_ASYNC_PRESENT="1",
               EASYCAST_SCREEN="top", XDG_RUNTIME_DIR="/run")
    env.pop("SDL_BANANA_PANELS", None)
    env.pop("EASYPSP_UPDATER", None)
    env.pop("EASYCAST_UPDATER", None)
    lib = runtime / "lib"
    # This bundle includes a dedicated Vulkan-enabled, lease-aware SDL.
    # Keep the existing RPG SDL untouched; it was built without Vulkan.
    env.update(LD_LIBRARY_PATH=str(lib),
               VK_ICD_FILENAMES=str(lib / "mali.json"), VK_DRIVER_FILES=str(lib / "mali.json"))
    for d in ("home", "config", "data"):
        (user / d).mkdir(parents=True, exist_ok=True)
    if system == "psp":
        ini = user / "config/ppsspp/PSP/SYSTEM/ppsspp.ini"
        ctrl = ini.with_name("controls.ini")
        ini.parent.mkdir(parents=True, exist_ok=True)
        fresh_ini = not ini.exists()
        fresh_ctrl = not ctrl.exists()
        if fresh_ini:
            ini_set(ini, {"General": {"CurrentDirectory": "/data/roms/psp"},
                          "Graphics": {"InternalResolution": "1", "FrameSkip": "0"}})
        if fresh_ctrl:
            shutil.copyfile(runtime / "psp/controls.ini", ctrl)
        psp_korean_defaults(ini, ctrl, fresh_ini, fresh_ctrl)
        # Ensure the panel menu event can be routed even with the default pad mapping.
        cfg = configparser.ConfigParser(interpolation=None, strict=False)
        cfg.optionxform = str
        cfg.read(ctrl, encoding="utf-8-sig")
        pause = cfg.get("ControlMapping", "Pause", fallback="")
        if "1-111" not in [p.strip() for p in pause.split(",")]:
            ini_set(ctrl, {"ControlMapping": {"Pause": ",".join(p for p in (pause,"1-111") if p)}})
        ini_set(ini, {"Graphics": {"GraphicsBackend": "3 (VULKAN)", "EasypspScreen": "0"}})
        # Native per-game settings may override the global ini; source
        # integration applies these explicit choices after native load.
        env["BANANA_EASY_RESOLUTION"] = opts["resolution"]
        env["BANANA_EASY_FRAMESKIP"] = opts["frameskip"]
        return env, [str(runtime / "psp/PPSSPPSDL"), "--fullscreen"], runtime / "psp"
    ini = user / "config/flycast/emu.cfg"
    ini.parent.mkdir(parents=True, exist_ok=True)
    if not ini.exists():
        text = (runtime / "dreamcast/defaults/emu.cfg").read_text()
        ini.write_text(text.replace("@@USERDATA@@", str(user)), encoding="utf-8")
    mappings = user / "config/flycast/mappings"
    mappings.mkdir(parents=True, exist_ok=True)
    m = mappings / "SDL_retrogame_joypad.cfg"
    if not m.exists():
        shutil.copyfile(runtime / "dreamcast/defaults/SDL_retrogame_joypad.cfg", m)
    for mapping in mappings.glob("SDL_retrogame_joypad*.cfg"):
        try:
            repair_dc_mapping(mapping)
        except (OSError, ValueError, configparser.Error) as e:
            print("Dreamcast mapping repair skipped:", mapping.name, e, flush=True)
    env["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
    cfg = configparser.ConfigParser(interpolation=None, strict=False)
    cfg.optionxform = str
    cfg.read(ini, encoding="utf-8-sig")
    renderer = cfg.get("config", "pvr.rend", fallback="4")
    # Keep native/user paths first, then search BananaOS's conventional BIOS
    # directories. This also migrates v20 settings without replacing saved data.
    (user / "bios").mkdir(parents=True, exist_ok=True)
    paths = [p.strip() for p in cfg.get("config", "Dreamcast.BiosPath", fallback="").split(";") if p.strip()]
    for path in (str(user / "bios"), "/data/bios/dc", "/data/bios/dreamcast", "/data/bios"):
        if path not in paths:
            paths.append(path)
    ini_set(ini, {"config": {"easycast.Screen": "0", "pvr.rend": renderer if renderer in ("4","5") else "4",
                            "Dreamcast.BiosPath": ";".join(paths)}})
    env["BANANA_EASY_RESOLUTION"] = opts["resolution"]
    env["BANANA_EASY_FRAMESKIP"] = opts["frameskip"]
    env["BANANA_EASY_FAST_LOADING"] = opts["fast_loading"]
    return env, [str(runtime / "dreamcast/flycast")], runtime / "dreamcast"


def main():
    system, rom = sys.argv[1:]
    if system not in ("psp", "dreamcast"):
        return 2
    data = Path("/data")
    key = os.environ.get("BANANA_GAME_KEY", system + "/" + Path(rom).name)
    folder = data / "banana/logs/easyemu"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (hashlib.sha256(key.encode("utf-8","surrogateescape")).hexdigest() + ".log")
    if path.exists():
        os.replace(path, path.with_suffix(".previous.log"))
    (folder / "last-log-path.txt").write_text(str(path) + "\n")
    with path.open("ab", buffering=0) as logf:
        def log(msg):
            logf.write((time.strftime("%Y-%m-%d %H:%M:%S") + " [EASYEMU] " + str(msg) + "\n").encode("utf-8","replace"))
        return run(system, rom, data, key, log, logf)


def run(system, rom, data, key, log, logf):
    stopping = False
    status_path = os.environ.get("BANANA_EASY_STATUS_FILE", "")
    last_status = None
    def progress(phase, detail=""):
        nonlocal last_status
        current = (phase, detail)
        if current == last_status:
            return
        last_status = current
        if not re.fullmatch(r"/run/banana/mkxp-status-[0-9]+", status_path):
            return
        try:
            target = Path(status_path)
            temp = target.with_suffix(".new")
            temp.write_text(phase + "\n" + detail + "\n", encoding="utf-8")
            os.replace(temp, target)
        except OSError:
            pass
    def show_failure(detail):
        progress("failed", detail)
        if os.environ.get("BANANA_DRM_LEASE_FD") and not stopping:
            time.sleep(2)
    def stop(sig, frame):
        nonlocal stopping
        stopping = True
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    lockfd = os.open("/run/banana/easyemu-gpu.lock", os.O_CREAT|os.O_RDWR|os.O_CLOEXEC, 0o600)
    fd = None
    child = None
    removed_panfrost = False
    loaded_mali = False
    freq = Path("/sys/class/devfreq/fde60000.gpu")
    saved_freq = {}
    menu = Path("/run/banana/easyemu-menu-" + str(os.getpid()))
    quitfile = Path("/run/banana/easyemu-quit-" + str(os.getpid()))
    pausefile = os.environ.get("BANANA_SA_PAUSE_FILE")
    def command(*args, required=True):
        try:
            result = subprocess.run(args, stdout=logf, stderr=subprocess.STDOUT, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as e:
            log("command failed: " + " ".join(args) + " " + repr(e))
            if required: raise
            return 1
        log("command " + " ".join(args) + " => " + str(result.returncode))
        if required and result.returncode:
            raise RuntimeError("command failed: " + " ".join(args))
        return result.returncode
    def send(sig):
        if child is not None:
            try: os.killpg(child.pid, sig)
            except ProcessLookupError: pass
    def cleanup(graceful=True):
        nonlocal child
        if child is None: return
        send(signal.SIGCONT)
        if child.poll() is None and graceful:
            quitfile.touch()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: pass
        send(signal.SIGTERM)
        try: child.wait(timeout=2)
        except subprocess.TimeoutExpired: pass
        send(signal.SIGKILL)
        try: child.wait(timeout=2)
        except subprocess.TimeoutExpired: log("child reap timeout")
        child = None
        menu.unlink(missing_ok=True)
        quitfile.unlink(missing_ok=True)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        log("system=" + system + " rom=" + rom)
        cmd = os.environ.get("BANANA_RA_CMD")
        if cmd:
            fd = os.open(cmd, os.O_RDWR|os.O_NONBLOCK|os.O_CLOEXEC|os.O_NOFOLLOW)
            if not stat.S_ISFIFO(os.fstat(fd).st_mode):
                raise RuntimeError("invalid command channel")
        startup_buf = b""
        def startup_cancelled():
            nonlocal stopping, startup_buf
            if fd is not None:
                try: startup_buf += os.read(fd,4096)
                except BlockingIOError: pass
                lines = startup_buf.split(b"\n")
                startup_buf = lines.pop()[-4096:]
                if any(line.strip()==b"QUIT" for line in lines): stopping=True
            return stopping
        manifest = json.loads(Path("/usr/share/banana/easyemu/bundle.json").read_text())
        progress("starting", "")
        runtime = install_bundle(data, manifest, log, startup_cancelled, progress)
        if startup_cancelled(): return 0
        progress("starting", "")
        module = runtime / "mali_kbase.ko"
        magic = re.search(rb"vermagic=([^\0]+)", module.read_bytes())
        if not magic or magic[1].split()[0].decode() != os.uname().release or os.uname().machine != "aarch64":
            raise RuntimeError("GPU module kernel/architecture mismatch")
        if Path("/sys/module/mali_kbase").exists():
            raise RuntimeError("GPU already owned by another Mali session")
        lease = os.environ.get("BANANA_DRM_LEASE_FD")
        passfds = ()
        if lease:
            n = int(lease)
            if n < 3: raise RuntimeError("invalid display lease")
            os.fstat(n)
            passfds = (n,)
        user = data / "banana/easyemu/userdata" / system
        opts = settings(data, system, key)
        log("settings=" + json.dumps(opts) + " lease=" + str(bool(lease)))
        env, args, cwd = configure(runtime, user, system, opts, bool(lease))
        env.update(BANANA_SA_MENU_FILE=str(menu), BANANA_SA_QUIT_FILE=str(quitfile))
        for name in ("max_freq", "min_freq", "governor"):
            try: saved_freq[name] = (freq / name).read_text().strip()
            except OSError: pass
        if Path("/sys/module/panfrost").exists():
            command("rmmod", "panfrost")
            removed_panfrost = True
        command("insmod", str(module))
        loaded_mali = True
        if not Path("/dev/mali0").exists():
            raise RuntimeError("Mali device not present")
        for p,v in ((freq / "governor","performance"),
                    (Path("/sys/devices/platform/fde60000.gpu/power_policy"),"coarse_demand")):
            try: p.write_text(v)
            except OSError as e: log(e)
        restarts = 0
        buf = b""
        while not stopping:
            menu.unlink(missing_ok=True); quitfile.unlink(missing_ok=True)
            offset = os.fstat(logf.fileno()).st_size
            child = subprocess.Popen(args + [rom], cwd=cwd, env=env, stdout=logf,
                                     stderr=subprocess.STDOUT, start_new_session=True, pass_fds=passfds)
            log("started pid=" + str(child.pid))
            progress("running", "")
            paused = False
            restart = False
            while not stopping and child.poll() is None:
                if fd is None: time.sleep(.1)
                elif select.select([fd], [], [], .1)[0]:
                    try: buf += os.read(fd, 4096)
                    except BlockingIOError: pass
                    lines = buf.split(b"\n")
                    buf = lines.pop()[-4096:]
                    for line in lines:
                        c = line.strip()
                        if c == b"QUIT": stopping = True
                        elif c == b"RESET": restart = True
                        elif c == b"MENU_TOGGLE":
                            send(signal.SIGCONT); paused=False
                            menu.touch()
                            log("native menu requested")
                if stopping or restart: break
                wanted = bool(pausefile and Path(pausefile).is_file())
                if wanted != paused:
                    send(signal.SIGSTOP if wanted else signal.SIGCONT)
                    paused = wanted
                    log("paused" if paused else "resumed")
            code = child.poll()
            log("exit=" + str(code) + " quit=" + str(stopping) + " restart=" + str(restart))
            cleanup(graceful=stopping or restart)
            if stopping: return 0
            if restart: continue
            if system == "psp" and code == 75 and restarts < 4:
                restarts += 1
                continue
            if system == "dreamcast":
                try:
                    with open(logf.name, "rb") as f:
                        f.seek(max(offset, os.fstat(f.fileno()).st_size - 131072))
                        output = f.read()
                    if b"Failed to locate bootfile" in output:
                        show_failure("Boot file missing")
                        return 1
                except OSError as e:
                    log("cannot inspect boot result: " + str(e))
            if code:
                show_failure("See game log")
            return code if code is not None and code >= 0 else 128 - (code or 0)
        return 0
    except Exception as e:
        log("ERROR " + repr(e))
        if not stopping:
            show_failure("Check Wi-Fi / runtime" if "runtime" in str(e).lower() else "See game log")
        return 0 if stopping else 1
    finally:
        cleanup()
        if fd is not None: os.close(fd)
        if loaded_mali:
            for _ in range(10):
                if not Path("/sys/module/mali_kbase").exists(): break
                if command("rmmod", "mali_kbase", required=False) == 0: break
                time.sleep(.25)
        if removed_panfrost:
            command("modprobe", "panfrost", required=False)
            for name, value in saved_freq.items():
                try: (freq / name).write_text(value)
                except OSError as e: log("restore " + name + ": " + str(e))
        os.close(lockfd)


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        dark = os.environ.get("BANANA_PORT_DARK_BACKLIGHT", "")
        if re.fullmatch(r"/sys/class/backlight/[^/]+", dark):
            try:
                marker = Path("/run/banana/panel-off")
                if marker.read_text().strip() == dark: marker.unlink()
            except OSError: pass
            try: Path(dark, "bl_power").write_text("0\n")
            except OSError: pass
    sys.exit(rc)
