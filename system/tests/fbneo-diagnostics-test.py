from pathlib import Path
import importlib.util,tempfile,json,os,subprocess,select,time,hashlib
r=Path(__file__).resolve().parents[2];source=r/'system/rootfs/usr/libexec/banana/fbneo-diagnostics.py'
spec=importlib.util.spec_from_file_location('diag',source);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
with tempfile.TemporaryDirectory(prefix='fbneo-diag-') as td:
 root=Path(td);d.DATA=root/'data';d.PROC=root/'proc';d.SYS=root/'sys'
 def put(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
 def process(pid,parent,ticks=100,start=123):
  rest=['0']*40;rest[0]='R';rest[1]=str(parent);rest[11]=str(ticks);rest[12]='10';rest[19]=str(start)
  put(d.PROC/str(pid)/'stat',f'{pid} (emulator ) name) '+' '.join(rest))
  put(d.PROC/str(pid)/'status','Name:\tretroarch\nState:\tR\nThreads:\t4\nCpus_allowed_list:\t0-3\n')
  put(d.PROC/str(pid)/'maps','100-200 r-xp 0 00:00 1 /usr/lib/libretro/fbneo_libretro.so\n')
 process(77,1);process(78,77)
 put(d.DATA/'retroarch/config/FinalBurn Neo/vf.opt','fbneo-dipswitch-vf-Resolution = "2160p"\npassword = "DO_NOT_LOG"\n')
 put(d.DATA/'retroarch/retroarch.cfg','video_threaded = "false"\ncheevos_token = "SECRET_TOKEN"\n')
 put(d.DATA/'banana/emulator-defaults.conf','fbneo.ra_frontend = retroarch\nra_password = SECRET_PASSWORD\nfbneo.ra_password = SCOPED_SECRET\n')
 put(d.SYS/'devices/system/cpu/cpufreq/policy0/scaling_cur_freq','1800000\n')
 put(d.SYS/'devices/system/cpu/cpufreq/policy0/scaling_max_freq','1800000\n')
 put(d.SYS/'class/thermal/thermal_zone0/temp','45000\n')
 assert d.proc_stat(77)['start']==123,'proc comm with closing parentheses parsed incorrectly'
 before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for b in [d.DATA,d.SYS] for p in b.rglob('*') if p.is_file()}
 previous={};a=d.processes(77,previous,1);process(78,77,150);b=d.processes(77,previous,2)
 assert next(x for x in b if x['pid']==78)['cpu_percent_of_one_core']>0
 assert next(x for x in b if x['pid']==78)['core_paths']==['/usr/lib/libretro/fbneo_libretro.so']
 d.run(77,Path('/roms/vf.zip'),delays=(0,.01))
 log=d.DATA/'banana/logs/fbneo-diagnostics.log';text=log.read_text();lines=[json.loads(x) for x in text.splitlines()]
 assert [x['type'] for x in lines]==['context','runtime','runtime','complete']
 assert '2160p' in text and '1800000' in text and 'retroarch' in text
 assert all(secret not in text for secret in ['DO_NOT_LOG','SECRET_TOKEN','SECRET_PASSWORD','SCOPED_SECRET'])
 assert log.stat().st_mode&0o777==0o600
 for path,digest in before.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'modified configuration or clock'
 d.run(77,Path('/roms/vf.zip'),delays=())
 assert (log.parent/'fbneo-diagnostics.previous.log').read_text()==text
 real=d.proc_stat;calls=[0]
 def reused(pid):
  calls[0]+=1;p=real(pid)
  if p and calls[0]>1:p['start']+=1
  return p
 d.proc_stat=reused;d.run(77,Path('/roms/vf.zip'),delays=(100,));d.proc_stat=real
 assert json.loads(log.read_text().splitlines()[-1])['type']=='parent_exited'
 print('DIAG_OPTIONS_PRIVACY_CLOCKS_PID_REUSE_ROTATION_PASS',flush=True)
 # A background collector must release inherited lease/FIFO descriptors while still alive.
 rd,wr=os.pipe();os.set_inheritable(wr,True)
 script=f'''import importlib.util,sys\nfrom pathlib import Path\ns=importlib.util.spec_from_file_location("diag",{str(source)!r});m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nm.DATA=Path({str(d.DATA)!r});m.PROC=Path({str(d.PROC)!r});m.SYS=Path({str(d.SYS)!r});sys.argv=["diag","77","vf.zip"];m.main()\n'''
 child=subprocess.Popen(['python3','-c',script],pass_fds=(wr,),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 os.close(wr)
 try:
  assert select.select([rd],[],[],3)[0],'collector kept inherited FD open'
  assert os.read(rd,1)==b''
  assert child.poll() is None,'collector exited instead of releasing descriptor'
  print('DIAG_INHERITED_FD_RELEASE_PASS',flush=True)
 finally:
  child.terminate();child.wait(timeout=3);os.close(rd)
print('FBNEO_DIAGNOSTICS_QA_PASS',flush=True)