#!/usr/bin/env python3
"""Host process-group and FIFO tests; synthetic port, no commercial game."""
import os,sys,time,tempfile,subprocess,hashlib,signal
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
sup=repo/"system/rootfs/usr/libexec/banana/port-supervisor.py"
def wait_for(pred, timeout=6):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if pred(): return
        time.sleep(.03)
    raise AssertionError("timeout")
with tempfile.TemporaryDirectory(prefix="banana-port-qa-") as td:
    t=Path(td); data=t/"data"; pause=t/"pause"; fifo=t/"cmd"; os.mkfifo(fifo)
    fd=os.open(fifo,os.O_RDWR|os.O_NONBLOCK)
    script=t/"test port.sh"
    script.write_text('''#!/bin/bash
echo "start $$"
echo $$ >> "$QA/pids"
( trap "" TERM; while :; do echo tick >> "$QA/ticks"; sleep .04; done ) &
echo $! >> "$QA/pids"
wait
''')
    env=os.environ|{"BANANA_PORT_DATA":str(data),"BANANA_RA_CMD":str(fifo),"BANANA_SA_PAUSE_FILE":str(pause),"BANANA_GAME_KEY":"ports/QA","QA":str(t)}
    log=data/"banana/logs/ports"/(hashlib.sha256(b"ports/QA").hexdigest()+".log")
    def log_has(word): return log.exists() and word in log.read_text(errors="replace")
    def pids(): return [int(x) for x in (t/"pids").read_text().split()] if (t/"pids").exists() else []
    def alive(pid):
        try: return Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()[0]!="Z"
        except FileNotFoundError: return False
    p=subprocess.Popen([sys.executable,str(sup),str(script)],env=env)
    try:
        wait_for(lambda:len(pids())>=2 and (t/"ticks").exists())
        first=pids()[:2]; pause.touch(); wait_for(lambda:log_has("[PORT] paused"))
        time.sleep(.15); n=(t/"ticks").stat().st_size
        time.sleep(.25); assert (t/"ticks").stat().st_size==n
        pause.unlink(); wait_for(lambda:log_has("[PORT] resumed"))
        wait_for(lambda:(t/"ticks").stat().st_size>n)
        os.write(fd,b"RESET\n"); wait_for(lambda:len(pids())>=4,10)
        assert not any(alive(i) for i in first)
        pause.touch()
        wait_for(lambda:log.read_text().count("[PORT] paused")==2)
        os.write(fd,b"QUIT\n")
        assert p.wait(timeout=8)==0
        wait_for(lambda:not any(alive(i) for i in pids()))
        assert log_has("[PORT] restarting") and log_has("request=quit") and log_has("SIGKILL")
        assert (data/"banana/logs/ports/last-log-path.txt").read_text().strip()==str(log)
        pause.unlink()
        script.write_text("#!/bin/bash\necho natural-error\nexit 7\n")
        assert subprocess.run([sys.executable,str(sup),str(script)],env=env,timeout=8).returncode==7
        assert log_has("exit=7 request=natural") and log.with_suffix(".previous.log").exists()
        script.write_text("#!/bin/bash\necho $$ >> \"$QA/pids\"\nwhile :; do sleep .1; done\n")
        p=subprocess.Popen([sys.executable,str(sup),str(script)],env=env)
        wait_for(lambda:len(pids())>=5)
        p.send_signal(signal.SIGTERM)
        assert p.wait(timeout=8)==0
        wait_for(lambda:not any(alive(i) for i in pids()))
        print("PASS port pause/resume, restart, quit while stopped, TERM/KILL child-group cleanup, natural failure, logs")
    finally:
        if p.poll() is None:
            p.terminate()
            p.wait(timeout=10)
        os.close(fd)
