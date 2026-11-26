#!/usr/bin/env python3
"""SFTP and Dropbear end-to-end regression. Run through ssh-sftp-test.sh."""
from pathlib import Path
import crypt
import os
import secrets
import subprocess
import sys
import time
import paramiko

root, work = map(Path, sys.argv[1:3])
data = root / "data/banana"
tool = "/usr/libexec/banana/ssh"
hashfile = data / "ssh/password.hash"
settings = data / "settings.conf"
def run(*args, text=None, check=True):
    return subprocess.run(["chroot", str(root), tool, *args], input=text,
                          text=True, check=check, capture_output=True)
def connect(password=None, key=None, user="root"):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        c.connect("127.0.0.1", port=22, username=user, password=password,
                  pkey=key, allow_agent=False, look_for_keys=False,
                  timeout=5, auth_timeout=5, banner_timeout=5)
    except Exception:
        c.close()
        raise
    return c
def denied(password, user="root"):
    try:
        c=connect(password=password,user=user)
    except paramiko.AuthenticationException:
        return
    c.close()
    raise AssertionError("Unexpected authentication success")
def ready():
    for _ in range(30):
        try:
            c=connect(key=key); c.close(); return
        except (OSError,paramiko.SSHException):
            time.sleep(.2)
    raise RuntimeError("Dropbear did not become ready")

keypath=work/"test-key"
subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(keypath)],check=True)
key=paramiko.Ed25519Key.from_private_key_file(str(keypath))
(data/"ssh/authorized_keys").write_bytes(keypath.with_suffix(".pub").read_bytes())
settings.write_text("ssh = on\n")
run("up")
ready()
denied("no-password-configured")
print("PASS existing public key and default key-only policy",flush=True)

assert run("set-password",text="short\n",check=False).returncode!=0
assert not hashfile.exists()
pw=secrets.token_urlsafe(15)+" '$!\\ test"
run("set-password",text=pw+"\n")
ready()
stored=hashfile.read_text().strip()
assert stored.startswith("$6$") and crypt.crypt(pw,stored)==stored and pw not in stored
assert (root/"etc/shadow").read_text().splitlines()[0].split(":")[1]==stored
denied("definitely-wrong")
denied(pw,user="nobody")
with connect(password=pw) as c:
    _, out, _=c.exec_command("printf banana-ssh-ok")
    assert out.read()==b"banana-ssh-ok"
    with c.open_sftp() as s:
        assert "banana" in s.listdir("/data")
        d="/data/banana/ssh-test"
        s.mkdir(d)
        payload=os.urandom(2*1024*1024)
        with s.file(d+"/upload.bin","wb") as f: f.write(payload)
        s.rename(d+"/upload.bin",d+"/renamed.bin")
        with s.file(d+"/renamed.bin","rb") as f: assert f.read()==payload
        assert s.stat(d+"/renamed.bin").st_size==len(payload)
        s.remove(d+"/renamed.bin")
        s.rmdir(d)
print("PASS password, denied wrong password/non-root, shell and 2 MiB SFTP upload/rename/download/delete",flush=True)

run("down")
assert not (root/"run/banana/dropbear.pid").exists()
run("up")
ready()
with connect(password=pw) as c:
    with c.open_sftp() as s: assert s.stat("/data/banana").st_mode
print("PASS password persistence across SSH restart",flush=True)
newpw=secrets.token_urlsafe(18)
run("set-password",text=newpw+"\n")
ready()
denied(pw)
with connect(password=newpw) as c:
    assert c.get_transport().is_authenticated()
print("PASS password rotation",flush=True)

run("clear-password")
ready()
assert not hashfile.exists()
denied(newpw)
with connect(key=key) as c:
    with c.open_sftp() as s: assert s.stat("/data").st_mode
print("PASS key-only mode restored and key-based SFTP",flush=True)
run("down")
print("PASS all SSH/SFTP integration tests",flush=True)
