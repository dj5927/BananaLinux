"""Host tests for archive parsing and process supervision, no real games needed."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import zlib

ROOT=Path(__file__).resolve().parents[2]
S=ROOT/"system/rootfs/usr/libexec/banana/mkxp-supervisor.py"
spec=importlib.util.spec_from_file_location("supervisor",S)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def num(n):
    if n==0: return b"\x00"
    if 0<n<123: return bytes([n+5])
    b=n.to_bytes((n.bit_length()+7)//8,"little")
    return bytes([len(b)])+b
def string(b): return b'"'+num(len(b))+b
def archive(code):
    return b"\x04\x08["+num(1)+b"["+num(3)+b"i"+num(0)+string(b"Main")+string(zlib.compress(code))
def word(n): return n.to_bytes(4,"little")
def keynext(k): return (k*7+3)&0xffffffff
def enc(data,k):
    out=bytearray()
    for i in range(0,len(data),4):
        chunk=data[i:i+4]
        out+=(int.from_bytes(chunk,"little")^(k&((1<<(8*len(chunk)))-1))).to_bytes(len(chunk),"little")
        k=keynext(k)
    return bytes(out)
def rgss1(entries):
    out=bytearray(b"RGSSAD\0\1"); key=0xdeadcafe
    for name,data in entries:
        out+=word(len(name)^key); key=keynext(key)
        for c in name: out.append(c^(key&255)); key=keynext(key)
        out+=word(len(data)^key); key=keynext(key)
        out+=enc(data,key)
    return bytes(out)
def rgss3(name,data):
    seed=0x12345678; base=(seed*9+3)&0xffffffff; key=0x87654321
    off=12+16+len(name)+4
    return b"RGSSAD\0\3"+word(seed)+b"".join(word(v^base) for v in (off,len(data),key,len(name)))+bytes(c^((base>>(8*(i%4)))&255) for i,c in enumerate(name))+word(base)+enc(data,key)

REAL_POPEN=subprocess.Popen
def main():
    temp=ROOT.parent/"host-test-temp"
    temp.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp,prefix="qa-") as td:
        d=Path(td); game=d/"한글 게임"; game.mkdir(); cfg=d/"cfg"; cfg.mkdir()
        code=b"Graphics.update\nobj&.foo\n"
        raw=archive(code)
        assert m.script_archive_sections(raw)==[code]
        # Data-only parser must refuse executable Marshal object tags.
        for bad in (b"\x04\x08o",b"\x04\x08[\x7f",b"\x04\x07"):
            try: m.script_archive_sections(bad)
            except ValueError: pass
            else: raise AssertionError("accepted invalid marshal")
        (game/"Data").mkdir()
        ini=game/"Game.ini"; ini.write_bytes(b"[Game]\nLibrary=RGSS301.dll\nScripts=Data/Scripts.rvdata2\n")
        scripts=game/"Data/Scripts.rvdata2"; scripts.write_bytes(raw)
        sources,score,fp=m.inspect(game,cfg)
        assert sources==[code] and score["ruby19"]>0 and score["ruby31"]>0
        scripts.write_bytes(archive(b"Graphics.update\n"))
        assert m.inspect(game,cfg)[2]!=fp
        scripts.unlink()
        for extension,packed in (("rgssad",rgss1([(b"Audio/BGM/x.ogg",b"skip"),(b"Data\\Scripts.rvdata2",raw)])),("rgss2a",rgss1([(b"Data/Scripts.rvdata2",raw)])),("rgss3a",rgss3(b"Data/Scripts.rvdata2",raw))):
            p=game/("Game."+extension); p.write_bytes(packed)
            assert m.read_rgss_scripts(p,["Data/Scripts.rvdata2"])==raw
            assert m.inspect(game,cfg)[0]==[code]
            p.unlink()
        p=game/"Game.rgss3a"; p.write_bytes(b"RGSSAD\0\3"+word(0)+word(1))
        assert m.inspect(game,cfg)[0]==[]
        p.unlink(); scripts.write_bytes(archive(b"Graphics.update\n"))
        print("PASS plain and encrypted RGSS archives, bounds, no evaluation, cache hash invalidation")
        runtime=d/"runtime"; root=runtime/"mkxp"; root.mkdir(parents=True)
        paths={}
        for mode in m.MODES:
            folder=root if mode=="ruby32" else root/"runtimes"/mode
            folder.mkdir(parents=True,exist_ok=True)
            exe=folder/"mkxp-z"; exe.write_text("fixture",encoding="ascii")
            (folder/"banana-filenames.rb").write_text("# ready fixture",encoding="ascii")
            paths[mode]=(folder,exe)
        quitfile=d/"user-quit"
        base={"BANANA_RPG_RUNTIME":str(runtime),"BANANA_RPG_CONFIG":str(cfg),"BANANA_SA_ENTRY":str(ini),"BANANA_MKXP_MODE":"auto","BANANA_MKXP_STARTUP_TIMEOUT":"1","BANANA_MKXP_QUIT_FILE":str(quitfile),"BANANA_MKXP_LOG_PATH":str(game/"banana-mkxp.log")}
        behavior={}; calls=[]; probes=[]
        def fake_probe(sources,folder,env,deadline,cancelled):
            probes.append(env["BANANA_MKXP_ACTIVE_RUNTIME"]); return "pass"
        def fake_launch(args,**kwargs):
            key=kwargs["env"]["BANANA_MKXP_ACTIVE_RUNTIME"]; calls.append(key)
            action=behavior.get(key,"fail")
            code={
                "fail":"import sys; sys.exit(23)",
                "success":"import os,pathlib; pathlib.Path(os.environ['BANANA_MKXP_READY_FILE']).write_text('frame')",
                "latefail":"import os,pathlib,time,sys; pathlib.Path(os.environ['BANANA_MKXP_READY_FILE']).write_text('frame'); time.sleep(.3); sys.exit(9)",
                "hang":"import time; time.sleep(20)",
                "quit":"import os,pathlib; pathlib.Path(os.environ['BANANA_MKXP_QUIT_FILE']).write_text('quit')",
            }[action]
            return REAL_POPEN([sys.executable,"-B","-c",code],**kwargs)
        def execute(mode="auto",reset=True):
            calls.clear(); probes.clear()
            if reset: (cfg/"ruby-auto.json").unlink(missing_ok=True)
            quitfile.unlink(missing_ok=True)
            base["BANANA_MKXP_MODE"]=mode
            old={sig:signal.getsignal(sig) for sig in m.STOP_SIGNALS}
            try:
                with patch.dict(os.environ,base,clear=False),patch.object(m,"installed",return_value=paths),patch.object(m,"probe",side_effect=fake_probe),patch.object(m.subprocess,"Popen",side_effect=fake_launch),contextlib.redirect_stdout(io.StringIO()) as stream:
                    rc=m.main()
            finally:
                for sig,handler in old.items(): signal.signal(sig,handler)
            journal=json.loads((cfg/"ruby-last-attempts.json").read_text(encoding="utf-8"))
            return rc,journal,stream.getvalue()
        behavior.update(ruby19="latefail",ruby18="success",ruby31="success",ruby32="success")
        rc,j,out=execute()
        assert rc==0 and len(calls)==2 and calls[0]=="ruby19", (calls,j)
        assert j["attempts"][0]["ready"] and j["attempts"][0]["exit_code"]==9
        assert j["outcome"]=="normal-exit" and "Runtime failed" in out
        winner=calls[-1]
        rc,j,out=execute(reset=False)
        assert rc==0 and calls==[winner] and not probes
        print("PASS late crash fallback, per-attempt error journal, successful runtime cache")
        behavior.clear(); rc,j,out=execute()
        assert rc==1 and len(set(calls))==4 and len(calls)==4 and j["outcome"]=="all-failed"
        assert all(x["exit_code"]==23 for x in j["attempts"])
        rc,j,out=execute("ruby19")
        assert rc==1 and calls==["ruby19"] and not probes
        print("PASS four failures bounded, strict manual runtime, no automatic manual retry")
        behavior.update(ruby19="hang",ruby18="success",ruby31="success",ruby32="success")
        rc,j,out=execute()
        assert rc==0 and len(calls)==2 and j["attempts"][0]["startup_timeout"]
        print("PASS startup timeout, terminate/reap before fallback")
        behavior["ruby19"]="quit"; rc,j,out=execute()
        assert rc==0 and calls==["ruby19"] and j["outcome"]=="user-exit"
        print("PASS explicit quit suppresses fallback")
        print("ALL MKXP SUPERVISOR HOST TESTS PASS")
if __name__=="__main__": main()
