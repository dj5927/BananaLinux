import sys
import json
import pathlib
import subprocess
import shutil
import hashlib
import fcntl
root=pathlib.Path(sys.argv[1])
source=root/'usr/libexec/banana/emmc-install.py'
ns={'__name__':'target_test'}
exec(compile(source.read_text(),str(source),'exec'),ns)
cfg='DEFAULT a\nLABEL a\n APPEND root=PARTLABEL=banana-root-a quiet\nLABEL b\n APPEND root=PARTLABEL=banana-root-b quiet\n'
new=ns['rewrite_extlinux'](cfg,['0','1','2','3'],'b')
assert 'root=PARTUUID=1' in new and 'root=PARTUUID=2' in new and 'DEFAULT b' in new
assert 'banana.slot=b' in new
print('ARM64_TARGET_INSTALLER_IMPORT_AND_BOOT_CONFIG_PASS')
