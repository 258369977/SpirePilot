"""Small JSON protocol for the WinUI desktop. Keys travel over stdin, never argv."""
import ctypes
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request
from experience import ExperienceStore

ROOT = pathlib.Path(__file__).resolve().parent
BILLING_CONFIG_KEYS = tuple(
    role + '_' + suffix
    for role in ('planner', 'combat')
    for suffix in ('input_price_per_million', 'cached_input_price_per_million',
                   'output_price_per_million'))

def read(path, default=None):
    try: return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError): return default

def process_identity(pid):
    from ctypes import wintypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    h = k.OpenProcess(0x1000, False, pid)
    if not h: return None
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259: return None
        values = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(h, *[ctypes.byref(v) for v in values]): return None
        return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime
    finally: k.CloseHandle(h)

def run_path(name):
    # Only allow directories owned by this controller's runs folder.
    root = (ROOT / 'runs').resolve()
    p = (root / name).resolve()
    if p.parent != root: raise ValueError('Invalid run directory')
    return p

def tail(path, limit=16000):
    try:
        with path.open('rb') as f:
            f.seek(0, 2); f.seek(max(0, f.tell()-limit))
            return f.read().decode('utf-8', errors='replace')
    except OSError: return ''

def active():
    data = read(ROOT / 'desktop_process.json', {})
    running = bool(data.get('pid') and data.get('identity') and process_identity(data['pid']) == data['identity'])
    return data, running

def model_environment(config, payload, command):
    env = os.environ.copy()
    for role in (('planner',) if command == 'review' else ('planner', 'combat')):
        value = payload.get(role + '_key', '').strip()
        if value: env['SPIRE_' + role.upper() + '_KEY'] = value
        elif not env.get('SPIRE_' + role.upper() + '_KEY') and not env.get(config[role + '_key_env']):
            raise ValueError(role + ' 模型缺少密钥。')
    return env

def dispatch(command, payload):
    config_path = ROOT / 'config.json'
    config = read(config_path if config_path.exists() else ROOT / 'config.example.json', {})
    config.setdefault('planner_reasoning_effort', 'low')
    if command == 'config': return config
    if command == 'save-config':
        for k in ('planner_model', 'combat_model', 'memory_scope'):
            value = payload.get(k)
            if not isinstance(value, str) or not value.strip(): raise ValueError('Empty '+k)
            config[k] = value.strip()
        config['cross_run_memory'] = bool(payload.get('cross_run_memory', True))
        effort = payload.get('planner_reasoning_effort', config['planner_reasoning_effort'])
        if effort not in ('low', 'medium', 'high'):
            raise ValueError('不支持的规划模型思考强度。')
        config['planner_reasoning_effort'] = effort
        for key in BILLING_CONFIG_KEYS:
            config.pop(key, None)
        for role in ('planner', 'combat'):
            if role + '_url' not in payload: continue
            from urllib.parse import urlsplit
            url = payload[role + '_url'].strip()
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('请填写不含密钥的完整 API URL。')
            protocol = payload.get(role + '_protocol', 'chat_schema')
            if protocol not in ('chat_schema', 'chat_json', 'decisions') or (role == 'planner' and protocol == 'decisions'):
                raise ValueError('不支持的接口协议。')
            if parsed.hostname.lower() == 'openrouter.ai':
                path = parsed.path.rstrip('/')
                if protocol == 'decisions' and path != '/api/alpha/decisions':
                    raise ValueError('OpenRouter Decisions 接口必须使用 https://openrouter.ai/api/alpha/decisions。')
                if protocol != 'decisions' and path != '/api/v1/chat/completions':
                    raise ValueError('OpenRouter 聊天接口必须使用 https://openrouter.ai/api/v1/chat/completions。')
            config[role + '_key_env'] = 'SPIRE_' + role.upper() + '_KEY'
            config.update({role + '_url': url, role + '_provider': payload.get(role + '_provider', '自定义'), role + '_protocol': protocol})
        # Never persist credentials.
        temp = ROOT / 'config.desktop.tmp'
        temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(ROOT / 'config.json')
        return {'saved': True}
    if command in ('start', 'review'):
        _, running = active()
        if running or (ROOT / 'controller.lock').exists():
            raise ValueError('控制器正在运行，或存在未清理的锁；请先停止并检查。')
        # Also guard the legacy controller from concurrent gameplay.
        legacy = ROOT.parent / 'controller.pid'
        if command == 'start' and legacy.exists():
            try: old_pid = int(legacy.read_text().strip())
            except ValueError: old_pid = 0
            if old_pid and process_identity(old_pid): raise ValueError('旧单模型进程仍在运行，请先停止旧控制器。')
        name = payload.get('run')
        directory = run_path(name) if name else run_path(time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid()))
        if name and not (directory / 'memory.json').exists(): raise ValueError('找不到所选对局记忆。')
        if command == 'review' and not (directory / 'result.json').exists(): raise ValueError('此局没有终局结果，暂不能复盘。')
        if command == 'start':
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(config['game_url'], timeout=4) as r: state = json.load(r)
            if state.get('state_type') == 'game_over': raise ValueError('游戏停在结算界面，请先在游戏中开始新局。')
            if state.get('player') and config.get('require_full_deck') and 'deck' not in state['player']:
                raise ValueError('Mod 未提供完整牌组，请安装支持 player.deck 的版本。')
            if name and (directory / 'result.json').exists(): raise ValueError('这份记录已结束，请为新局创建新记录。')
        env = model_environment(config, payload, command)
        directory.mkdir(parents=True, exist_ok=True)
        (ROOT / 'STOP').unlink(missing_ok=True)
        si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
        args = [sys.executable, '-u', str(ROOT / 'hybrid_player.py'), '--run-dir', str(directory)]
        if command == 'review': args += ['--review-only']
        with (directory / 'stdout.log').open('ab') as stdout, (directory / 'stderr.log').open('ab') as stderr:
            p = subprocess.Popen(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 startupinfo=si, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        identity = process_identity(p.pid)
        record = {'pid': p.pid, 'identity': identity, 'run': directory.name, 'mode': command}
        (ROOT / 'desktop_process.json').write_text(json.dumps(record), encoding='utf-8')
        return record
    if command == 'stop':
        (ROOT / 'STOP').write_text('Desktop stop requested', encoding='utf-8')
        return {'stop_requested': True}
    if command == 'status':
        proc, running = active()
        name = payload.get('run') or proc.get('run')
        d = run_path(name) if name else None
        memory = read(d/'memory.json', {}) if d else {}
        return {'process': proc, 'running': running, 'stop_requested': (ROOT/'STOP').exists(),
                'state': read(d/'latest_state.json', {}) if d else {},
                'memory': memory,
                'review_status': read(d/'review_status.json', {}) if d else {},
                'log': (tail(d/'stdout.log')+'\n'+tail(d/'stderr.log',4000)) if d else ''}
    if command == 'history':
        records=[]
        for d in sorted((ROOT/'runs').glob('*'), reverse=True):
            if not d.is_dir(): continue
            result=read(d/'result.json', {}); state=result.get('state') or read(d/'latest_state.json', {})
            records.append({'name':d.name,'character':state.get('player',{}).get('character','未知'),
                            'floor':state.get('run',{}).get('floor'), 'ended': bool(result),
                            'review_status':read(d/'review_status.json',{}).get('status','未复盘')})
        return records[:200]
    if command == 'delete-run':
        name = payload.get('run')
        if not isinstance(name, str) or not name.strip():
            raise ValueError('请选择要删除的对局记录。')
        name = name.strip()
        directory = run_path(name)
        proc, running = active()
        if running and proc.get('run') == name:
            raise ValueError('不能删除正在运行的对局，请先停止自动游玩。')
        if not directory.exists() or not directory.is_dir() or directory.is_symlink():
            raise ValueError('找不到所选对局记录。')
        # Windows can briefly retain file handles while the UI refreshes logs.
        for attempt in range(5):
            try:
                shutil.rmtree(directory)
                break
            except OSError:
                if attempt == 4: raise
                time.sleep(0.08 * (attempt + 1))
        if proc.get('run') == name and not running:
            (ROOT / 'desktop_process.json').unlink(missing_ok=True)
        return {'deleted': name}
    if command == 'review-text':
        return {'text':tail(run_path(payload['run'])/'review.md',100000) or '本局尚无复盘。'}
    if command == 'memories':
        p=pathlib.Path(config.get('experience_db','experience/lessons.sqlite3'))
        if not p.is_absolute(): p=ROOT/p
        store=ExperienceStore(p)
        return store.list_memories(100)
    if command == 'probe':
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(config['game_url'], timeout=4) as r: s=json.load(r)
        return {'screen':s.get('state_type'),'deck_available':'deck' in s.get('player',{})}
    raise ValueError('Unknown command')

if __name__ == '__main__':
    try:
        command=sys.argv[1]
        payload=json.loads(sys.stdin.read() or '{}')
        print(json.dumps({'ok':True,'data':dispatch(command,payload)},ensure_ascii=True))
    except Exception as e:
        # Do not echo request payloads or keys in errors.
        print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=True))
        sys.exit(1)
