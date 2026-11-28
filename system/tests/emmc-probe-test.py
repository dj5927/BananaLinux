import importlib.util
from pathlib import Path
import tempfile
import sys
from unittest.mock import patch
tool=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'rootfs/usr/libexec/banana/emmc-install.py'
spec=importlib.util.spec_from_file_location('m',tool);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
# Use /tmp for native and qemu -L runs: the target firmware maps /var to /tmp.
with tempfile.TemporaryDirectory(prefix='banana-emmc-probe-',dir='/tmp') as tmp:
 t=Path(tmp)
 def write(p,s):
  f=t/p.lstrip('/');f.parent.mkdir(parents=True,exist_ok=True);f.write_text(s);return f
 write('/etc/banana/board','rgds\n')
 write('/sys/class/block/mmcblk1/device/type','SD\n')
 write('/sys/class/block/mmcblk0/device/type','MMC\n')
 write('/sys/class/block/mmcblk0/ro','0\n');write('/sys/class/block/mmcblk0/size',str(8*1024**3//512))
 mounts='/dev/mmcblk1p4 /data exfat rw 0 0\n/dev/mmcblk1p1 /boot vfat ro 0 0\n'
 write('/proc/mounts',mounts);write('/proc/swaps','Filename Type Size Used Priority\n')
 info='1 0 179:34 / / ro - squashfs /dev/root ro\n'
 write('/proc/self/mountinfo',info)
 f=t/'sys/dev/block/179:34';f.parent.mkdir(parents=True);f.symlink_to(t/'mmcblk1p2')
 f=t/'sys/dev/block/179:1';f.symlink_to(t/'mmcblk0p1')
 write('/boot/a/Image','kernel')
 m.RUN=t/'run';m.RUN.mkdir();(m.RUN/'disk').write_text('/dev/mmcblk1\n');(m.RUN/'slot').write_text('a\n')
 m.DATA=t/'data';(m.DATA/'banana').mkdir(parents=True)
 def mapped(s):
  s=str(s)
  return t/s.lstrip('/') if any(s.startswith(k) for k in ('/sys/','/proc/mounts','/proc/swaps','/proc/self/','/etc/','/boot/')) else Path(s)
 source={'label':'gpt','sectorsize':512,'partitions':[{'start':s,'size':n,'type':'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7'} for s,n in ((32768,131072),(163840,524288),(688128,524288),(1212416,1000000))]}
 def reject():
  try:m.probe()
  except RuntimeError:return
  raise AssertionError('unsafe probe accepted')
 with patch.object(m,'Path',mapped),patch.object(m,'table',return_value=source),patch.object(m.shutil,'which',return_value='/fixture/tool'):
  assert m.probe()['target']=='/dev/mmcblk0'
  # CONFIG_SWAP=n omits /proc/swaps entirely on production firmware.
  (t/'proc/swaps').unlink()
  for board in ('rgds','rgds-plus'):
   write('/etc/banana/board',board)
   assert m.probe()['target']=='/dev/mmcblk0'
  write('/proc/swaps','Filename Type Size Used Priority\n')
  # Missing optional file is allowed; permission and I/O failures must abort.
  original_read=Path.read_text
  for error in (PermissionError(13,'fixture denied'),OSError(5,'fixture I/O')):
   def failed_read(path,*args,**kwargs):
    if path==t/'proc/swaps':raise error
    return original_read(path,*args,**kwargs)
   with patch.object(Path,'read_text',failed_read):
    try:m.probe()
    except type(error):pass
    else:raise AssertionError('swaps read failure was ignored')
  write('/sys/class/block/mmcblk0/ro','1');reject();write('/sys/class/block/mmcblk0/ro','0')
  write('/proc/mounts',mounts+'/dev/mmcblk0p1 /mnt/internal vfat rw 0 0\n');reject();write('/proc/mounts',mounts)
  write('/proc/self/mountinfo',info+'2 0 179:1 / /mnt/alias rw - vfat /dev/disk/by-uuid/alias rw\n');reject();write('/proc/self/mountinfo',info)
  write('/proc/swaps','Filename Type Size Used Priority\n/dev/mmcblk0p2 partition 1 0 -1\n');reject();write('/proc/swaps','Filename Type Size Used Priority\n')
  write('/sys/class/block/mmcblk1/device/type','MMC');reject();write('/sys/class/block/mmcblk1/device/type','SD')
  write('/proc/mounts','tmpfs /data tmpfs rw 0 0\n');reject();write('/proc/mounts',mounts)
  write('/etc/banana/board','other');reject();write('/etc/banana/board','rgds-plus')
  assert m.probe()['target']=='/dev/mmcblk0'
print('EMMC_PREFLIGHT_BOTH_BOARDS_NO_SWAP_AND_UNSAFE_TARGET_REJECTIONS_PASS')
