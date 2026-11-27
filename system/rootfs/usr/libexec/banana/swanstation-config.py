#!/usr/bin/python3
"""Apply Banana's SwanStation performance defaults without touching other cores."""
import os
import re
import sys
from pathlib import Path

def read_config(path):
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"')
    return values

def update_config(path, changes):
    old = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    lines = [line for line in old.splitlines()
             if not ("=" in line and not line.lstrip().startswith("#")
                     and line.split("=",1)[0].strip() in changes)]
    lines += [f'{key} = "{value}"' for key,value in changes.items() if value is not None]
    new = "\n".join(lines)+"\n"
    if new == old:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+".banana-new")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(new); f.flush(); os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)

def prepare(root, schema, native_menu):
    data = root/"banana"
    ra = root/"retroarch/config/SwanStation"
    opt, cfg = ra/"SwanStation.opt", ra/"SwanStation.cfg"
    selected = read_config(data/"swanstation.conf")
    core, front = {}, {}
    for row in schema.read_text(encoding="utf-8").splitlines():
        if not row.strip(): continue
        key, default, label, help_, allowed, names = row.split("\t")
        val = selected.get(key,default)
        if val not in allowed.split("|"):
            val = default
        (core if key.startswith("swanstation_") else front)[key] = val
    # Back up existing user choices once. Keep all unmanaged options.
    for path in (opt,cfg):
        backup = path.with_suffix(path.suffix+".pre-banana-v25")
        if path.exists() and not backup.exists():
            backup.write_bytes(path.read_bytes())
    update_config(opt,core)
    # Match the installed GLES/KMS frontend; no Vulkan in this firmware.
    front["video_driver"]="gl"
    # RA per-core overrides load after appendconfig. Don't let the menu's
    # own hotkey intercept F+X. The UI owns it only with a working panel.
    hot={"input_menu_toggle_btn":"31","input_menu_toggle_axis":"nul",
         "input_menu_toggle":"nul","input_menu_toggle_gamepad_combo":"0"}
    if native_menu:
        front.update(hot)
    else:
        old=read_config(cfg)
        backup=read_config(cfg.with_suffix(cfg.suffix+".pre-banana-v25"))
        for key,val in hot.items():
            if old.get(key)==val:
                front[key]=backup.get(key)
    front.update({"video_monitor_index":None,"stdin_cmd_enable":None})
    update_config(cfg,front)
    print("SwanStation: "+str(core["swanstation_GPU_Renderer"])+" "
          +str(core["swanstation_GPU_ResolutionScale"])+"x; buffers="+front["video_max_swapchain_images"],
          file=sys.stderr)

if __name__=="__main__":
    prepare(Path("/data"),Path("/usr/share/banana/swanstation-options.tsv"),
            os.environ.get("BANANA_SWAN_MENU")=="1" and bool(os.environ.get("BANANA_DRM_LEASE_FD")))
