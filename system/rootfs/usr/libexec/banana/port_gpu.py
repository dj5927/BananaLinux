#!/usr/bin/env python3
"""Per-port graphics selection. Driver changes are restricted to a GPU lease."""
import ctypes
import fcntl
import importlib.util
import os
import shutil
import signal
import tempfile
import time
from pathlib import Path


def read_conf(path):
    values={}
    try:
        for line in Path(path).read_text(encoding='utf-8-sig',errors='replace').splitlines():
            if '=' in line and not line.lstrip().startswith(('#',';')):
                k,v=line.split('=',1);values[k.strip()]=v.strip()
    except FileNotFoundError:
        pass
    return values


def driver_for(data,key,manager=False):
    if manager:
        return 'panfrost'
    default='panfrost'
    per=read_conf(Path(data)/'banana/rpg-per-game.conf')
    value=per.get(key.encode('utf-8','surrogateescape').hex()+'.gpu_driver','')
    return value if value in ('panfrost','mali') else default


class PortGPU:
    def __init__(self,data,key,log,logfile,manager=False,run_dir=Path('/run/banana'),session_factory=None,modules=Path('/sys/module')):
        self.data=Path(data);self.log=log;self.logfile=logfile
        self.driver=driver_for(data,key,manager)
        self.run_dir=Path(run_dir);self.modules=Path(modules)
        self.session_factory=session_factory
        self.fd=None;self.session=None;self.lib=None
    def start(self,env,cancelled=lambda:False):
        self.run_dir.mkdir(parents=True,exist_ok=True)
        self.fd=os.open(self.run_dir/'easyemu-gpu.lock',os.O_CREAT|os.O_RDWR|os.O_CLOEXEC,0o600)
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (self.modules/'mali_kbase').exists():raise RuntimeError('GPU already owned by another Mali session')
        env=env.copy();env['BANANA_PORT_GPU_DRIVER']=self.driver
        self.log('graphics driver='+self.driver)
        if self.driver=='panfrost':return env
        if self.session_factory is None:
            spec=importlib.util.spec_from_file_location('port_duck_gpu',Path(__file__).with_name('duckstation-supervisor.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            factory=module.MaliSession
        else:factory=self.session_factory
        self.session=factory(self.log,self.logfile)
        original=env.get('LD_LIBRARY_PATH','')
        self.session.start(self.data,env,cancelled,lambda phase,detail='':self.log(phase+' '+detail))
        if cancelled():raise RuntimeError('cancelled')
        runtime=Path(env['LD_LIBRARY_PATH'])
        self.lib=Path(tempfile.mkdtemp(prefix='port-mali-',dir=self.run_dir))
        # Do not expose EasyPSP's SDL to arbitrary ports: keep the established ports SDL.
        files=('libEGL.so.1','libGLESv1_CM.so.1','libGLESv2.so.2','libgbm.so.1',
               'libmali.so.1','libmali-hook.so.1','libMaliVulkan.so.1','libvulkan.so.1')
        for name in files:
            target=runtime/name
            if not target.is_file():raise RuntimeError('Missing Mali graphics library: '+name)
            (self.lib/name).symlink_to(target)
        for short,full in [('libEGL.so','libEGL.so.1'),('libGLESv2.so','libGLESv2.so.2'),
                           ('libGLESv1_CM.so','libGLESv1_CM.so.1'),('libgbm.so','libgbm.so.1')]:
            (self.lib/short).symlink_to(full)
        paths=[]
        if env.get('BANANA_DRM_LEASE_FD'):paths.append('/usr/lib/banana/ports/lib')
        paths.append(str(self.lib))
        paths.extend(p for p in original.split(':') if p and p not in paths)
        env['LD_LIBRARY_PATH']=':'.join(paths)
        env['BANANA_PORT_GPU_LIB']=str(self.lib)
        # MaliSession's Duck-specific renderer flag has no role in a port.
        env.pop('BANANA_DUCK_VK_DRM',None)
        self.log('Mali libraries='+str(self.lib)+'; dedicated ports SDL retained')
        return env
    def close(self):
        try:
            if self.session is not None:
                self.session.close()
                if (self.modules/'mali_kbase').exists():raise RuntimeError('Mali still busy; Panfrost restore refused')
                if not (self.modules/'panfrost').exists():
                    self.session.command('modprobe','panfrost')
                if not (self.modules/'panfrost').exists():raise RuntimeError('Panfrost restore failed')
        finally:
            if self.lib is not None:shutil.rmtree(self.lib,ignore_errors=True)
            if self.fd is not None:os.close(self.fd);self.fd=None


def process_snapshot(root=Path('/proc')):
    result={}
    for p in root.iterdir():
        if not p.name.isdigit():continue
        try:
            text=(p/'stat').read_text();fields=text[text.rindex(')')+2:].split()
            result[int(p.name)]=(int(fields[1]),fields[0],int(fields[19]))
        except (OSError,ValueError,IndexError):pass
    return result


class PortProcesses:
    """Adopt/clean detached descendants before releasing their GPU driver."""
    def __init__(self,log):
        self.log=log;self.paused={}
        libc=ctypes.CDLL(None,use_errno=True)
        if libc.prctl(36,1,0,0,0)!=0:raise OSError(ctypes.get_errno(),'PR_SET_CHILD_SUBREAPER')
    def descendants(self):
        all_=process_snapshot();parents={os.getpid()};found={}
        while True:
            new={p:info for p,info in all_.items() if p not in parents and info[0] in parents}
            if not new:return found
            found.update(new);parents.update(new)
    def send(self,pid,started,sig):
        try:
            fd=os.pidfd_open(pid)
            try:
                current=process_snapshot().get(pid)
                if current is None or current[2]!=started:return False
                signal.pidfd_send_signal(fd,sig)
                return True
            finally:os.close(fd)
        except ProcessLookupError:return False
    def pause(self):
        # Freeze launchers first, then collect again so newly forked children cannot escape.
        for _ in range(8):
            new={p:i for p,i in self.descendants().items() if p not in self.paused and i[1] not in ('T','t','Z','X')}
            if not new:break
            for p,i in new.items():
                if self.send(p,i[2],signal.SIGSTOP):self.paused[p]=i[2]
    def resume(self):
        for p,started in list(self.paused.items()):self.send(p,started,signal.SIGCONT)
        self.paused.clear()
    def cleanup(self,child):
        self.resume()
        for sig,seconds in [(signal.SIGTERM,2),(signal.SIGKILL,1)]:
            self.log('port cleanup '+sig.name)
            until=time.monotonic()+seconds
            while True:
                if child is not None:child.poll()
                tree=self.descendants()
                for p,i in tree.items():
                    if i[1] not in ('Z','X'):
                        self.send(p,i[2],signal.SIGCONT)
                        self.send(p,i[2],sig)
                    elif child is None or p!=child.pid:
                        try:os.waitpid(p,os.WNOHANG)
                        except ChildProcessError:pass
                if not {p:i for p,i in self.descendants().items() if i[1] not in ('Z','X')}:return
                if time.monotonic()>=until:break
                time.sleep(.05)
            self.log('port cleanup escalating after '+sig.name)
        raise RuntimeError('Port processes still active; GPU cannot be released')
