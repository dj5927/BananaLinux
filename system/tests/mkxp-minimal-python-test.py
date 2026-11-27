"""Run using the actual firmware Python, not host CPython."""
import codecs
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import zlib
import sys

spec=importlib.util.spec_from_file_location("supervisor",sys.argv[1])
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
def small(n): return b"\0" if n==0 else bytes([n+5])
def string(b): return b'"'+small(len(b))+b
code=b"Graphics.update\n"
archive=b"\x04\x08[\x06[\x08i\x00"+string(b"Main")+string(zlib.compress(code))
for enc in ("cp949","cp932"):
    try: codecs.lookup(enc); print("Python codec present",enc)
    except LookupError: print("Reproduced missing codec",enc)
assert list(m.decoded_paths(b"Data/Scripts.rvdata2"))==["Data/Scripts.rvdata2"]
assert "\ud55c\uae00" in list(m.decoded_paths(bytes.fromhex("c7d1b1db")))
assert "\u65e5\u672c" in list(m.decoded_paths(bytes.fromhex("93fa967b")))
with tempfile.TemporaryDirectory(prefix="v12-target-qa-") as td:
    d=Path(td); game=d/"999 victory"; game.mkdir(); cfg=d/"cfg"; cfg.mkdir()
    (game/"Data").mkdir()
    script=game/"Data/Scripts.rvdata2"; script.write_bytes(archive)
    ini=game/"Game.ini"; ini.write_bytes(b"[Game]\nLibrary=RGSS301.dll\nScripts=Data/Scripts.rvdata2\n")
    assert m.inspect(game,cfg)[0]==[code]
    script.unlink()
    for name,encoded in (("\ud55c\uae00",bytes.fromhex("c7d1b1db")),("\u65e5\u672c",bytes.fromhex("93fa967b"))):
        path=game/"Data"/(name+".rvdata2"); path.write_bytes(archive)
        ini.write_bytes(b"[Game]\nLibrary=RGSS301.dll\nScripts=Data/"+encoded+b".rvdata2\n")
        assert m.inspect(game,cfg)[0]==[code]
        path.unlink()
    print("PASS ASCII, CP949 and CP932 archive paths on firmware Python")
    # Simulate an unexpected inspection exception and probe exception; launch
    # the actual supervisor's subprocess state machine with harmless test executables.
    script.write_bytes(archive)
    ini.write_bytes(b"[Game]\nLibrary=RGSS301.dll\nScripts=Data/Scripts.rvdata2\n")
    runtime=d/"runtime"; mk=runtime/"mkxp"
    for mode in m.MODES:
        exe=mk/"runtimes"/mode/"mkxp-z"; exe.parent.mkdir(parents=True)
        exe.write_text("#!/bin/sh\nexit "+("7" if mode=="ruby32" else "0")+"\n")
        exe.chmod(0o755)
    os.environ.update(BANANA_RPG_RUNTIME=str(runtime),BANANA_RPG_CONFIG=str(cfg),BANANA_SA_ENTRY=str(ini),BANANA_MKXP_MODE="auto")
    orig=m.inspect
    def fail(*args): raise LookupError("simulated optional codec failure")
    m.inspect=fail
    m.probe=fail
    assert m.main()==0
    journal=json.loads((cfg/"ruby-last-attempts.json").read_text())
    assert journal["outcome"]=="normal-exit" and "preflight_error" in journal
    assert len(journal["attempts"])==2 and journal["attempts"][0]["exit_code"]==7
    os.environ["BANANA_MKXP_MODE"]="ruby19"
    assert m.main()==0
    journal=json.loads((cfg/"ruby-last-attempts.json").read_text())
    assert journal["order"]==["ruby19"] and "preflight_error" not in journal
    print("PASS optional preflight/probe failure fallback and manual bypass")
print("TARGET MINIMAL PYTHON PASS")
