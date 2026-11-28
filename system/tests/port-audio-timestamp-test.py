from pathlib import Path
import os,subprocess,tempfile,time,signal
r=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='port-audio-ts-') as td:
 d=Path(td);cc=os.environ.get('CC','cc');runner=os.environ.get('RUNNER','').split()
 def run(args,**kw):return subprocess.run(args,check=True,**kw)
 mock=d/'libmock-alsa.so';client=d/'client'
 run([cc,'-O2','-fPIC','-shared',str(r/'system/tests/port-audio/mock-alsa.c'),'-Wl,--version-script='+str(r/'system/tests/port-audio/mock-alsa.map'),'-o',str(mock)])
 run([cc,'-O2',str(r/'system/tests/port-audio/timestamp-client.c'),'-L'+str(d),'-lmock-alsa','-lpthread','-Wl,-rpath,'+str(d),'-o',str(client)])
 sources=[('fixed',r/'ui/src/port_audio.c')]
 if os.environ.get('PREVIOUS_AUDIO_SOURCE'):sources.insert(0,('previous',Path(os.environ['PREVIOUS_AUDIO_SOURCE'])))
 for mode,source in sources:
  lib=d/(mode+'.so');run([cc,'-O2','-Wall','-Wextra','-Werror','-fPIC','-shared',str(source),'-o',str(lib),'-ldl','-lpthread'])
  env=os.environ|({'LD_PRELOAD':str(lib),'BANANA_PORT_AUDIO_RECOVERY':'1'} if not runner else {})
  args=runner+['-E','LD_PRELOAD='+str(lib),'-E','BANANA_PORT_AUDIO_RECOVERY=1',str(client)] if runner else [str(client)]
  p=subprocess.run(args,env=env);assert p.returncode==(42 if mode=='previous' else 0)
  ticks=d/(mode+'.ticks');child=subprocess.Popen(args+[str(ticks)],env=env)
  def value():
   try:return int(ticks.read_text())
   except (FileNotFoundError,ValueError):return 0
  def wait(fn):
   end=time.monotonic()+5
   while not fn():
    assert time.monotonic()<end,'timeout'
    time.sleep(.02)
  try:
   wait(lambda:value()>5)
   for cycle in range(1 if mode=='previous' else 3):
    os.kill(child.pid,signal.SIGSTOP);time.sleep(.3);before=value();os.kill(child.pid,signal.SIGCONT)
    if mode=='previous':assert child.wait(timeout=5)==42
    else:wait(lambda:value()>before+4);assert child.poll() is None
   print('TIMESTAMP_REAL_SIGNAL_PCM_MODEL_PASS',mode,flush=True)
  finally:
   if child.poll() is None:child.send_signal(signal.SIGCONT);child.terminate();child.wait(timeout=5)
print('PORT_AUDIO_TIMESTAMP_REGRESSION_PASS',flush=True)