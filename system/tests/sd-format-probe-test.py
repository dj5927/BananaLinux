import importlib.util
from pathlib import Path
import os,sys,tempfile
import fcntl,subprocess
from unittest.mock import patch
tool=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'rootfs/usr/libexec/banana/sd-format.py'
spec=importlib.util.spec_from_file_location('sdformat',tool);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='banana-sd-probe-',dir='/tmp') as tmp:
 t=Path(tmp)
 def write(p,s):
  f=t/p.lstrip('/');f.parent.mkdir(parents=True,exist_ok=True);f.write_text(s);return f
 def mapped(p):
  s=str(p)
  return t/s.lstrip('/') if s.startswith(('/sys/','/proc/','/etc/','/data/')) else Path(s)
 def reject():
  try:m.probe()
  except RuntimeError:return
  raise AssertionError('unsafe format probe accepted')
 write('/etc/banana/board','rgds');write('/data/banana/emmc-install.conf','version=1')
 for n,typ in (('mmcblk0','MMC'),('mmcblk1','SD')):
  for f,v in {'device/type':typ,'device/cid':'identity-'+n,'dev':'179:'+('0' if n.endswith('0') else '32'),'size':str(512*1024**2//512),'diskseq':'5','ro':'0'}.items():write('/sys/class/block/'+n+'/'+f,v)
 for dev,n in (('179:2','mmcblk0p2'),('179:4','mmcblk0p4'),('179:33','mmcblk1p1')):
  p=t/'sys/dev/block'/dev;p.parent.mkdir(parents=True,exist_ok=True);p.symlink_to(t/n)
 info='1 0 179:2 / / ro - squashfs /dev/root ro\n2 1 179:4 / /data rw - exfat /dev/mmcblk0p4 rw\n3 1 179:33 / /run/sd2 rw - exfat /dev/mmcblk1p1 rw\n'
 write('/proc/self/mountinfo',info)
 m.RUN=t/'run';m.RUN.mkdir();(m.RUN/'disk').write_text('/dev/mmcblk0')
 m.PLAN=m.RUN/'plan.json';m.TOKEN=m.RUN/'token'
 with patch.object(m,'Path',mapped),patch.object(m,'media_map',return_value=['roms:roms']),patch.object(m.shutil,'which',return_value='/fixture/tool'),patch.object(m.subprocess,'run') as run:
  run.return_value.returncode=1
  for b in ('rgds','rgds-plus'):
   write('/etc/banana/board',b);assert m.probe()['card']['name']=='mmcblk1'
  # CONFIG_SWAP=n: file intentionally absent.
  write('/sys/class/block/mmcblk0/device/type','SD');reject();write('/sys/class/block/mmcblk0/device/type','MMC')
  write('/proc/self/mountinfo',info.replace('179:2','179:33',1));reject();write('/proc/self/mountinfo',info)
  write('/proc/self/mountinfo',info.replace('179:4','179:33',1));reject();write('/proc/self/mountinfo',info)
  write('/sys/class/block/mmcblk1/ro','1');reject();write('/sys/class/block/mmcblk1/ro','0')
  write('/sys/class/block/mmcblk2/device/type','SD');reject();(t/'sys/class/block/mmcblk2/device/type').unlink()
  write('/sys/class/block/mmcblk1/holders/busy','');reject();(t/'sys/class/block/mmcblk1/holders/busy').unlink()
  write('/proc/self/mountinfo',info+'4 1 179:33 / /mnt/alias rw - exfat /dev/disk/by-uuid/alias rw\n');reject();write('/proc/self/mountinfo',info)
  run.return_value.returncode=0;reject();run.return_value.returncode=1
  swap=t/'swapfile';swap.write_text('fixture');st=swap.stat();dev=f'{os.major(st.st_dev)}:{os.minor(st.st_dev)}'
  p=t/'sys/dev/block'/dev;p.symlink_to(t/'mmcblk1p1')
  write('/proc/swaps','Filename Type Size Used Priority\n'+str(swap)+' file 1 0 -1\n');reject();(t/'proc/swaps').unlink()
  original=Path.read_text
  def denied(p,*a,**kw):
   if p==t/'proc/swaps':raise PermissionError('fixture denied')
   return original(p,*a,**kw)
  with patch.object(Path,'read_text',denied):
   try:m.probe()
   except PermissionError:pass
   else:raise AssertionError('permission error ignored')
  plan=m.probe();write('/sys/class/block/mmcblk1/diskseq','6')
  with patch.object(m,'cmd',side_effect=AssertionError('write command before revalidation')):
   try:m.format_card(plan,'exfat')
   except RuntimeError:pass
   else:raise AssertionError('replaced card accepted')
  write('/sys/class/block/mmcblk1/diskseq','5')
  with patch.object(m,'cmd',side_effect=subprocess.CalledProcessError(1,['umount'])),patch.object(m,'reset_layout',side_effect=AssertionError('busy card was erased')):
   try:m.format_card(m.probe(),'fat32')
   except subprocess.CalledProcessError:pass
   else:raise AssertionError('failed unmount ignored')
  for lock in ('sd-media.lock','update-apply.lock'):
   with open(m.RUN/lock,'a') as held:
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with patch.object(m.sys,'argv',['sd-format','probe']),patch.object(m,'probe',side_effect=AssertionError('operation bypassed storage lock')):
     try:m.main()
     except BlockingIOError:pass
     else:raise AssertionError('storage lock ignored')
  with patch.object(m.sys,'argv',['sd-format','probe']):m.main()
  with patch.object(m,'format_card',side_effect=AssertionError('expired token accepted')):
   with patch.object(m.sys,'argv',['sd-format','format','exfat','ERASE-ENTIRE-SD','wrong']):
    try:m.main()
    except RuntimeError:pass
    else:raise AssertionError('wrong token accepted')
print('SD_FORMAT_BOTH_BOARDS_SYSTEM_PROTECTION_BUSY_SWAP_REPLACED_CARD_AND_TOKEN_PASS')
