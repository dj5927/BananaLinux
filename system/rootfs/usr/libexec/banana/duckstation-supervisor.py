#!/usr/bin/python3
"""Standalone DuckStation with the Banana SA panel's command/lease contract."""
import fcntl
import hashlib
import os
import re
import resource
import select
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

SCHEMA = Path("/usr/share/banana/duckstation-options.tsv")
ENGINE = Path("/usr/lib/banana/duckstation/duckstation-nogui")

def options(schema):
    rows = {}
    for line in schema.read_text(encoding="utf-8").splitlines():
        key, default, label, help_, allowed, names = line.split("\t")
        values = allowed.split("|")
        assert default in values and len(values) == len(names.split("|")) and key not in rows
        rows[key] = (default, values)
    return rows

def read_values(path, ini=False):
    out, section = {}, ""
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if ini and line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
            elif "=" in line and not line.startswith(("#", ";")):
                key, value = line.split("=", 1)
                out[(section+"." if ini else "")+key.strip()] = value.strip().strip('"')
    return out

def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".banana-new")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def update_ini(path, changes):
    # Keep all unmanaged settings, including duplicate native bindings.
    text = path.read_text(encoding="utf-8-sig", errors="replace") if path.exists() else ""
    lines = text.splitlines()
    remaining = dict(changes)
    output, section = [], ""
    def flush():
        for k in list(remaining):
            s, name = k.split(".",1)
            if s == section:
                output.append(name+" = "+remaining.pop(k))
    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith("[") and trimmed.endswith("]"):
            flush()
            section = trimmed[1:-1]
        elif "=" in trimmed and not trimmed.startswith(("#",";")):
            key = section+"."+trimmed.split("=",1)[0].strip()
            if key in changes: continue
        output.append(line)
    flush()
    for sec in dict.fromkeys(k.split(".",1)[0] for k in remaining):
        section=sec
        output.extend(["", "["+section+"]"])
        flush()
    atomic_write(path, "\n".join(output)+"\n")

def prepare(data, schema=SCHEMA):
    opts = options(schema)
    user = data/"banana/duckstation"
    cfg = data/"banana/duckstation.conf"
    ini = user/"settings.ini"
    home = user/"home"
    home.mkdir(parents=True, exist_ok=True)
    # Distinct memory cards/states: no overwrite of RetroArch's saves.
    for folder in ("memcards", "savestates", "cache", "gamesettings", "bios"):
        (user/folder).mkdir(exist_ok=True)
    wanted=read_values(cfg)
    current=read_values(ini, True)
    selected={k:wanted.get(k,d) if wanted.get(k,d) in allowed else d
              for k,(d,allowed) in opts.items()}
    updates={k:v for k,v in selected.items() if "." in k}
    updates.update({
        "Main.SettingsVersion":"3", "Main.StartFullscreen":"true",
        "Main.PauseOnMenu":"true", "Main.PauseOnFocusLoss":"false",
        "Main.ConfirmPowerOff":"false", "Main.InhibitScreensaver":"true",
        "Main.SyncToHostRefreshRate":"false", "Main.StartPaused":"false",
        "CPU.OverclockEnable":"false", "GPU.FullscreenMode":"",
        "Audio.Backend":"SDL", "Logging.LogToConsole":"true",
        "Logging.LogLevel":"Info", "InputSources.SDL":"true",
        "InputSources.SDLControllerEnhancedMode":"false", "Cheevos.Enabled":"false",
        "BIOS.SearchDirectory":str(data/"bios"),
        "MemoryCards.Directory":str(user/"memcards"),
        "Folders.SaveStates":str(user/"savestates"),
        "MemoryCards.Card1Type":"PerGameTitle", "MemoryCards.Card2Type":"None",
    })
    if not ini.exists():
        pad={"Type":"AnalogController","Up":"DPadUp","Down":"DPadDown",
             "Left":"DPadLeft","Right":"DPadRight",
             "Triangle":"X","Circle":"A","Cross":"B","Square":"Y",
             "Select":"Back","Start":"Start","L1":"LeftShoulder","R1":"RightShoulder",
             "L2":"+LeftTrigger","R2":"+RightTrigger","L3":"LeftStick","R3":"RightStick",
             "LLeft":"-LeftX","LRight":"+LeftX","LDown":"+LeftY","LUp":"-LeftY",
             "RLeft":"-RightX","RRight":"+RightX","RDown":"+RightY","RUp":"-RightY"}
        updates.update({"Pad1."+k:("SDL-0/"+v if k!="Type" else v) for k,v in pad.items()})
        updates.update({"Pad"+str(n)+".Type":"None" for n in range(2,9)})
    # The lower panel/F+X owns menu dispatch; avoid an overlapping SDL chord.
    updates["Hotkeys.OpenPauseMenu"]=""
    # Use the normal BIOS directory. Import PS1 BIOS files from its psx
    # subfolder via a private directory of symlinks, without changing originals.
    bios=user/"bios"
    for folder in (data/"bios",data/"bios/psx"):
        if folder.is_dir():
            for f in folder.iterdir():
                try:
                    if f.is_file() and f.stat().st_size in (524288,4194304):
                        dest=bios/f.name
                        if not dest.exists() and not dest.is_symlink(): dest.symlink_to(f)
                except OSError: pass
    updates["BIOS.SearchDirectory"]=str(bios)
    update_ini(ini, updates)
    return user, ini, cfg, opts, selected

def sync_native(ini,cfg,opts,selected):
    native=read_values(ini, True)
    old=read_values(cfg)
    # Preserve user-selected panel and unrelated values. Only sync supported
    # values actually changed in the native global settings file.
    changed=False
    for k,(default,allowed) in opts.items():
        if "." not in k: continue
        v=native.get(k)
        if v in allowed and v != selected[k]:
            old[k]=v;changed=True
    if changed: atomic_write(cfg, "".join(k+" = "+v+"\n" for k,v in old.items()))

def run(rom, data, engine=ENGINE, schema=SCHEMA, run_dir=Path("/run/banana")):
    key=os.environ.get("BANANA_GAME_KEY", "psx/"+Path(rom).name)
    logs=data/"banana/logs/duckstation"
    logs.mkdir(parents=True, exist_ok=True)
    logpath=logs/(hashlib.sha256(key.encode("utf-8","surrogateescape")).hexdigest()+".log")
    if logpath.exists(): os.replace(logpath,logpath.with_suffix(".previous.log"))
    (logs/"last-log-path.txt").write_text(str(logpath)+"\n")
    stopped=False; child=None; fd=None; ready=False; lockfd=None
    markers={name:run_dir/("duck-"+name+"-"+str(os.getpid()))
             for name in ("ready","menu","quit","reset")}
    status=os.environ.get("BANANA_EASY_STATUS_FILE","")
    def progress(phase, detail=""):
        if re.fullmatch(r"/run/banana/mkxp-status-[0-9]+",status):
            try: atomic_write(Path(status),phase+"\n"+detail+"\n")
            except OSError: pass
    def stop(sig,frame):
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP): signal.signal(sig,stop)
    def signal_child(sig):
        if child is not None and child.poll() is None:
            try: os.killpg(child.pid,sig)
            except ProcessLookupError: pass
    with logpath.open("ab",buffering=0) as log:
        def msg(s): log.write((time.strftime("%Y-%m-%d %H:%M:%S")+" [DUCK] "+str(s)+"\n").encode("utf-8","replace"))
        try:
            progress("starting")
            lockfd=os.open(run_dir/"easyemu-gpu.lock",os.O_CREAT|os.O_RDWR|os.O_CLOEXEC,0o600)
            fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if not Path(rom).is_file(): raise RuntimeError("Game file missing")
            # Do not switch or unload any GPU driver. Mesa/Panfrost is shared
            # with RetroArch and remains untouched.
            if Path("/sys/module/mali_kbase").exists():
                raise RuntimeError("GPU already owned by a Mali session")
            lease=os.environ.get("BANANA_DRM_LEASE_FD")
            passed=()
            if lease:
                n=int(lease);assert n>=3
                os.fstat(n);passed=(n,)
            fifo=os.environ.get("BANANA_RA_CMD")
            if fifo:
                fd=os.open(fifo,os.O_RDWR|os.O_NONBLOCK|os.O_CLOEXEC|os.O_NOFOLLOW)
                if not stat.S_ISFIFO(os.fstat(fd).st_mode): raise RuntimeError("invalid command channel")
            user,ini,cfg,opts,selected=prepare(data,schema)
            env=os.environ.copy()
            env.update(HOME=str(user/"home"),XDG_CONFIG_HOME=str(user/"config"),
                       DUCKSTATION_NOGUI_PLATFORM="vty",SDL_AUDIODRIVER="alsa",
                       SDL_VIDEODRIVER="dummy",XDG_RUNTIME_DIR="/run",
                       BANANA_DUCK_READY_FILE=str(markers["ready"]),
                       BANANA_SA_MENU_FILE=str(markers["menu"]),BANANA_SA_QUIT_FILE=str(markers["quit"]),
                       BANANA_DUCK_RESET_FILE=str(markers["reset"]))
            (user/"config").mkdir(exist_ok=True)
            # DuckStation looks for a data root named duckstation beneath XDG_CONFIG_HOME.
            env["XDG_CONFIG_HOME"]=str(user.parent)
            for k in ("LD_PRELOAD","LD_LIBRARY_PATH","VK_ICD_FILENAMES","VK_DRIVER_FILES"):
                env.pop(k,None)
            for m in markers.values(): m.unlink(missing_ok=True)
            msg("rom="+rom+" lease="+str(bool(lease))+" settings="+str(selected))
            resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            child=subprocess.Popen([str(engine),"-batch","-fullscreen","-settings",str(ini),"--",rom],
                cwd=str(user),env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,pass_fds=passed)
            deadline=time.monotonic()+40;buf=b""
            while child.poll() is None and not stopped:
                if not ready and markers["ready"].is_file():
                    ready=True;progress("running");msg("Game boot completed")
                if not ready and time.monotonic()>deadline:
                    raise RuntimeError("game boot timed out")
                if fd is None: time.sleep(.1);continue
                if select.select([fd],[],[],.1)[0]:
                    try: buf+=os.read(fd,4096)
                    except BlockingIOError: pass
                    lines=buf.split(b"\n");buf=lines.pop()[-4096:]
                    for line in lines:
                        c=line.strip()
                        if c==b"QUIT": stopped=True
                        elif c==b"MENU_TOGGLE": markers["menu"].touch()
                        elif c==b"RESET": markers["reset"].touch()
            if stopped: return 0
            code=child.returncode
            msg("exit="+str(code))
            if not ready or code:
                progress("failed","See game log");time.sleep(2)
                return 1
            return 0
        except Exception as e:
            msg("ERROR "+repr(e))
            if not stopped: progress("failed","See game log");time.sleep(2)
            return 0 if stopped else 1
        finally:
            if child is not None:
                if child.poll() is None:
                    markers["quit"].touch()
                    try: child.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        signal_child(signal.SIGTERM)
                        try: child.wait(timeout=2)
                        except subprocess.TimeoutExpired: signal_child(signal.SIGKILL);child.wait(timeout=2)
                if ready:
                    try: sync_native(ini,cfg,opts,selected)
                    except OSError as e: msg("settings sync: "+repr(e))
            for m in markers.values(): m.unlink(missing_ok=True)
            if fd is not None: os.close(fd)
            if lockfd is not None: os.close(lockfd)
            bl=os.environ.get("BANANA_PORT_DARK_BACKLIGHT","")
            if re.fullmatch(r"/sys/class/backlight/[^/]+",bl):
                try:
                    Path("/run/banana/panel-off").unlink(missing_ok=True)
                    (Path(bl)/"bl_power").write_text("0")
                except OSError: pass

if __name__=="__main__":
    sys.exit(run(sys.argv[1],Path("/data")) if len(sys.argv)==2 else 2)
