#!/usr/bin/python3
"""Native MKXP runtime selection. Never execute game code during inspection."""
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import zlib

MODES = ("ruby18", "ruby19", "ruby31", "ruby32")
REV = 5
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_SOURCE = 32 * 1024 * 1024
STOP_SIGNALS = tuple(getattr(signal,n) for n in ("SIGTERM","SIGINT","SIGHUP") if hasattr(signal,n))

def log(message):
    print(time.strftime("%Y-%m-%d %H:%M:%S") + " [MKXP] " + str(message), flush=True)

_missing_codecs=set()
_reported_codecs=set()

def iconv_decode(raw, encoding):
    """Use the firmware's existing glibc gconv modules when Python lacks CJK codecs."""
    import ctypes as c
    libc=c.CDLL("libc.so.6",use_errno=True)
    libc.iconv_open.argtypes=[c.c_char_p,c.c_char_p]
    libc.iconv_open.restype=c.c_void_p
    libc.iconv.argtypes=[c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(c.c_size_t),c.POINTER(c.c_void_p),c.POINTER(c.c_size_t)]
    libc.iconv.restype=c.c_size_t
    libc.iconv_close.argtypes=[c.c_void_p]
    libc.iconv_close.restype=c.c_int
    cd=libc.iconv_open(b"UTF-8",encoding.upper().encode("ascii"))
    if cd is None or cd==c.c_void_p(-1).value:
        raise LookupError("system iconv unavailable: "+encoding)
    try:
        src=c.create_string_buffer(raw)
        dst=c.create_string_buffer(len(raw)*4+4)
        ip=c.c_void_p(c.addressof(src)); op=c.c_void_p(c.addressof(dst))
        il=c.c_size_t(len(raw)); ol=c.c_size_t(len(dst))
        ret=libc.iconv(cd,c.byref(ip),c.byref(il),c.byref(op),c.byref(ol))
        if ret==c.c_size_t(-1).value or il.value:
            raise UnicodeError("invalid "+encoding+" path")
        return dst.raw[:len(dst)-ol.value].decode("utf-8")
    finally:
        libc.iconv_close(cd)

def decoded_paths(raw):
    # ASCII paths are identical in all these encodings. Never load optional
    # codecs just to decode the standard Data/Scripts.* member.
    if raw.isascii():
        yield raw.decode("ascii")
        return
    seen=set()
    for encoding in ("utf-8","cp949","cp932"):
        try:
            if encoding in _missing_codecs: raise LookupError(encoding)
            name=raw.decode(encoding)
        except LookupError:
            _missing_codecs.add(encoding)
            try:
                name=iconv_decode(raw,encoding)
            except (LookupError,ImportError,OSError,AttributeError,UnicodeError):
                if encoding not in _reported_codecs:
                    log("Optional path codec unavailable or invalid: "+encoding)
                    _reported_codecs.add(encoding)
                continue
        except UnicodeError:
            continue
        if name not in seen:
            seen.add(name)
            yield name

class MarshalReader:
    # Restricted data-only subset of Marshal 4.8. No user-defined objects,
    # hooks, classes, evaluation, or allocation based on unchecked lengths.
    def __init__(self, data):
        self.data, self.pos, self.objects, self.symbols = data, 0, [], []
        self.nodes = 0
    def take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError("truncated marshal")
        out = self.data[self.pos:self.pos+n]
        self.pos += n
        return out
    def integer(self):
        c = int.from_bytes(self.take(1), "little", signed=True)
        if c == 0: return 0
        if c > 4: return c - 5
        if c < -4: return c + 5
        value = int.from_bytes(self.take(abs(c)), "little")
        return value - (1 << (8 * abs(c))) if c < 0 else value
    def count(self, limit):
        n = self.integer()
        if not 0 <= n <= limit: raise ValueError("marshal length limit")
        return n
    def item(self, depth=0):
        self.nodes += 1
        if depth > 32 or self.nodes > 250000: raise ValueError("marshal complexity limit")
        t = self.take(1)
        if t == b"0": return None
        if t == b"T": return True
        if t == b"F": return False
        if t == b"i": return self.integer()
        if t == b"[":
            n = self.count(20000)
            a = []
            self.objects.append(a)
            for _ in range(n): a.append(self.item(depth+1))
            return a
        if t == b'"':
            b = self.take(self.count(MAX_ARCHIVE))
            self.objects.append(b)
            return b
        if t == b":":
            b = self.take(self.count(65536))
            self.symbols.append(b)
            return b
        if t in (b";", b"@"):
            a = self.symbols if t == b";" else self.objects
            i = self.integer()
            if not 0 <= i < len(a): raise ValueError("invalid marshal link")
            return a[i]
        if t == b"I":
            v = self.item(depth+1)
            for _ in range(self.count(64)):
                self.item(depth+1); self.item(depth+1)
            return v
        raise ValueError("unsupported marshal tag " + repr(t))
    def read(self):
        if self.take(2) != b"\x04\x08": raise ValueError("unsupported marshal version")
        return self.item()

def bounded_read(path, limit):
    with path.open("rb") as f:
        data = f.read(limit + 1)
    if len(data) > limit: raise ValueError("file size limit")
    return data

def project_file(root, name):
    path = root
    for part in name.replace("\\", "/").split("/"):
        if not part or part in (".", ".."): return None
        if not path.is_dir(): return None
        matches = sorted((p for p in itertools.islice(path.iterdir(),4097) if p.name.casefold() == part.casefold()), key=lambda p: p.name)
        if not matches: return None
        path = matches[0]
        if path.is_symlink(): return None
    return path if path.is_file() else None

def script_archive_sections(raw):
    obj=MarshalReader(raw).read()
    if not isinstance(obj,list): raise ValueError("script archive root is not array")
    total=0; result=[]
    for entry in obj:
        if not isinstance(entry,list) or len(entry)<3 or not isinstance(entry[2],bytes): continue
        limit=min(4*1024*1024, MAX_SOURCE-total)
        decomp=zlib.decompressobj()
        src=decomp.decompress(entry[2],limit+1)
        if not decomp.eof or len(src)>limit: raise ValueError("script inflation limit or invalid stream")
        total+=len(src); result.append(src)
    return result

def read_rgss_scripts(path, wanted):
    # RGSSAD v1/v3 format, matching mkxp-z's read-only archive implementation.
    # Only read the script member; never unpack other assets.
    mask=0xffffffff
    wanted={p.replace("\\","/").casefold() for p in wanted}
    def advance(k): return (k*7+3)&mask
    def matches(raw):
        return any(name.replace("\\","/").casefold() in wanted for name in decoded_paths(raw))
    with path.open("rb") as f:
        length=path.stat().st_size
        def take(n):
            if n<0 or f.tell()+n>length: raise ValueError("invalid RGSS archive bounds")
            data=f.read(n)
            if len(data)!=n: raise ValueError("truncated RGSS archive")
            return data
        def u32(): return int.from_bytes(take(4),"little")
        def payload(offset,size,key):
            if size>MAX_ARCHIVE: raise ValueError("RGSS scripts size limit")
            if offset<8 or offset+size>length: raise ValueError("invalid RGSS member offset")
            f.seek(offset)
            data=bytearray(take(size))
            for i in range(0,len(data),4):
                n=min(4,len(data)-i)
                data[i:i+n]=(int.from_bytes(data[i:i+n],"little")^(key&((1<<(8*n))-1))).to_bytes(n,"little")
                key=advance(key)
            return bytes(data)
        header=take(8)
        if header[:7]!=b"RGSSAD\x00": raise ValueError("invalid RGSS archive header")
        if header[7]==1:
            key=0xdeadcafe
            for _ in range(20000):
                if f.tell()==length: return None
                n=u32()^key; key=advance(key)
                if not 0<n<=4096: raise ValueError("invalid RGSS entry name size")
                name=bytearray(take(n))
                for i in range(n): name[i]^=key&255; key=advance(key)
                size=u32()^key; key=advance(key)
                offset=f.tell()
                if offset+size>length: raise ValueError("invalid RGSS entry size")
                if matches(name): return payload(offset,size,key)
                f.seek(offset+size)
        elif header[7]==3:
            base=(u32()*9+3)&mask
            for _ in range(20000):
                offset=u32()^base
                if offset==0: return None
                size=u32()^base; key=u32()^base; n=u32()^base
                if not 0<n<=4096 or offset+size>length: raise ValueError("invalid RGSS3 entry bounds")
                name=bytearray(take(n))
                for i in range(n): name[i]^=(base>>(8*(i%4)))&255
                if matches(name): return payload(offset,size,key)
        else: raise ValueError("unsupported RGSS archive version")
        raise ValueError("RGSS member count limit")

def external_scripts(root):
    queue=[(root/"Scripts",0)]
    visited=0; yielded=0
    while queue and visited<4096 and yielded<256:
        folder,depth=queue.pop(0)
        if folder.is_symlink() or not folder.is_dir(): continue
        for p in sorted(itertools.islice(folder.iterdir(),4096-visited),key=lambda p:p.name):
            visited+=1
            if p.is_symlink(): continue
            if p.is_dir() and depth<5: queue.append((p,depth+1))
            elif p.is_file() and p.suffix.lower()==".rb":
                yield p
                yielded+=1
                if yielded>=256: return

def inspect(root, cfg):
    sources, clues, score = [], [], dict.fromkeys(MODES, 0)
    digest = hashlib.sha256()
    def add(mode, weight, clue):
        score[mode] += weight
        if clue not in clues: clues.append(clue)
    def collect(path, data):
        digest.update(str(path.relative_to(root)).encode("utf-8", "surrogateescape"))
        digest.update(b"\0" + hashlib.sha256(data).digest())
    try:
        ini = project_file(root, "Game.ini")
        raw = bounded_read(ini, 128*1024) if ini else b""
        if ini: collect(ini, raw)
        if re.search(rb"(?i)RGSS3\d*",raw): add("ruby19",90,"Game.ini RGSS3")
        elif re.search(rb"(?i)RGSS[12]\d*",raw): add("ruby18",90,"Game.ini RGSS1/2")
        packed=[]
        for p in sorted(itertools.islice(root.iterdir(),4096),key=lambda p:p.name):
            if p.is_symlink() or not p.is_file(): continue
            n = p.name.lower()
            for mode, pattern in (("ruby18", r"ruby(?:187|18\.|1\.8)"), ("ruby19", r"ruby(?:19[123]|19\.|1\.9)"), ("ruby31", r"ruby(?:31[0-9]|31\.|3\.1)"), ("ruby32", r"ruby(?:32[0-9]|32\.|3\.2)")):
                if re.search(pattern, n): add(mode, 150, p.name)
            if re.search(r"rgss3\d*.*\.dll", n): add("ruby19", 90, "RGSS3 DLL")
            elif re.search(r"rgss[12]\d*.*\.dll", n): add("ruby18", 90, "RGSS1/2 DLL")
            if p.suffix.lower() in (".rgssad",".rgss2a",".rgss3a"): packed.append(p)
            digest.update(os.fsencode(p.name)+b"\0")
        paths = []
        match = re.search(rb"(?im)^\s*Scripts\s*=\s*([^\r\n]+)", raw)
        if match:
            paths.extend(decoded_paths(match[1].strip()))
        paths += ["Data/Scripts.rxdata", "Data/Scripts.rvdata", "Data/Scripts.rvdata2"]
        archive = next((p for n in paths if (p := project_file(root,n))), None)
        if archive:
            add("ruby19" if archive.suffix.lower()==".rvdata2" else "ruby18", 45, archive.suffix)
            raw = bounded_read(archive, MAX_ARCHIVE)
            collect(archive, raw)
            sources.extend(script_archive_sections(raw))
        else:
            for p in packed[:8]:
                try:
                    raw=read_rgss_scripts(p,paths)
                    if raw is None: continue
                    add("ruby19" if p.suffix.lower()==".rgss3a" else "ruby18",45,p.suffix)
                    collect(p,raw)
                    sources.extend(script_archive_sections(raw))
                    log("Read script member from "+p.name)
                    break
                except (OSError,ValueError,zlib.error) as e:
                    log("Archive probe unavailable "+p.name+": "+str(e))
            if not sources: log("No readable Scripts archive; using available signatures")
        for p in external_scripts(root):
            if sum(map(len,sources)) >= MAX_SOURCE: break
            data=bounded_read(p,min(256*1024, MAX_SOURCE-sum(map(len,sources))))
            collect(p,data); sources.append(data)
    except (OSError,ValueError,LookupError,zlib.error) as e:
        log("Preflight incomplete (not a compatibility rejection): "+str(e))
        # Do not cache an incomplete scan as a successful syntax check.
        sources=[]
        digest.update(b"incomplete")
    for src in sources:
        if re.search(rb"&\.[A-Za-z_]|\bdef\s+[^\n(]+\([^\n)]*\*\*|\b__dir__\b",src):
            add("ruby31", 60, "modern syntax"); add("ruby32", 60, "modern syntax")
        if re.search(rb"require_relative|\.force_encoding|\bEncoding::",src):
            add("ruby19", 12, "encoding API")
        if re.search(rb"\.untaint\b|\bWin32API\b",src):
            add("ruby18", 4, "legacy API"); add("ruby19", 4, "legacy API")
    log("Preflight sections=%d clues=%s scores=%s" % (len(sources),clues[:20],score))
    return sources, score, digest.hexdigest()

def installed(root):
    result={}
    for mode in MODES:
        folder=root/"runtimes"/mode
        exe=folder/"mkxp-z"
        if mode=="ruby32" and not exe.is_file():
            folder=root; exe=folder/"mkxp-z"
        if exe.is_file() and os.access(exe,os.X_OK):
            result[mode]=(folder,exe)
    return result

def runtime_env(base, folder, mode):
    env=base.copy()
    env.pop("RUBYOPT",None); env.pop("RUBYLIB",None)
    root=Path(base["BANANA_RPG_RUNTIME"])/"mkxp"
    env["LD_LIBRARY_PATH"]=":".join(str(p) for p in (folder/"lib",root/"lib",root.parent/"common/lib"))
    paths=[folder/"ruby/stdlib",folder/"ruby/extensions"]
    env["MKXP_PORTABLE_RUBY_LOADPATH"]=":".join(str(p) for p in paths if p.is_dir())
    env["BANANA_RPG_RESOURCE_PRELOAD"]=str(root/"banana-filenames.rb" if mode=="ruby32" else folder/"banana-filenames.rb")
    env["BANANA_MKXP_ACTIVE_RUNTIME"]=mode
    env["BANANA_MKXP_WIN32_PRELOAD"]=str(root/"banana-win32.rb")
    game=Path(base["BANANA_SA_ENTRY"]).parent.name.casefold()
    env["BANANA_MKXP_SENIA"]="1" if ("eternal senia" in game or "\uc774\ud130\ub110 \uc138\ub2c8\uc544" in game) else "0"
    return env

def probe(sources, folder, env, deadline, cancelled=lambda:False):
    cli=folder/"ruby/bin/ruby"
    if not sources or not cli.is_file(): return "unknown"
    env=env.copy()
    env.pop("LD_PRELOAD",None)
    env["RUBYLIB"]=env.get("MKXP_PORTABLE_RUBY_LOADPATH","")
    with tempfile.TemporaryDirectory(prefix="mkxp-probe-",dir=env["BANANA_RPG_CONFIG"]) as td:
        for i,src in enumerate(sources):
            if cancelled(): return "cancelled"
            remaining=deadline-time.monotonic()
            if remaining <= 0: return "timeout"
            path=Path(td)/"section.rb"
            path.write_bytes(src)
            try:
                args=[str(cli)]
                if env["BANANA_MKXP_ACTIVE_RUNTIME"]!="ruby18": args.append("--disable-gems")
                if env["BANANA_MKXP_ACTIVE_RUNTIME"]=="ruby19": args.append("-Ku")
                r=subprocess.run(args+["-c",str(path)],env=env,cwd=td,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=min(5,remaining))
            except (OSError,subprocess.TimeoutExpired) as e:
                log("Probe unavailable: "+str(e)); return "unknown"
            if r.returncode:
                log("Probe section=%d status=%d detail=%s"%(i,r.returncode,r.stderr[:1500].decode("utf-8","replace").strip()))
                return "fail" if r.returncode==1 else "unknown"
    return "pass"

def save_json(path, value):
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",prefix=path.name+".",suffix=".tmp",dir=path.parent,delete=False) as stream:
            tmp=Path(stream.name)
            json.dump(value,stream,ensure_ascii=True)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)
    except (OSError,ValueError,TypeError) as e: log("Journal/cache write failed: "+str(e))
    finally:
        if tmp is not None:
            try: tmp.unlink(missing_ok=True)
            except OSError: pass

def main():
    base=os.environ.copy()
    root=Path(base["BANANA_RPG_RUNTIME"])/"mkxp"
    cfg=Path(base["BANANA_RPG_CONFIG"])
    game=Path(base["BANANA_SA_ENTRY"]).parent
    mode=base.get("BANANA_MKXP_MODE","auto") or "auto"
    cfg.mkdir(parents=True,exist_ok=True)
    runtimes=installed(root)
    # Native reset re-execs run-rpg in the original child. Do not nest
    # supervisors or retry the same runtime indefinitely.
    if base.get("BANANA_MKXP_SUPERVISED")=="1" and base.get("BANANA_SA_RESTARTING")=="1":
        key=base.get("BANANA_MKXP_ACTIVE_RUNTIME")
        if key not in runtimes:
            log("Restart runtime missing: "+str(key)); return 127
        folder,exe=runtimes[key]
        log("Restart same runtime="+key)
        os.execve(str(exe),[str(exe)],runtime_env(base,folder,key))
    log("Configured runtime=%s installed=%s"%(mode,list(runtimes)))
    journal={"started":time.strftime("%Y-%m-%d %H:%M:%S"),"game":str(game),"mode":mode,"log":base.get("BANANA_MKXP_LOG_PATH",""),"attempts":[]}
    journalpath=cfg/"ruby-last-attempts.json"
    def event(outcome):
        journal["outcome"]=outcome
        save_json(journalpath,journal)
        status=base.get("BANANA_MKXP_STATUS_FILE")
        if status:
            attempt=journal["attempts"][-1] if journal["attempts"] else {}
            phase={"preflight":"preflight","launching":"preflight","runtime-failed":"retry","restart":"restart","all-failed":"failed","no-runtime":"failed","manual-runtime-missing":"failed"}.get(outcome,"running" if attempt.get("ready") else "starting")
            name={"ruby18":"Ruby 1.8.7","ruby19":"Ruby 1.9.3","ruby31":"Ruby 3.1.6","ruby32":"Ruby 3.2.3"}.get(attempt.get("runtime"),"")
            path=Path(status); tmp=path.with_name(path.name+".tmp")
            try:
                tmp.write_text(phase+"\n"+name+"\n",encoding="utf-8")
                tmp.replace(path)
            except OSError as e: log("Status marker write failed: "+str(e))
    if not runtimes:
        log("No MKXP executable installed"); event("no-runtime"); return 127
    if mode!="auto" and mode not in runtimes:
        log("Requested runtime missing: "+mode); event("manual-runtime-missing"); return 127
    child=None
    interrupted=False
    quitfile=base.get("BANANA_MKXP_QUIT_FILE")
    def cancelled():
        return interrupted or bool(quitfile and Path(quitfile).is_file())
    def stop(sig,frame):
        nonlocal interrupted
        interrupted=True
        if child and child.poll() is None:
            try: child.send_signal(sig)
            except ProcessLookupError: pass
    for sig in STOP_SIGNALS: signal.signal(sig,stop)
    event("preflight")
    sources,score,fingerprint=[],dict.fromkeys(MODES,0),"unavailable"
    if mode=="auto":
        try:
            sources,score,fingerprint=inspect(game,cfg)
        except Exception as e:
            import traceback
            log("Optional preflight failed; continuing with installed runtimes: "+repr(e))
            traceback.print_exc()
            journal["preflight_error"]=repr(e)
    else:
        log("Manual runtime selected; skipping optional script inspection")
    identity={}
    for key,(folder,exe) in runtimes.items():
        st=exe.stat()
        identity[key]=[st.st_size,st.st_mtime_ns]
    cachepath=cfg/"ruby-auto.json"
    signature={"rev":REV,"fingerprint":fingerprint,"engines":identity}
    try: cache=json.loads(cachepath.read_text(encoding="utf-8"))
    except (OSError,ValueError): cache={}
    if not isinstance(cache,dict) or not isinstance(cache.get("probes",{}),dict): cache={}
    valid=cache.get("signature")==signature and bool(sources)
    if mode=="auto":
        results=dict(cache.get("probes",{})) if valid else {}
        if valid: log("Using cached syntax results: "+str(results))
        for key,(folder,exe) in runtimes.items():
            if cancelled(): log("User exit during preflight"); event("user-exit"); return 0
            if results.get(key) not in ("pass","fail"):
                try:
                    results[key]=probe(sources,folder,runtime_env(base,folder,key),time.monotonic()+30,cancelled)
                except Exception as e:
                    log("Optional syntax probe failed for "+key+": "+repr(e))
                    results[key]="unknown"
            log("Syntax probe %s=%s"%(key,results[key]))
        last=cache.get("last_success") if valid else None
        order=sorted(runtimes,key=lambda k:(results.get(k)=="fail",k!=last,results.get(k)!="pass",-score[k],k!="ruby32"))
        save_json(cachepath,{"signature":signature,"probes":results,"last_success":last})
    else: order=[mode]; results={}
    log("Launch order="+",".join(order))
    journal.update({"probe":results,"order":order,"fingerprint":fingerprint})
    event("launching")
    lease=base.get("BANANA_DRM_LEASE_FD","")
    fds=()
    if lease.isdigit():
        try: os.fstat(int(lease)); fds=(int(lease),)
        except OSError: log("Display lease descriptor is invalid"); event("invalid-display-lease"); return 4
    marker_dir=tempfile.TemporaryDirectory(prefix="mkxp-session-",dir=cfg)
    try: timeout=max(1,min(300,int(base.get("BANANA_MKXP_STARTUP_TIMEOUT","90"))))
    except ValueError: timeout=90
    for i,key in enumerate(order,1):
        if cancelled(): log("User exit before next attempt"); event("user-exit"); return 0
        folder,exe=runtimes[key]
        env=runtime_env(base,folder,key)
        # On in-engine reset, run-rpg re-executes the same child directly.
        env["BANANA_MKXP_SUPERVISED"]="1"
        ready=Path(marker_dir.name)/("%d.ready"%i)
        restart=Path(marker_dir.name)/("%d.restart"%i)
        env["BANANA_MKXP_READY_FILE"]=str(ready)
        env["BANANA_MKXP_RESTART_FILE"]=str(restart)
        monitor_ready=Path(env["BANANA_RPG_RESOURCE_PRELOAD"]).is_file()
        log("Attempt %d/%d %s binary=%s"%(i,len(order),key,exe))
        started=time.monotonic()
        attempt={"runtime":key,"started":time.strftime("%Y-%m-%d %H:%M:%S"),"binary":str(exe),"ready":False}
        journal["attempts"].append(attempt); event("running")
        was_ready=False; timed_out=False; cancelled_at=None; active=0.0; last_tick=started
        try:
            child=subprocess.Popen([str(exe)],env=env,cwd=game,pass_fds=fds)
            while child.poll() is None:
                now=time.monotonic()
                pause_path=base.get("BANANA_SA_PAUSE_FILE")
                if not (pause_path and Path(pause_path).is_file()):
                    active+=min(now-last_tick,1.0)
                last_tick=now
                if not was_ready and ready.is_file():
                    was_ready=True; attempt["ready"]=True
                    log("First Graphics.update completed for "+key)
                    event("running")
                    if mode=="auto": save_json(cachepath,{"signature":signature,"probes":results,"last_success":key})
                if cancelled():
                    if cancelled_at is None:
                        cancelled_at=now; log("User exit requested; waiting for clean engine shutdown")
                    if now-cancelled_at>=3:
                        child.terminate()
                        try: child.wait(timeout=3)
                        except subprocess.TimeoutExpired: child.kill(); child.wait()
                        break
                elif monitor_ready and not was_ready and active>=timeout:
                    timed_out=True
                    log("Startup timeout: no completed Graphics.update within %ds"%timeout)
                    child.terminate()
                    try: child.wait(timeout=3)
                    except subprocess.TimeoutExpired: child.kill(); child.wait()
                    break
                time.sleep(0.1)
            rc=child.wait()
            if not was_ready and ready.is_file():
                was_ready=True; attempt["ready"]=True
        except OSError as e:
            log("Launch error "+repr(e)); attempt["launch_error"]=str(e); rc=127
            if child and child.poll() is None: child.kill(); child.wait()
        child=None
        log("Attempt result runtime=%s exit=%d signal=%s duration=%.2fs"%(key,rc,-rc if rc<0 else "-",time.monotonic()-started))
        attempt.update({"exit_code":rc,"signal":-rc if rc<0 else None,"startup_timeout":timed_out,"duration_seconds":round(time.monotonic()-started,2)})
        if cancelled() or (not timed_out and rc in tuple(-s for s in STOP_SIGNALS)):
            log("Exit requested; no fallback"); event("user-exit"); return 0
        if rc==86 and restart.is_file():
            launcher=base.get("BANANA_SA_LAUNCHER","")
            entry=base.get("BANANA_SA_ENTRY","")
            log("Explicit restart; reloading game settings")
            event("restart")
            if not os.path.isabs(launcher) or not os.path.isabs(entry):
                log("Restart launcher or entry invalid"); event("restart-error"); return 1
            marker_dir.cleanup()
            for fd in fds: os.set_inheritable(fd,True)
            base["BANANA_SA_RESTARTING"]="1"
            base.pop("BANANA_MKXP_SUPERVISED",None)
            os.execve(launcher,[launcher,"mkxp",entry],base)
        if rc==0 and not timed_out:
            if mode=="auto" and was_ready: save_json(cachepath,{"signature":signature,"probes":results,"last_success":key})
            log("Normal exit"); event("normal-exit"); return 0
        event("runtime-failed")
        if mode=="auto":
            save_json(cachepath,{"signature":signature,"probes":results,"last_success":None})
            log("Runtime failed; moving to next installed candidate")
    log("All selected runtimes failed; returning to launcher")
    event("all-failed")
    return 1

if __name__=="__main__":
    try: sys.exit(main())
    except Exception:
        import traceback
        detail=traceback.format_exc()
        traceback.print_exc()
        try:
            path=Path(os.environ["BANANA_RPG_CONFIG"])/"ruby-last-attempts.json"
            try: journal=json.loads(path.read_text(encoding="utf-8"))
            except (OSError,ValueError): journal={}
            if not isinstance(journal,dict): journal={}
            journal.update({"outcome":"supervisor-error","traceback":detail})
            save_json(path,journal)
        except Exception: traceback.print_exc()
        sys.exit(1)
