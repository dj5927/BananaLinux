import importlib.util
from pathlib import Path
import struct
import tempfile
import uuid
import zlib
tool=Path(__file__).resolve().parents[2]/'tools/image-protect-boot.py'
spec=importlib.util.spec_from_file_location('protect',tool);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as t:
 p=Path(t)/'test.img';size=32*1024**2;sectors=size//512
 e=bytearray(128*128);e[:16]=m.BASIC;e[16:32]=uuid.uuid4().bytes_le
 struct.pack_into('<QQQ',e,32,32768,32895,4);e[56:64]='boot'.encode('utf-16le')
 guid=uuid.uuid4().bytes_le
 def hdr(cur,alt,start):
  h=bytearray(512);h[:8]=b'EFI PART';struct.pack_into('<IIIIQQQQ16sQIII',h,8,0x10000,92,0,0,cur,alt,34,sectors-34,guid,start,128,128,zlib.crc32(e));struct.pack_into('<I',h,16,zlib.crc32(h[:92]));return h
 with p.open('wb') as f:f.truncate(size)
 with p.open('r+b') as f:
  f.seek(510);f.write(b'\x55\xaa');f.seek(512);f.write(hdr(1,sectors-1,2));f.seek(1024);f.write(e)
  f.seek((sectors-33)*512);f.write(e);f.seek((sectors-1)*512);f.write(hdr(sectors-1,1,sectors-33))
  f.seek(32768);f.write(b'ROCKCHIP-LOADER-FIXTURE')
  f.seek(16777216);f.write(b'FAT-BOOT-FILES-FIXTURE')
 before=p.read_bytes();m.protect(p);after=p.read_bytes()
 assert before[:512]==after[:512]
 assert before[32768:(sectors-33)*512]==after[32768:(sectors-33)*512]
 with p.open('rb') as f:
  for lba in (1,sectors-1):
   h,e,_,_=m.header(f,lba);assert e[:16]==m.ESP
   assert struct.unpack_from('<Q',e,48)[0]==(1<<63)|4
 # The same predicate used by Rufus's post-DD remount path now excludes boot.
 assert before[1024:1040]!=m.ESP and after[1024:1040]==m.ESP
 m.protect(p);assert p.read_bytes()==after
 print('GPT_BOTH_CRCS_ESP_NO_AUTOMOUNT_LOADER_PAYLOAD_IDEMPOTENCE_PASS')
