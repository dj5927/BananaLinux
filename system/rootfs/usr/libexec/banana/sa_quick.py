#!/usr/bin/python3
"""Single-flight native control IPC with explicit completion acknowledgements."""
import os
import tempfile
import time
from pathlib import Path

class QuickBridge:
    RESULTS={"ok","warning","failed","empty","blocked","fast_on","fast_off"}
    def __init__(self, run_dir, report, log):
        self.root=Path(tempfile.mkdtemp(prefix="sa-quick-",dir=run_dir))
        self.report=report
        self.log=log
        self.req=self.root/"request"
        self.res=self.root/"result"
        self.seq=0
        self.pending=None
        self.timed_out=False
    def env(self):
        return {"BANANA_QUICK_REQUEST":str(self.req),"BANANA_QUICK_RESULT":str(self.res)}
    def reset(self):
        for f in self.root.iterdir(): f.unlink(missing_ok=True)
        self.pending=None
        self.timed_out=False
    def close(self):
        try:
            self.reset()
            self.root.rmdir()
        except OSError as e:
            self.log("quick cleanup: "+str(e))
    def command(self, line):
        parts=line.split()
        if not parts or parts[0] not in (b"SAVE_STATE",b"LOAD_STATE",b"FAST_FORWARD"):
            return False
        op={b"SAVE_STATE":"save",b"LOAD_STATE":"load",b"FAST_FORWARD":"fast"}[parts[0]]
        try:
            slot=int(parts[1]) if len(parts)==2 else 1
        except ValueError:
            return True
        if len(parts)>2 or not 1<=slot<=5:
            self.report("Invalid state slot")
            return True
        if self.pending is not None:
            self.report("State request pending")
            return True
        self.seq+=1
        self.res.unlink(missing_ok=True)
        tmp=self.root/"request.new"
        tmp.write_text(f"{self.seq} {op} {slot}\n",encoding="ascii")
        os.replace(tmp,self.req)
        self.pending=(self.seq,op,slot,time.monotonic())
        self.timed_out=False
        self.report("Saving state..." if op=="save" else "Loading state..." if op=="load" else "Changing speed...")
        self.log(f"quick {op} slot={slot} id={self.seq}")
        return True
    def poll(self):
        if self.pending is None:
            return
        seq,op,slot,started=self.pending
        if self.res.is_file():
            try:
                fields=self.res.read_text(encoding="ascii").split()
                self.res.unlink(missing_ok=True)
                if len(fields)==2 and fields[0]==str(seq) and fields[1] in self.RESULTS:
                    result=fields[1]
                    self.pending=None
                    self.timed_out=False
                    message={
                        "ok":"State saved" if op=="save" else "State loaded",
                        "warning":"State warning","failed":"State operation failed",
                        "empty":"State slot empty","blocked":"Unavailable during this game",
                        "fast_on":"Fast forward on","fast_off":"Fast forward off",
                    }[result]
                    self.report(message)
                    self.log(f"quick result {seq} {op} {slot} {result}")
                    return
            except (OSError,UnicodeError) as e:
                self.log(f"quick result read: {e}")
        if not self.timed_out and time.monotonic()-started>45:
            self.timed_out=True
            # Never retry or replace an operation whose result is unknown.
            # If the engine has not consumed the command, withdraw it.
            try:
                self.req.unlink()
            except FileNotFoundError:
                pass
            else:
                self.pending=None
            self.report("State request timed out")
            self.log(f"quick timeout {seq} {op}; no retry")
