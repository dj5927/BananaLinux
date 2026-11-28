#!/usr/bin/env python3
"""Install the running SD system into eMMC. CLI never accepts a target disk."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

RUN = Path('/run/banana')
DATA = Path('/data')
WORK = Path('/run/banana/emmc-target')

def cmd(*args, **kw):
    return subprocess.check_output(args, text=True, **kw).strip()

def status(text):
    RUN.mkdir(parents=True, exist_ok=True)
    temp = RUN / 'emmc-status.new'
    temp.write_text(text + '\n')
    temp.replace(RUN / 'emmc-status')

def uuid():
    return Path('/proc/sys/kernel/random/uuid').read_text().strip()

def sha(path, size=None):
    h = hashlib.sha256()
    with open(path, 'rb', buffering=0) as f:
        while size is None or size > 0:
            b = f.read(min(size, 1048576) if size is not None else 1048576)
            if not b:
                if size: raise RuntimeError('short read: ' + str(path))
                break
            h.update(b)
            if size is not None: size -= len(b)
    return h.hexdigest()

def table(disk):
    return json.loads(cmd('sfdisk', '--json', disk))['partitiontable']

def partition_plan(src, capacity):
    parts = src['partitions']
    if src.get('label') != 'gpt' or src.get('sectorsize', 512) != 512 or len(parts) != 4:
        raise RuntimeError('unsupported source partition table')
    if [p['start'] for p in parts[:3]] != [32768, 163840, 688128]:
        raise RuntimeError('unsupported source partition offsets')
    if [p['size'] for p in parts[:3]] != [131072, 524288, 524288]:
        raise RuntimeError('unsupported source partition sizes')
    start = parts[2]['start'] + parts[2]['size']
    if capacity - start * 512 < 2 * 1024**3:
        raise RuntimeError('eMMC needs at least 2 GiB for settings and runtimes')
    guids = [uuid() for _ in range(4)]
    lines = ['label: gpt', 'label-id: ' + uuid(), 'unit: sectors', '']
    for i, name in enumerate(('boot', 'banana-root-a', 'banana-root-b')):
        p = parts[i]
        lines.append('start={start}, size={size}, type={type}, uuid={u}, name="{n}"'.format(**p, u=guids[i], n=name))
    lines.append('start={}, type=EBD0A0A2-B9E5-4433-87C0-68B6B72699C7, uuid={}, name="banana-data"'.format(start, guids[3]))
    return '\n'.join(lines) + '\n', guids

def probe():
    if os.geteuid() != 0: raise RuntimeError('root is required')
    board = Path('/etc/banana/board').read_text().strip()
    if board not in ('rgds', 'rgds-plus'): raise RuntimeError('unsupported handheld')
    source = (RUN / 'disk').read_text().strip()
    if not source.startswith('/dev/mmcblk') or not source[11:].isdigit():
        raise RuntimeError('boot from a BananaOS SD card first')
    if Path('/sys/class/block/' + source[5:] + '/device/type').read_text().strip() != 'SD':
        raise RuntimeError('installation must run from SD')
    mounts=[ln.split() for ln in Path('/proc/mounts').read_text().splitlines()]
    if not any(row[0]==source+'p4' and row[1]=='/data' and row[2] in ('exfat','vfat') for row in mounts):
        raise RuntimeError('source SD data partition is unavailable')
    if not any(row[0]==source+'p1' and row[1]=='/boot' for row in mounts):
        raise RuntimeError('source SD boot partition is unavailable')
    root=[ln.split()[2] for ln in Path('/proc/self/mountinfo').read_text().splitlines() if ln.split()[4]=='/'][-1]
    if Path('/sys/dev/block/'+root).resolve().name not in (source[5:]+'p2',source[5:]+'p3'):
        raise RuntimeError('running root does not match source SD')
    targets = [p for p in Path('/sys/class/block').glob('mmcblk[0-9]*')
               if p.name[6:].isdigit() and (p/'device/type').is_file()
               and (p/'device/type').read_text().strip() == 'MMC']
    if len(targets) != 1: raise RuntimeError('exactly one internal eMMC is required')
    target = '/dev/' + targets[0].name
    if target == source: raise RuntimeError('source equals target')
    if (targets[0]/'ro').read_text().strip() != '0': raise RuntimeError('eMMC is read-only')
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        node=Path('/sys/dev/block/'+line.split()[2]).resolve().name
        if node == targets[0].name or node.startswith(targets[0].name+'p'):
            raise RuntimeError('eMMC is mounted; unmount it first')
    for ln in Path('/proc/mounts').read_text().splitlines():
        if ln.split()[0].startswith(target): raise RuntimeError('eMMC is mounted; unmount it first')
    if any(ln.split()[0].startswith(target) for ln in Path('/proc/swaps').read_text().splitlines()[1:]):
        raise RuntimeError('eMMC swap is in use')
    for p in [targets[0], *targets[0].glob(targets[0].name + 'p*')]:
        holders = p/'holders'
        if holders.is_dir() and list(holders.iterdir()): raise RuntimeError('eMMC is in use')
    capacity = int((targets[0]/'size').read_text()) * 512
    layout, guids = partition_plan(table(source), capacity)
    slot = (RUN / 'slot').read_text().strip()
    if slot not in ('a', 'b'): raise RuntimeError('unknown running slot')
    if not Path('/boot/' + slot + '/Image').is_file(): raise RuntimeError('boot files are unavailable')
    for tool in ('dd','sfdisk','partx','mkfs.exfat','mount','umount','blockdev','sync'):
        if shutil.which(tool) is None: raise RuntimeError('missing tool: ' + tool)
    # Backups + copied settings/runtime need space on the source and target.
    settings = [p for p in DATA.iterdir() if p.name not in ('roms','bios','saves','states','screenshots','store','lost+found')]
    needed = sum(p.stat().st_size for d in settings for p in ([d] if d.is_file() else d.rglob('*')) if p.is_file())
    if capacity - 620756992 < needed + 512*1024**2: raise RuntimeError('settings and runtime do not fit eMMC')
    if shutil.disk_usage(DATA).free < 32*1024**2: raise RuntimeError('SD needs 32 MiB for boot backups')
    return dict(source=source,target=target,capacity=capacity,layout=layout,guids=guids,slot=slot,settings=settings)

def rewrite_extlinux(text, guids, slot):
    lines=[]; label=None
    for line in text.splitlines():
        if line.startswith('DEFAULT '): line='DEFAULT ' + slot
        if line.startswith('LABEL '): label=line.split()[1]
        if line.lstrip().startswith('APPEND '):
            if label not in ('a','b'): raise RuntimeError('unknown extlinux slot')
            tokens=line.split()
            if sum(x.startswith('root=') for x in tokens) != 1: raise RuntimeError('invalid root arguments')
            tokens=[x for x in tokens if not x.startswith('banana.slot=')]
            tokens=[('root=PARTUUID='+guids[1 if label=='a' else 2]) if x.startswith('root=') else x for x in tokens]
            line='  ' + ' '.join(tokens) + ' banana.slot=' + label
        lines.append(line)
    if not all(any(x.startswith('LABEL '+s) for x in lines) for s in ('a','b')):
        raise RuntimeError('missing extlinux slots')
    return '\n'.join(lines)+'\n'

def install(p):
    source,target=p['source'],p['target']
    backup=DATA/'banana/backups'/('emmc-'+time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True)
    (backup/'WARNING.txt').write_text('Boot and GPT recovery metadata only. This is NOT a full backup of the erased eMMC.\n')
    cmd('dd','if='+target,'of='+str(backup/'first-16MiB.bin'),'bs=1M','count=16','conv=fsync',stderr=subprocess.DEVNULL)
    with open(target,'rb',buffering=0) as f:
        f.seek(p['capacity']-34*512)
        (backup/'last-34-sectors.bin').write_bytes(f.read(34*512))
    dump=subprocess.run(['sfdisk','--dump',target],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (backup/'partition-table.txt').write_text(dump.stdout)
    cmd('sync')
    # This is the first destructive operation. Target was discovered, never supplied by CLI.
    status('writing 2%')
    subprocess.run(['sfdisk','--wipe','always','--wipe-partitions','always',target],input=p['layout'],text=True,check=True,stdout=subprocess.DEVNULL)
    cmd('partx','--update',target)
    for i in range(20):
        if Path(target+'p4').exists(): break
        time.sleep(.2)
    if not Path(target+'p4').exists(): raise RuntimeError('new eMMC partitions did not appear')
    # Rockchip loader in the user area; hardware boot partitions are never modified.
    cmd('dd','if='+source,'of='+target,'bs=512','skip=64','seek=64','count=32704','conv=fsync,notrunc',stderr=subprocess.DEVNULL)
    for i in (1,2,3):
        status('writing {}%'.format(5+i*20))
        cmd('dd','if='+source+'p'+str(i),'of='+target+'p'+str(i),'bs=4M','conv=fsync,notrunc',stderr=subprocess.DEVNULL)
        cmd('blockdev','--flushbufs',target+'p'+str(i))
        size=int(cmd('blockdev','--getsize64',source+'p'+str(i)))
        if sha(source+'p'+str(i),size)!=sha(target+'p'+str(i),size): raise RuntimeError('eMMC readback mismatch')
    cmd('mkfs.exfat','-L','BANANA-INT',target+'p4')
    WORK.mkdir(parents=True,exist_ok=True)
    try:
        cmd('mount','-t','exfat',target+'p4',str(WORK))
        status('writing 80%')
        for item in p['settings']:
            if item.is_dir(): shutil.copytree(item,WORK/item.name,dirs_exist_ok=True)
            elif item.is_file(): shutil.copy2(item,WORK/item.name)
        (WORK/'banana').mkdir(exist_ok=True)
        (WORK/'banana/emmc-install.conf').write_text('version=1\nmedia=sd\n')
        # Runtime settings stay internal. User game folders are read from SD at boot.
        cmd('sync')
    finally:
        subprocess.run(['umount',str(WORK)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        cmd('mount','-t','vfat',target+'p1',str(WORK))
        conf=WORK/'extlinux/extlinux.conf'
        text=rewrite_extlinux(conf.read_text(),p['guids'],p['slot'])
        conf.write_text(text)
        cmd('sync')
        if conf.read_text()!=text: raise RuntimeError('boot configuration readback failed')
    finally:
        subprocess.run(['umount',str(WORK)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    # Loader readback independently from the partition table.
    cmd('blockdev','--flushbufs',target)
    def boot_hash(disk):
        with open(disk,'rb',buffering=0) as f:
            f.seek(32768); return hashlib.sha256(f.read(16777216-32768)).hexdigest()
    if boot_hash(source)!=boot_hash(target): raise RuntimeError('bootloader readback mismatch')
    cmd('sync')
    (backup/'INSTALL-COMPLETE.txt').write_text('Target: '+target+'\nPartition UUIDs: '+','.join(p['guids'])+'\n')
    status('done eMMC')

def main():
    import fcntl
    RUN.mkdir(parents=True,exist_ok=True)
    with open(RUN/'update-apply.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        p=probe()
        if sys.argv[1:] == ['probe']:
            status('ready '+p['target']+' '+str(p['capacity']//(1024**3))+' GiB')
        elif sys.argv[1:] == ['install','ERASE-INTERNAL-EMMC']:
            (RUN/'awake.pid').write_text(str(os.getpid()))
            try: install(p)
            finally:
                if (RUN/'awake.pid').read_text().strip()==str(os.getpid()): (RUN/'awake.pid').unlink()
        else: raise RuntimeError('explicit erase confirmation is required')

if __name__ == '__main__':
    try: main()
    except Exception as e:
        status('failed: '+str(e)); print(str(e),file=sys.stderr); sys.exit(1)
