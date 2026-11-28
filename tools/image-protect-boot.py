#!/usr/bin/env python3
"""Mark the boot FAT partition ESP/no-automount; never change loader or payload."""
import hashlib
from pathlib import Path
import struct
import sys
import uuid
import zlib

ESP=uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b').bytes_le
BASIC=uuid.UUID('ebd0a0a2-b9e5-4433-87c0-68b6b72699c7').bytes_le
def header(f,lba):
 f.seek(lba*512);b=bytearray(f.read(512))
 assert b[:8]==b'EFI PART'
 size=struct.unpack_from('<I',b,12)[0];crc=struct.unpack_from('<I',b,16)[0]
 assert 92<=size<=512
 test=bytearray(b[:size]);struct.pack_into('<I',test,16,0);assert zlib.crc32(test)==crc
 start,n,es,ec=struct.unpack_from('<QIII',b,72)
 assert es>=128 and n*es<=32768
 f.seek(start*512);entries=bytearray(f.read(n*es));assert zlib.crc32(entries)==ec
 return b,entries,start,es
def protect(path):
 path=Path(path)
 assert path.is_file() and path.name.lower().endswith(('.img','.img.part')), 'regular uncompressed image required'
 with path.open('r+b') as f:
  a,e,start,es=header(f,1);backup=struct.unpack_from('<Q',a,32)[0]
  b,be,bst,bes=header(f,backup);assert e==be and es==bes
  assert e[:16] in (BASIC,ESP)
  assert struct.unpack_from('<Q',e,32)[0]==32768
  original=bytes(e);flags=struct.unpack_from('<Q',e,48)[0]
  e[:16]=ESP;struct.pack_into('<Q',e,48,flags|(1<<63))
  # Every byte other than partition zero's type and attributes is preserved.
  assert e[16:48]==original[16:48] and e[56:]==original[56:]
  for h,pos in ((a,start),(b,bst)):
   f.seek(pos*512);f.write(e)
   struct.pack_into('<I',h,88,zlib.crc32(e));struct.pack_into('<I',h,16,0)
   size=struct.unpack_from('<I',h,12)[0];struct.pack_into('<I',h,16,zlib.crc32(h[:size]))
   lba=struct.unpack_from('<Q',h,24)[0];f.seek(lba*512);f.write(h)
  f.flush()
 with path.open('rb') as f:
  for lba in (1,backup):
   h,entries,_,_=header(f,lba);assert entries[:16]==ESP
   assert struct.unpack_from('<Q',entries,48)[0]&(1<<63)
 return {'boot_partition_type':'EFI System','no_automount':True,'offset':32768*512}
if __name__=='__main__':
 for p in sys.argv[1:]:print(p,protect(p))
