#!/usr/bin/env python3
"""Real loop disks, FAT32/exFAT and bind mounts; never uses a physical device."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'rootfs/usr/libexec/banana'
spec=importlib.util.spec_from_file_location('installer',TOOLS/'emmc-install.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def run(*args,**kw): return subprocess.check_output(args,text=True,**kw).strip()
def expect_fail(fn):
 try: fn()
 except Exception: return
 raise AssertionError('expected failure')
with tempfile.TemporaryDirectory(prefix='banana-v41-',dir='/var/tmp') as tmp:
 t=Path(tmp); loops=[]; mounted=[]
 def loop(name,size):
  p=t/name
  with p.open('wb') as f:f.truncate(size)
  d=run('losetup','--find','--show','--partscan',str(p));loops.append(d);return d
 def mount(d,p,fs=None):
  p.mkdir(parents=True,exist_ok=True);run('mount',*(['-t',fs] if fs else []),d,str(p));mounted.append(p)
 def umount(p):run('umount',str(p));mounted.remove(p)
 try:
  for fs in ('vfat','exfat'):
   disk=loop(fs+'.img',128*1024**2)
   run('mkfs.vfat' if fs=='vfat' else 'mkfs.exfat',disk)
   media=t/fs;mount(disk,media,fs)
   (media/'KEEP.txt').write_bytes(b'unchanged')
   for _ in range(2):run('sh',str(TOOLS/'media-layout'),str(media),str(ROOT/'rootfs/etc/banana/systems.conf'))
   assert (media/'roms/psx').is_dir() and (media/'roms/ports').is_dir()
   assert (media/'bios/mkxp/rtp/vxace').is_dir()
   assert (media/'KEEP.txt').read_bytes()==b'unchanged'
   (media/'roms/psx/Korean-test.bin').write_bytes(b'rom')
   assert not (media/'banana/settings.conf').exists()
   bind=t/('bind-'+fs);bind.mkdir()
   run('mount','--bind',str(media/'saves'),str(bind));mounted.append(bind)
   (bind/'test.sav').write_bytes(b'SAVE')
   assert (media/'saves/test.sav').read_bytes()==b'SAVE'
   umount(bind)
   internal=t/('internal-'+fs);(internal/'banana').mkdir(parents=True)
   (internal/'banana/settings.conf').write_bytes(b'ORIGINAL-SETTINGS')
   (internal/'banana/emmc-install.conf').write_text('version=1\n')
   state=t/('state-'+fs);(state/'sd2').mkdir(parents=True)
   (state/'disk').write_text('/dev/mmcblk0\n')
   sysfs=t/('sys-'+fs);(sysfs/'mmcblk0/device').mkdir(parents=True)
   (sysfs/'mmcblk0/device/type').write_text('MMC\n')
   lib=t/('tools-'+fs);lib.mkdir()
   shutil.copyfile(TOOLS/'media-layout',lib/'media-layout');(lib/'media-layout').chmod(0o755)
   helper=(TOOLS/'emmc-media').read_text().replace('/sys/class/block',str(sysfs)).replace('/run/banana',str(state)).replace('/run/sd2',str(media)).replace('/data',str(internal)).replace('/usr/libexec/banana',str(lib)).replace('/etc/banana/systems.conf',str(ROOT/'rootfs/etc/banana/systems.conf'))
   script=lib/'emmc-media';script.write_text(helper)
   legacy=media/'banana/duckstation/memcards';legacy.mkdir(parents=True)
   (legacy/'old.mcd').write_bytes(b'LEGACY-SAVE')
   run('sh',str(script),'attach')
   try:
    assert (internal/'roms/psx/Korean-test.bin').read_bytes()==b'rom'
    assert (internal/'banana/duckstation/memcards/old.mcd').read_bytes()==b'LEGACY-SAVE'
    (internal/'banana/duckstation/memcards/new.mcd').write_bytes(b'NEW-SAVE')
    assert (media/'saves/psx/new.mcd').read_bytes()==b'NEW-SAVE'
    assert (internal/'banana/settings.conf').read_bytes()==b'ORIGINAL-SETTINGS'
    run('sh',str(script),'attach')
   finally: run('sh',str(script),'detach')
   assert not (internal/'roms/psx/Korean-test.bin').exists()
   assert (media/'saves/psx/new.mcd').read_bytes()==b'NEW-SAVE'
   umount(media)
   print('MEDIA_LAYOUT_PASS',fs,flush=True)
  source=loop('source.img',4*1024**3);target=loop('target.img',4*1024**3)
  raw='label: gpt\nunit: sectors\n\nstart=32768,size=131072,type=EBD0A0A2-B9E5-4433-87C0-68B6B72699C7,name="boot"\nstart=163840,size=524288,type=0FC63DAF-8483-4772-8E79-3D69D8477DE4,name="banana-root-a"\nstart=688128,size=524288,type=0FC63DAF-8483-4772-8E79-3D69D8477DE4,name="banana-root-b"\nstart=1212416,type=EBD0A0A2-B9E5-4433-87C0-68B6B72699C7,name="banana-data"\n'
  subprocess.run(['sfdisk',source],input=raw,text=True,check=True,stdout=subprocess.DEVNULL)
  run('partx','--update',source)
  # The production code uses MMC p<n>; loop disks use the same convention.
  run('mkfs.vfat',source+'p1');run('mkfs.exfat',source+'p4')
  boot=t/'boot';mount(source+'p1',boot)
  (boot/'extlinux').mkdir()
  conf=(ROOT.parent/'buildroot/board/rgds/extlinux.conf.in').read_text().replace('@DTB@','fixture')
  (boot/'extlinux/extlinux.conf').write_text(conf)
  (boot/'a').mkdir();(boot/'a/Image').write_bytes(b'kernel')
  umount(boot)
  # Deterministic roots and Rockchip-loader fixture.
  with open(source,'r+b',buffering=0) as f:
   f.seek(32768);f.write(b'ROCKCHIP-TEST-LOADER'*100)
  for i in (2,3):
   with open(source+'p'+str(i),'r+b',buffering=0) as f:f.write(('root-'+str(i)).encode()*4096)
  data=t/'data';mount(source+'p4',data)
  (data/'banana').mkdir();(data/'banana/settings.conf').write_bytes(b'language=ko\nface_layout=xbox\n')
  (data/'roms').mkdir();(data/'roms/keep.rom').write_bytes(b'USER-ROM')
  source_table=m.table(source);capacity=4*1024**3
  layout,guids=m.partition_plan(source_table,capacity)
  expect_fail(lambda:m.partition_plan(source_table,1024**3))
  bad=dict(source_table);bad['label']='dos';expect_fail(lambda:m.partition_plan(bad,capacity))
  new=m.rewrite_extlinux(conf,guids,'b')
  assert 'DEFAULT b' in new and 'banana.slot=b' in new and 'PARTLABEL=' not in new
  assert guids[1] in new and guids[2] in new
  expect_fail(lambda:m.rewrite_extlinux('LABEL a\n APPEND quiet\n',guids,'a'))
  m.DATA=data;m.RUN=t/'run';m.WORK=t/'target-mount'
  p=dict(source=source,target=target,capacity=capacity,layout=layout,guids=guids,slot='a',settings=[data/'banana'])
  m.install(p)
  assert (m.RUN/'emmc-status').read_text().startswith('done')
  mount(target+'p4',m.WORK)
  assert (m.WORK/'banana/settings.conf').read_bytes()==b'language=ko\nface_layout=xbox\n'
  assert (m.WORK/'banana/emmc-install.conf').is_file()
  assert not (m.WORK/'roms').exists();umount(m.WORK)
  mount(target+'p1',m.WORK)
  cfg=(m.WORK/'extlinux/extlinux.conf').read_text()
  assert 'PARTLABEL=' not in cfg and 'banana.slot=a' in cfg
  umount(m.WORK)
  assert (data/'roms/keep.rom').read_bytes()==b'USER-ROM'
  assert [p['uuid'] for p in m.table(target)['partitions']]!=[p['uuid'] for p in source_table['partitions']]
  print('EMMC_LOOP_INSTALL_READBACK_SETTINGS_PASS',flush=True)
 finally:
  for p in reversed(mounted):subprocess.run(['umount','-l',str(p)])
  for d in reversed(loops):subprocess.run(['losetup','-d',d])
print('ALL_STORAGE_TESTS_PASS',flush=True)
