#!/usr/bin/python3
"""Standalone DuckStation with the Banana SA panel's command/lease contract."""
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import resource
import shutil
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

def import_bios(data, bios, log):
    # FAT/exFAT data partitions may not support symbolic links.
    # Keep all original files, especially existing private BIOS copies.
    for folder in (data/"bios", data/"bios/psx"):
        if not folder.is_dir(): continue
        for src in sorted(folder.iterdir()):
            try:
                if not src.is_file() or src.stat().st_size not in (524288,4194304):
                    continue
                dest=bios/src.name
                if dest.exists() and not dest.is_symlink():
                    continue
                tmp=bios/("."+src.name+".banana-import")
                try:
                    with src.open("rb") as inp, tmp.open("xb") as out:
                        shutil.copyfileobj(inp,out)
                        out.flush();os.fsync(out.fileno())
                    if tmp.stat().st_size!=src.stat().st_size:
                        raise OSError("BIOS size changed during copy")
                    os.replace(tmp,dest)
                    log("BIOS imported: "+str(src)+" -> "+str(dest))
                finally:
                    tmp.unlink(missing_ok=True)
            except OSError as e:
                log("BIOS import failed: "+str(src)+" "+str(e))
    log("BIOS directory: "+str(bios))
    for f in sorted(bios.iterdir()):
        try:
            if f.is_file(): log("BIOS candidate: "+f.name+" bytes="+str(f.stat().st_size))
        except OSError as e: log("BIOS candidate unavailable: "+f.name+" "+str(e))

def prepare(data, schema=SCHEMA, log=lambda msg: None):
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
        "Main.FastForwardSpeed":"2.0", "Main.TurboSpeed":"2.0",
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
    # Use private BIOS copies without relying on filesystem symlink support.
    bios=user/"bios"
    import_bios(data,bios,log)
    updates["BIOS.SearchDirectory"]=str(bios)
    update_ini(ini, updates)
    return user, ini, cfg, opts, selected

class MaliSession:
    """Use the same pinned runtime/module transaction as EasyPSP/EasyCast."""
    def __init__(self, log, logfile):
        self.log=log
        self.logfile=logfile
        self.removed=False
        self.loaded=False
        self.freq=Path("/sys/class/devfreq/fde60000.gpu")
        self.saved={}
    def command(self,*args,required=True):
        try:
            rc=subprocess.run(args,stdout=self.logfile,stderr=subprocess.STDOUT,timeout=15).returncode
        except (OSError,subprocess.TimeoutExpired) as e:
            self.log("GPU command failed: "+repr(e))
            if required: raise
            return 1
        self.log("GPU command "+" ".join(args)+" => "+str(rc))
        if required and rc: raise RuntimeError("GPU command failed: "+" ".join(args))
        return rc
    def start(self,data,env,cancelled,progress):
        spec=importlib.util.spec_from_file_location("banana_easyemu","/usr/libexec/banana/easyemu-supervisor.py")
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        manifest=json.loads(Path("/usr/share/banana/easyemu/bundle.json").read_text())
        runtime=mod.install_bundle(data,manifest,self.log,cancelled,progress)
        if cancelled(): raise RuntimeError("cancelled")
        module=runtime/"mali_kbase.ko"
        magic=re.search(rb"vermagic=([^\0]+)",module.read_bytes())
        if not magic or magic[1].split()[0].decode()!=os.uname().release or os.uname().machine!="aarch64":
            raise RuntimeError("GPU module kernel/architecture mismatch")
        if Path("/sys/module/mali_kbase").exists(): raise RuntimeError("Mali session already active")
        for name in ("max_freq","min_freq","governor"):
            try: self.saved[name]=(self.freq/name).read_text().strip()
            except OSError: pass
        if Path("/sys/module/panfrost").exists():
            self.command("rmmod","panfrost");self.removed=True
        self.command("insmod",str(module));self.loaded=True
        if not Path("/dev/mali0").exists(): raise RuntimeError("Mali device missing")
        for path,value in ((self.freq/"governor","performance"),
                (Path("/sys/devices/platform/fde60000.gpu/power_policy"),"coarse_demand")):
            try: path.write_text(value)
            except OSError as e: self.log("GPU policy: "+str(e))
        lib=runtime/"lib"
        env.update(LD_LIBRARY_PATH=str(lib),VK_ICD_FILENAMES=str(lib/"mali.json"),
                   VK_DRIVER_FILES=str(lib/"mali.json"),BANANA_DUCK_VK_DRM="1")
        self.log("Mali Vulkan runtime="+str(runtime))
    def close(self):
        if self.loaded:
            for _ in range(10):
                if not Path("/sys/module/mali_kbase").exists(): break
                if self.command("rmmod","mali_kbase",required=False)==0: break
                time.sleep(.25)
        if self.removed:
            if Path("/sys/module/mali_kbase").exists():
                self.log("ERROR: Mali still in use; refusing conflicting Panfrost load")
                return
            self.command("modprobe","panfrost",required=False)
            for name,value in self.saved.items():
                try: (self.freq/name).write_text(value)
                except OSError as e: self.log("GPU restore: "+str(e))

def sync_native(ini,cfg,opts,selected):
    native=read_values(ini, True)
    old=read_values(cfg)
    # Preserve user-selected panel and unrelated values. Only sync supported
    # values actually changed in the native global settings file.
    changed=False
    for k,(default,allowed) in opts.items():
        if "." not in k: continue
        v=native.get(k)
        # A BananaOS menu setting changed while the game was running takes
        # precedence over native settings written on shutdown.
        if k in old and old[k] != selected[k]:
            continue
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
    stopped=False; child=None; fd=None; ready=False; lockfd=None; mali=None; quick=None
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
            user,ini,cfg,opts,selected=prepare(data,schema,msg)
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
            for k in ("LD_PRELOAD","LD_LIBRARY_PATH","VK_ICD_FILENAMES","VK_DRIVER_FILES","BANANA_DUCK_VK_DRM"):
                env.pop(k,None)
            env["BANANA_DUCK_RENDERER"]=selected["GPU.Renderer"]
            if selected["GPU.Renderer"]=="Vulkan":
                startup_buf=b""
                def cancelled():
                    nonlocal stopped,startup_buf
                    if fd is not None:
                        try: startup_buf+=os.read(fd,4096)
                        except BlockingIOError: pass
                        lines=startup_buf.split(b"\n");startup_buf=lines.pop()[-4096:]
                        if any(line.strip()==b"QUIT" for line in lines): stopped=True
                    return stopped
                mali=MaliSession(msg,log)
                mali.start(data,env,cancelled,progress)
                if cancelled(): return 0
            for m in markers.values(): m.unlink(missing_ok=True)
            from sa_quick import QuickBridge
            quick=QuickBridge(run_dir,lambda detail: progress("running",detail),msg)
            env.update(quick.env())
            msg("rom="+rom+" lease="+str(bool(lease))+" settings="+str(selected))
            resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            child=subprocess.Popen([str(engine),"-batch","-fullscreen","-settings",str(ini),"--",rom],
                cwd=str(user),env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,pass_fds=passed)
            # A cold Vulkan shader/pipeline cache may take longer on RK3566.
            deadline=time.monotonic()+(120 if mali is not None else 40);buf=b""
            while child.poll() is None and not stopped:
                quick.poll()
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
                        elif ready: quick.command(c)
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
            if quick is not None: quick.close()
            if fd is not None: os.close(fd)
            if mali is not None: mali.close()
            if lockfd is not None: os.close(lockfd)
            bl=os.environ.get("BANANA_PORT_DARK_BACKLIGHT","")
            if re.fullmatch(r"/sys/class/backlight/[^/]+",bl):
                try:
                    Path("/run/banana/panel-off").unlink(missing_ok=True)
                    (Path(bl)/"bl_power").write_text("0")
                except OSError: pass

if __name__=="__main__":
    sys.exit(run(sys.argv[1],Path("/data")) if len(sys.argv)==2 else 2)
