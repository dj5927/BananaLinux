"""Exercise the production destructive core exclusively on fresh loop disks."""
import importlib.util,os,sys,tempfile,subprocess,json,builtins
from pathlib import Path
from unittest.mock import patch
root=Path(sys.argv[1]);repo=Path(sys.argv[2])
spec=importlib.util.spec_from_file_location('fmt',root/'usr/libexec/banana/sd-format.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
run=subprocess.run
def checked(*args,**kw):return subprocess.check_output(args,text=True,**kw).strip()
for fs in ('fat32','exfat'):
 with tempfile.TemporaryDirectory(prefix='banana-sd-loop-',dir='/var/tmp') as tmp:
  t=Path(tmp);image=t/'sd.img';image.touch();os.truncate(image,512*1024**2)
  loop=checked('losetup','--find','--show','--partscan',str(image));mounted=False
  try:
   run(['sfdisk',loop],input='label: gpt\n\nsize=32M\nsize=32M\nsize=32M\ntype=linux\n',text=True,check=True,stdout=subprocess.DEVNULL)
   with image.open('r+b') as f:f.seek(65536);f.write(b'OLD-ROCKCHIP-LOADER')
   assert len(json.loads(checked('sfdisk','--json',loop))['partitiontable']['partitions'])==4
   name='mmcblk1';fake=t/'sys';fake.mkdir()
   def convert(s):
    s=str(s)
    return loop+s[len('/dev/mmcblk1'):] if s.startswith('/dev/mmcblk1') else s
   originalopen=os.open;originalfile=builtins.open
   def mappedpath(p):
    s=str(p)
    if s=='/sys/class/block/mmcblk1':return fake
    if s.startswith('/dev/mmcblk1'):return Path(convert(s))
    return Path(s)
   def mappedrun(args,**kw):return run([convert(x) for x in args],**kw)
   def command(*args,**kw):
    args=[convert(x) for x in args]
    if args[0]=='mkfs.fat':args=['qemu-aarch64',str(root/'usr/bin/mkfs.fat'),*args[1:]]
    elif args[0]=='mkfs.exfat':args=['qemu-aarch64','-L',str(root),str(root/'usr/sbin/mkfs.exfat'),*args[1:]]
    result=checked(*args,**kw)
    if args[0]=='partx':(fake/'mmcblk1p1').mkdir(exist_ok=True)
    return result
   plan={'card':{'name':name,'size':512*1024**2//512}}
   with patch.object(m,'Path',mappedpath),patch.object(m,'require_same'),patch.object(m,'status'),patch.object(m,'cmd',command),patch.object(m.subprocess,'run',mappedrun),patch.object(m.os,'open',lambda p,*a,**kw:originalopen(convert(p),*a,**kw)),patch.object(builtins,'open',lambda p,*a,**kw:originalfile(convert(p),*a,**kw)):
    part=m.reset_layout(plan,fs)
   table=json.loads(checked('sfdisk','--json',loop))['partitiontable']
   assert table['label']=='dos' and len(table['partitions'])==1
   assert table['partitions'][0]['size']==512*1024**2//512-2048
   with image.open('rb') as f:
    f.seek(65536);assert f.read(18)==bytes(18)
    f.seek(512*1024**2-512);assert f.read(8)!=b'EFI PART'
   options='rw,noatime,fmask=0000,dmask=0000,'+('utf8=1' if fs=='fat32' else 'iocharset=utf8')
   point=t/'mount';point.mkdir();checked('mount','-t','vfat' if fs=='fat32' else 'exfat','-o',options,loop+'p1',str(point));mounted=True
   checked('sh',str(repo/'system/rootfs/usr/libexec/banana/media-layout'),str(point),str(repo/'system/rootfs/etc/banana/systems.conf'))
   for folder in ('roms/psx','roms/psp','roms/mkxp','bios/psx','bios/dc','saves/nds','states/psx','screenshots','store'):assert (point/folder).is_dir(),folder
   sample=point/'roms/psx/한글 파일 이름.txt';sample.write_text('한글 read-write');checked('sync');assert sample.read_text()=='한글 read-write'
   checked('umount',str(point));mounted=False
   checked('mount','-t','vfat' if fs=='fat32' else 'exfat','-o',options,loop+'p1',str(point));mounted=True;assert sample.read_text()=='한글 read-write'
   print('WHOLE_CARD_FOUR_GPT_PARTITIONS_TO_ONE_FULL_CAPACITY_AND_FOLDERS_PASS',fs,flush=True)
  finally:
   if mounted:subprocess.run(['umount',str(point)],check=True)
   subprocess.run(['losetup','-d',loop],check=True)
