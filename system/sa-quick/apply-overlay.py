#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil,sys
root=Path(sys.argv[1]); here=Path(__file__).resolve().parent
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
todo=[]
for a in json.loads((here/"baseline.json").read_text()):
    for f in a["files"]:
        src=here/"overlay"/f["path"];dst=root/f["path"]
        assert sha(src)==f["sha256"],src
        if f["base_sha256"] is None: assert not dst.exists(),dst
        else: assert sha(dst)==f["base_sha256"],dst
        todo.append((src,dst))
for src,dst in todo:
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
print("SOURCE_OVERLAY_APPLIED",len(todo))
