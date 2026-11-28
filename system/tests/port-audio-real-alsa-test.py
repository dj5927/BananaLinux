"""Real ALSA plugin regression. CC/RUNNER allow target 1.2.15.3 under QEMU.
PREVIOUS_AUDIO_SOURCE is optional; its poll recovery must abort in plugin status.
"""
from pathlib import Path
import os,subprocess,tempfile
r=Path(__file__).resolve().parents[2]
cc=os.environ.get('CC','cc');runner=os.environ.get('RUNNER','').split()
with tempfile.TemporaryDirectory(prefix='port-audio-real-') as td:
 d=Path(td);fixture=d/'fault.so';client=d/'client';config=d/'asound.conf'
 def build(args):subprocess.run([cc,'-O2','-Wall','-Wextra','-Werror']+args,check=True)
 build(['-DPIC','-fPIC','-shared',str(r/'system/tests/port-audio/alsa-fault-plugin.c'),'-o',str(fixture),'-lasound'])
 build([str(r/'system/tests/port-audio/alsa-plugin-client.c'),'-o',str(client),'-lasound','-ldl'])
 config.write_text('pcm_type.banana_fault { lib "'+str(fixture)+'" }\npcm.fault { type banana_fault }\npcm.emul { type mmap_emul slave.pcm "fault" }\npcm.repro { type linear slave { pcm "emul" format S16_LE } }\n')
 sources=[('fixed',r/'ui/src/port_audio.c')]
 if os.environ.get('PREVIOUS_AUDIO_SOURCE'):sources.insert(0,('previous',Path(os.environ['PREVIOUS_AUDIO_SOURCE'])))
 base_config=config.read_text()
 for label,source in sources:
  lib=Path(os.environ['PORT_AUDIO_LIBRARY']) if label=='fixed' and os.environ.get('PORT_AUDIO_LIBRARY') else d/(label+'.so')
  if not (label=='fixed' and os.environ.get('PORT_AUDIO_LIBRARY')):build(['-fPIC','-shared',str(source),'-o',str(lib),'-ldl','-lpthread'])
  modes=[('linear','poll'),('linear','recover')]
  if label=='previous':modes=[('linear','poll')]
  elif os.environ.get('ALSA_EQ_MODULE'):modes += [('speaker','poll'),('speaker','recover')]
  for graph,mode in modes:
   rate=48000
   if graph=='speaker':
    eq=os.environ['ALSA_EQ_MODULE']
    config.write_text(base_config[:base_config.index('pcm.repro')]+ 'pcm_type.banana_eq { lib '+chr(34)+eq+chr(34)+' }\npcm.repro { type plug slave { pcm { type banana_eq slave.pcm '+chr(34)+'emul'+chr(34)+' } format S16_LE channels 2 rate 48000 } }\n')
    rate=44100
   else:config.write_text(base_config)
   print('REAL_ALSA_GRAPH',graph,mode,flush=True)
   values={'ALSA_CONFIG_PATH':str(config),'BANANA_PORT_AUDIO_RECOVERY':'1','LD_PRELOAD':str(lib)+(' '+os.environ['ALSA_PRELOAD'] if os.environ.get('ALSA_PRELOAD') and label=='fixed' else '')}
   env=os.environ|values if not runner else os.environ.copy()
   args=runner+sum((['-E',k+'='+v] for k,v in values.items()),[])+[str(client)] if runner else [str(client)]
   p=subprocess.run(args+[str(fixture),mode,str(rate)],env=env,capture_output=True,text=True,timeout=20)
   print(p.stdout+p.stderr,flush=True)
   if label=='previous':
    assert p.returncode in (-6,134),p.returncode
    assert 'snd_pcm_plugin_status' in p.stderr and 'appl_ptr' in p.stderr
    print('REAL_ALSA_V36_ASSERT_REPRODUCED',flush=True)
   else:assert p.returncode==0,(mode,p.returncode)
print('REAL_ALSA_PLUGIN_REGRESSION_PASS',flush=True)
