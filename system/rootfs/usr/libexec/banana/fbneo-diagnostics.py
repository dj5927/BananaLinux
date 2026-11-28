#!/usr/bin/env python3
"""Bounded, read-only FBNeo launch diagnostics. No network or option/clock writes."""
import json
import os
import sys
import time
from pathlib import Path

PROC = Path('/proc')
SYS = Path('/sys')
DATA = Path('/data')
RA_KEYS = set('video_driver video_context_driver video_threaded video_vsync video_swap_interval video_frame_delay video_hard_sync video_hard_sync_frames video_max_swapchain_images video_shader_enable video_refresh_rate audio_driver audio_device audio_latency audio_sync audio_rate_control rewind_enable run_ahead_enabled preemptive_frames_enable preemptive_frames run_ahead_frames run_ahead_secondary_instance game_specific_options core_options_path vrr_runloop_enable video_frame_delay_auto video_monitor_index'.split())
SETTING_KEYS = set('core.fbneo ra_frontend bananafront_lowlat bananafront_cpugov ra_shader ra_border ra_audio_latency'.split())

def read(path, limit=131072):
    try:
        with path.open('rb') as f:
            return f.read(limit).decode('utf-8', 'replace')
    except OSError:
        return ''

def proc_stat(pid):
    text = read(PROC / str(pid) / 'stat', 4096)
    try:
        rest = text[text.rindex(')') + 2:].split()
        return {'pid': pid, 'ppid': int(rest[1]), 'start': int(rest[19]),
                'ticks': int(rest[11]) + int(rest[12])}
    except (ValueError, IndexError):
        return None

def options(rom):
    base = DATA / 'retroarch'
    core = base / 'config/FinalBurn Neo'
    paths = [base/'retroarch.cfg', base/'retroarch-core-options.cfg',
             core/'FinalBurn Neo.opt', core/(rom.stem+'.opt'),
             core/'FinalBurn Neo.cfg', core/(rom.stem+'.cfg'),
             DATA/'banana/settings.conf', DATA/'banana/emulator-defaults.conf']
    result = {}
    for path in paths:
        values = {}
        for line in read(path).splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            key, value = (v.strip() for v in line.split('=', 1))
            if key.startswith('fbneo-') or key in RA_KEYS or key in SETTING_KEYS or (key.startswith('fbneo.') and key[6:] in RA_KEYS | SETTING_KEYS):
                values[key] = value[:512]
        if values:
            result[str(path)] = values
    extra = os.environ.get('BANANAFRONT_OPTIONS', '')
    if extra:
        values = {}
        for line in read(Path(extra)).splitlines():
            if '=' in line:
                key, value = (v.strip() for v in line.split('=', 1))
                if key.startswith('fbneo-'):
                    values[key] = value[:512]
        result['BANANAFRONT_OPTIONS'] = values
    return result

def clocks():
    out = {}
    groups = [(SYS/'devices/system/cpu/cpufreq', 'policy*',
               'scaling_governor scaling_cur_freq cpuinfo_cur_freq scaling_min_freq scaling_max_freq cpuinfo_max_freq affected_cpus'),
              (SYS/'class/devfreq', '*', 'name governor cur_freq min_freq max_freq'),
              (SYS/'class/thermal', 'thermal_zone*', 'type temp'),
              (SYS/'class/thermal', 'cooling_device*', 'type cur_state max_state')]
    for root, pattern, names in groups:
        for folder in sorted(root.glob(pattern))[:32]:
            values = {n: read(folder/n, 512).strip() for n in names.split()}
            if any(values.values()):
                out[str(folder)] = values
    out['cpu_online'] = read(SYS/'devices/system/cpu/online', 512).strip()
    return out

def processes(parent, previous, elapsed):
    allp = {}
    for path in PROC.iterdir():
        if path.name.isdecimal():
            p = proc_stat(int(path.name))
            if p:
                allp[p['pid']] = p
    selected = {parent}
    while True:
        expanded = selected | {p['pid'] for p in allp.values() if p['ppid'] in selected}
        if expanded == selected:
            break
        selected = expanded
    out = []
    ticks = os.sysconf('SC_CLK_TCK')
    for pid in sorted(selected - {os.getpid()}):
        p = allp.get(pid)
        if not p:
            continue
        status = {}
        for line in read(PROC/str(pid)/'status', 8192).splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                if key in {'Name', 'State', 'Threads', 'Cpus_allowed_list'}:
                    status[key] = value.strip()
        maps = []
        for line in read(PROC/str(pid)/'maps', 524288).splitlines():
            if '_libretro.so' in line:
                parts = line.split(None, 5)
                if len(parts) == 6:
                    maps.append(parts[5])
        p['status'] = status
        p['core_paths'] = sorted(set(maps))
        old = previous.get((pid, p['start']))
        if old and elapsed > old[1]:
            p['cpu_percent_of_one_core'] = round((p['ticks']-old[0])/ticks/(elapsed-old[1])*100, 1)
        previous[(pid, p['start'])] = (p['ticks'], elapsed)
        out.append(p)
    return out

def run(parent, rom, delays=(1, 5, 10, 20, 30)):
    identity = proc_stat(parent)
    if not identity:
        return
    folder = DATA/'banana/logs'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/'fbneo-diagnostics.log'
    if path.is_symlink():
        return
    if path.exists():
        path.replace(folder/'fbneo-diagnostics.previous.log')
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', buffering=1) as log:
        def emit(kind, **values):
            log.write(json.dumps({'type': kind, **values}, ensure_ascii=True)+'\n')
        emit('context', game=rom.name, parent=parent, version=read(Path('/etc/banana/version'), 128).strip(),
             options=options(rom), note='Configured overrides; absent keys use core defaults. No settings modified.')
        previous = {}
        begin = time.monotonic()
        for delay in delays:
            while True:
                live = proc_stat(parent)
                if not live or live['start'] != identity['start']:
                    emit('parent_exited')
                    return
                remaining = begin+delay-time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(.25, remaining))
            elapsed = time.monotonic()-begin
            emit('runtime', elapsed=round(elapsed, 3), clocks=clocks(),
                 processes=processes(parent, previous, elapsed))
        emit('complete')

def main():
    # Do not keep the emulator's DRM lease, command FIFO or other inherited fds alive.
    os.closerange(3, 1048576)
    try:
        run(int(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, IndexError):
        pass  # Diagnostics must never prevent game launch.
if __name__ == '__main__':
    main()
