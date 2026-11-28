#!/usr/bin/env python3
"""Whole removable-SD reset. No caller-supplied target path is accepted."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

RUN=Path('/run/banana')
MEDIA=Path('/run/sd2')
TOOLS=Path('/usr/libexec/banana')
PLAN=RUN/'sd-format-plan.json'
TOKEN=RUN/'sd-format-token'

def cmd(*args,**kw):
    return subprocess.check_output(args,text=True,**kw).strip()

def status(value):
    RUN.mkdir(parents=True,exist_ok=True)
    p=RUN/'sd-format-status.new';p.write_text(value+'\n');p.replace(RUN/'sd-format-status')

def device(major_minor):
    return Path('/sys/dev/block/'+major_minor).resolve().name

def belongs(name,disk):
    return name==disk or re.fullmatch(re.escape(disk)+r'p[0-9]+',name) is not None

def mounts():
    # mountinfo encodes whitespace; unsupported paths are rejected, never shell-expanded.
    return [ln.split() for ln in Path('/proc/self/mountinfo').read_text().splitlines()]

def identity(disk):
    p=Path('/sys/class/block/'+disk)
    return dict(name=disk,cid=(p/'device/cid').read_text().strip(),
                dev=(p/'dev').read_text().strip(),size=int((p/'size').read_text()),
                seq=(p/'diskseq').read_text().strip())

def probe():
    if os.geteuid()!=0:raise RuntimeError('root is required')
    if Path('/etc/banana/board').read_text().strip() not in ('rgds','rgds-plus'):
        raise RuntimeError('unsupported handheld')
    root=(RUN/'disk').read_text().strip()
    if not re.fullmatch(r'/dev/mmcblk[0-9]+',root):raise RuntimeError('unknown system disk')
    rootname=root[5:]
    if Path('/sys/class/block/'+rootname+'/device/type').read_text().strip()!='MMC':
        raise RuntimeError('Boot from internal eMMC without the boot SD, then insert the SD to format.')
    if not Path('/data/banana/emmc-install.conf').is_file():raise RuntimeError('eMMC media setup is unavailable')
    mi=mounts()
    roots=[device(r[2]) for r in mi if r[4]=='/']
    if not roots or roots[-1] not in (rootname+'p2',rootname+'p3'):raise RuntimeError('system root does not match eMMC')
    data=[device(r[2]) for r in mi if r[4]=='/data']
    if data!=[rootname+'p4']:raise RuntimeError('internal settings mount does not match eMMC')
    cards=[p for p in Path('/sys/class/block').glob('mmcblk[0-9]*')
           if re.fullmatch(r'mmcblk[0-9]+',p.name) and (p/'device/type').is_file()
           and (p/'device/type').read_text().strip()=='SD']
    if len(cards)!=1:raise RuntimeError('Insert exactly one SD card to format. Remove any other SD card.')
    card=cards[0];name=card.name
    if name==rootname:raise RuntimeError('system disk cannot be formatted')
    if (card/'ro').read_text().strip()!='0':raise RuntimeError('SD card is read-only')
    ident=identity(name)
    if not ident['cid'] or not ident['seq']:raise RuntimeError('SD identity is unavailable')
    if not 64*1024**2<=ident['size']*512<2*1024**4:raise RuntimeError('SD capacity must be between 64 MiB and 2 TiB')
    for p in (card,*card.glob(name+'p*')):
        if (p/'holders').is_dir() and list((p/'holders').iterdir()):raise RuntimeError('SD device is busy')
    allowed={'/run/sd2'}
    for pair in media_map():allowed.add('/data/'+pair.split(':')[1])
    for r in mi:
        if belongs(device(r[2]),name) and r[4] not in allowed:
            raise RuntimeError('SD has another mounted volume; unmount it first')
    try:swaps=Path('/proc/swaps').read_text().splitlines()[1:]
    except FileNotFoundError:swaps=[]
    for row in swaps:
        st=os.stat(row.split()[0]);dev=st.st_rdev if st.st_rdev else st.st_dev
        if belongs(device(str(os.major(dev))+':'+str(os.minor(dev))),name):raise RuntimeError('SD swap is active')
    if subprocess.run(['pidof','ksmbd.mountd'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
        raise RuntimeError('Turn off file sharing before formatting the SD.')
    for tool in ('sfdisk','partx','mkfs.fat','mkfs.exfat','mount','umount','blockdev','sync'):
        if shutil.which(tool) is None:raise RuntimeError('missing tool: '+tool)
    return dict(card=ident,root=identity(rootname))

def media_map():
    # Keep the exact native-engine bind list shared with emmc-media.
    for ln in (TOOLS/'emmc-media').read_text().splitlines():
        if ln.startswith("MAP='"):return ln[5:-1].split()
    raise RuntimeError('media bindings are unavailable')

def require_same(plan):
    if probe()!=plan:raise RuntimeError('SD or system disk changed. Cancel and check the card again.')

def reset_layout(plan,fs):
    """Destructive core, called only after identity checks and strict unmount."""
    name=plan['card']['name'];target='/dev/'+name;size=plan['card']['size']*512
    require_same(plan)
    status('writing 10%')
    # Clear MBR, primary/backup GPT and the old Rockchip loader. This is a quick
    # repartition/format, not a secure overwrite of every previous data sector.
    fd=os.open(target,os.O_RDWR|os.O_EXCL)
    try:
        zero=bytes(1024**2)
        for offset in (*range(0,16*1024**2,1024**2),size-1024**2):
            os.lseek(fd,offset,os.SEEK_SET)
            if os.write(fd,zero)!=len(zero):raise RuntimeError('short SD metadata write')
        os.fsync(fd)
    finally:os.close(fd)
    require_same(plan)
    kind='c' if fs=='fat32' else '7'
    layout='label: dos\nunit: sectors\n\nstart=2048, size={}, type={}\n'.format(plan['card']['size']-2048,kind)
    subprocess.run(['sfdisk','--wipe','always','--wipe-partitions','always',target],input=layout,text=True,check=True,stdout=subprocess.DEVNULL)
    cmd('partx','--update',target)
    part=target+'p1'
    for _ in range(30):
        children=list(Path('/sys/class/block/'+name).glob(name+'p*'))
        if [p.name for p in children]==[name+'p1'] and Path(part).is_block_device():break
        time.sleep(.2)
    else:raise RuntimeError('old SD partitions did not disappear')
    table=json.loads(cmd('sfdisk','--json',target))['partitiontable']
    parts=table['partitions']
    if table['label']!='dos' or len(parts)!=1 or parts[0]['start']!=2048 or parts[0]['size']!=plan['card']['size']-2048:
        raise RuntimeError('SD partition table readback mismatch')
    require_same(plan)
    status('writing 45%')
    if fs=='fat32':cmd('mkfs.fat','-F','32','-n','BANANA-SD',part)
    else:cmd('mkfs.exfat','-L','BANANA-SD',part)
    cmd('blockdev','--flushbufs',target)
    with open(part,'rb',buffering=0) as f:b=f.read(512)
    if (fs=='fat32' and b[82:90]!=b'FAT32   ') or (fs=='exfat' and b[3:11]!=b'EXFAT   '):
        raise RuntimeError('SD filesystem readback mismatch')
    return part

def format_card(plan,fs):
    require_same(plan)
    # Never use lazy/forced unmount: an open game/save/file must block erasure.
    cmd(str(TOOLS/'emmc-media'),'detach-strict')
    mi=mounts();name=plan['card']['name']
    for r in sorted(mi,key=lambda r:len(r[4]),reverse=True):
        if belongs(device(r[2]),name):cmd('umount',r[4])
    if any(belongs(device(r[2]),name) for r in mounts()):raise RuntimeError('SD is still mounted')
    part=reset_layout(plan,fs)
    require_same(plan)
    status('writing 75%')
    MEDIA.mkdir(parents=True,exist_ok=True)
    options='rw,noatime,fmask=0000,dmask=0000,'+('utf8=1' if fs=='fat32' else 'iocharset=utf8')
    cmd('mount','-t','vfat' if fs=='fat32' else 'exfat','-o',options,part,str(MEDIA))
    cmd(str(TOOLS/'media-layout'),str(MEDIA),'/etc/banana/systems.conf')
    check=MEDIA/'.banana-format-check';check.write_text('SD format write/read check\n');cmd('sync')
    if check.read_text()!='SD format write/read check\n':raise RuntimeError('SD write/read verification failed')
    check.unlink();cmd('sync')
    cmd(str(TOOLS/'emmc-media'),'attach')
    status('done '+fs)

def main():
    RUN.mkdir(parents=True,exist_ok=True)
    with open(RUN/'update-apply.lock','a') as update,open(RUN/'sd-media.lock','a') as media:
        fcntl.flock(update,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fcntl.flock(media,fcntl.LOCK_EX|fcntl.LOCK_NB)
        args=sys.argv[1:]
        if args==['probe']:
            TOKEN.unlink(missing_ok=True);PLAN.unlink(missing_ok=True)
            p=probe();token=uuid.uuid4().hex
            PLAN.write_text(json.dumps(dict(token=token,plan=p)))
            TOKEN.write_text(token+'\n')
            status('ready /dev/{} {:.1f} GiB'.format(p['card']['name'],p['card']['size']*512/1024**3))
        elif len(args)==4 and args[0]=='format' and args[1] in ('fat32','exfat') and args[2]=='ERASE-ENTIRE-SD':
            saved=json.loads(PLAN.read_text())
            if args[3]!=saved['token']:raise RuntimeError('SD confirmation expired; check the card again')
            PLAN.unlink();TOKEN.unlink(missing_ok=True)
            (RUN/'awake.pid').write_text(str(os.getpid()))
            try:format_card(saved['plan'],args[1])
            finally:
                if (RUN/'awake.pid').read_text().strip()==str(os.getpid()):(RUN/'awake.pid').unlink()
        else:raise RuntimeError('explicit whole-card confirmation is required')

if __name__=='__main__':
    try:main()
    except BlockingIOError:
        # A concurrent probe must not overwrite an active formatter's status.
        if not (RUN/'sd-format-status').exists():status('failed: Another storage operation is busy. Try again shortly.')
        print('SD or update operation is busy; try again shortly',file=sys.stderr);sys.exit(1)
    except Exception as e:
        status('failed: '+str(e));print(str(e),file=sys.stderr);sys.exit(1)
