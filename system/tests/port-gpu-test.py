#!/usr/bin/env python3
from pathlib import Path
import os,sys,tempfile,io,subprocess,signal,time,importlib.util
base=Path(__file__).resolve().parents[2]
root=base/'system/rootfs/usr/libexec/banana'
sys.path.insert(0,str(root))
from port_gpu import PortGPU,PortProcesses,driver_for
count=0
def check(v,msg):
 global count
 assert v,msg;count+=1
with tempfile.TemporaryDirectory() as t:
 d=Path(t);(d/'banana').mkdir();key='ports/한글 게임.sh';k=key.encode().hex()+'.gpu_driver'
 check(driver_for(d,key)=='panfrost','default')
 (d/'banana/rpg-per-game.conf').write_text(k+' = mali\nother = preserved\n')
 check(driver_for(d,key)=='mali','per game')
 check(driver_for(d,'ports/Other.sh')=='panfrost','independent game')
 check(driver_for(d,key,True)=='panfrost','manager')
 modules=d/'modules';modules.mkdir();runtime=d/'runtime';runtime.mkdir();run=d/'run';run.mkdir()
 names=('libEGL.so.1','libGLESv1_CM.so.1','libGLESv2.so.2','libgbm.so.1','libmali.so.1','libmali-hook.so.1','libMaliVulkan.so.1','libvulkan.so.1')
 for name in names:(runtime/name).write_text(name)
 events=[]
 class Session:
  def __init__(self,*args):pass
  def start(self,data,env,cancel,progress):
   events.append('switch');(modules/'mali_kbase').mkdir();env.update(LD_LIBRARY_PATH=str(runtime),VK_ICD_FILENAMES=str(runtime/'mali.json'),BANANA_DUCK_VK_DRM='1')
  def command(self,*args,**kwargs):
   events.append('panfrost retry');(modules/'panfrost').mkdir(exist_ok=True);return 0
  def close(self):events.append('restore');(modules/'mali_kbase').rmdir()
 gpu=PortGPU(d,key,events.append,io.BytesIO(),run_dir=run,session_factory=Session,modules=modules)
 env=gpu.start({'LD_LIBRARY_PATH':'/old/libs','BANANA_DRM_LEASE_FD':'8'})
 check(env['LD_LIBRARY_PATH'].split(':')[:2]==['/usr/lib/banana/ports/lib',str(gpu.lib)],'scoped library priority')
 check(not (gpu.lib/'libSDL2-2.0.so.0').exists(),'no easyemu SDL injection')
 check((gpu.lib/'libEGL.so').resolve()==(runtime/'libEGL.so.1'),'EGL alias')
 check('BANANA_DUCK_VK_DRM' not in env,'no duck flag')
 second=PortGPU(d,'ports/Other.sh',events.append,io.BytesIO(),run_dir=run,modules=modules)
 try:second.start({});raise AssertionError('GPU lock not exclusive')
 except BlockingIOError:count+=1
 finally:second.close()
 lib=gpu.lib;gpu.close();check(not lib.exists() and not (modules/'mali_kbase').exists(),'normal restoration')
 # Partial startup failures still restore the switched driver.
 (runtime/'libEGL.so.1').unlink()
 gpu=PortGPU(d,key,events.append,io.BytesIO(),run_dir=run,session_factory=Session,modules=modules)
 try:gpu.start({});raise AssertionError('missing graphics lib accepted')
 except RuntimeError:count+=1
 finally:gpu.close()
 check(not (modules/'mali_kbase').exists(),'failure restoration')
 gpu=PortGPU(d,'ports/Other.sh',events.append,io.BytesIO(),run_dir=run,session_factory=lambda *a:(_ for _ in ()).throw(AssertionError('Panfrost switched')),modules=modules)
 env=gpu.start({'KEEP':'yes'});check(env['KEEP']=='yes' and env['BANANA_PORT_GPU_DRIVER']=='panfrost','Panfrost environment');gpu.close()
 # Real child lifecycle: a detached grandchild, pause/resume, cleanup after launcher exits.
 manager=PortProcesses(events.append)
 fixture=d/'fixture.py';fixture.write_text('''import os,time,signal
from pathlib import Path
p=Path(__file__).parent
if os.fork()==0:
 os.setsid();(p/'detached.pid').write_text(str(os.getpid()))
 n=0
 while True:
  n+=1;(p/'ticks').write_text(str(n));time.sleep(.01)
while True:time.sleep(.01)
''')
 child=subprocess.Popen([sys.executable,str(fixture)],start_new_session=True)
 def wait(fn):
  until=time.monotonic()+3
  while not fn():
   assert time.monotonic()<until,'fixture timeout';time.sleep(.02)
 wait(lambda:(d/'ticks').exists())
 manager.pause();time.sleep(.05);a=(d/'ticks').read_text();time.sleep(.08)
 check((d/'ticks').read_text()==a,'detached child paused')
 manager.resume();wait(lambda:(d/'ticks').read_text()!=a);count+=1
 child.terminate();child.wait(timeout=3);time.sleep(.05)
 check(bool(manager.descendants()),'orphan adopted before GPU restore')
 manager.cleanup(child);check(not {p:i for p,i in manager.descendants().items() if i[1]!='Z'},'detached child cleaned')
 # Native supervisor integration on Panfrost, retaining existing hotkeys and restart.
 script=d/'game.sh';script.write_text('echo "$BANANA_PORT_GPU_DRIVER" >> "$BANANA_PORT_DATA/driver.txt"\nwhile true; do sleep .1; done\n')
 fifo=d/'cmd';os.mkfifo(fifo);fd=os.open(fifo,os.O_RDWR|os.O_NONBLOCK);pause=d/'pause'
 env=os.environ|{'BANANA_PORT_DATA':str(d),'BANANA_GAME_KEY':'ports/Test.sh','BANANA_RA_CMD':str(fifo),'BANANA_SA_PAUSE_FILE':str(pause)}
 p=subprocess.Popen([sys.executable,str(root/'port-supervisor.py'),str(script)],env=env)
 wait(lambda:(d/'driver.txt').exists());check((d/'driver.txt').read_text().strip()=='panfrost','supervisor selected driver')
 os.write(fd,b'RESET\n');wait(lambda:len((d/'driver.txt').read_text().splitlines())==2);count+=1
 pause.touch();time.sleep(.3);pause.unlink();os.write(fd,b'QUIT\n');check(p.wait(timeout=5)==0,'supervisor quit');os.close(fd)
print('PORT_GPU_QA_PASS',count,flush=True)