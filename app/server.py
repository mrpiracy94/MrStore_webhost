#!/usr/bin/env python3
"""MrStore_webhost: local single-admin Docker site manager, Python standard library."""
import hashlib
import hmac
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import cookies
from urllib.parse import urlparse, parse_qs
import zipfile

ROOT = Path('/data')
SITES = ROOT / 'sites'
DB = ROOT / 'sites.json'
CONFIG = ROOT / 'config'
HOST_DATA_DIR = os.environ.get('HOST_DATA_DIR', '/DATA/AppData/MrStore_webhost/data').rstrip('/')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
PORT = int(os.environ.get('PORT', '8484'))
MAX_ZIP = 50 * 1024 * 1024
MAX_UNPACKED = 150 * 1024 * 1024
MAX_FILES = 2500
MAX_EDIT = 1024 * 1024
MAX_LIST = 500
VERSION = '0.2'
ALLOWED = {'html', 'php', 'react', 'node'}
LOCK = threading.RLock()
SESSIONS = {}
JOBS = {}
LOGIN_ATTEMPTS = {}


def init():
    if len(ADMIN_PASSWORD) < 12 or any(x in ADMIN_PASSWORD.upper() for x in ('ALTERAR', 'CHANGE_ME', 'COLOCA_AQUI')):
        raise SystemExit('ERRO: Define ADMIN_PASSWORD com pelo menos 12 caracteres antes de iniciar.')
    if not HOST_DATA_DIR.startswith('/') or HOST_DATA_DIR == '/':
        raise SystemExit('ERRO: HOST_DATA_DIR deve ser um caminho absoluto especifico no anfitriao.')
    ROOT.mkdir(parents=True, exist_ok=True)
    SITES.mkdir(parents=True, exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True)
    for kind, fallback in (('html', '=404'), ('react', '/index.html')):
        config = CONFIG / f'nginx-{kind}.conf'
        if not config.exists():
            config.write_text('''server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;
    autoindex off;
    location / { try_files $uri $uri/ ''' + fallback + r'''; }
    location ~ /\. { deny all; }
    location ~* \.(php|phar|sql|sqlite|db|log|bak|ini|conf|ya?ml|toml|lock)$ { deny all; }
    location = /package.json { deny all; }
    location = /package-lock.json { deny all; }
}
''', encoding='utf-8')
    apache = CONFIG / 'apache-security.conf'
    if not apache.exists():
        apache.write_text(r'''<Directory /var/www/html>
    Options -Indexes
    <FilesMatch "(?i)^(\..*|composer\.(json|lock)|package(-lock)?\.json|.*\.(sql|sqlite|db|log|bak|ini|conf|ya?ml|toml|lock))$">
        Require all denied
    </FilesMatch>
</Directory>
''', encoding='utf-8')
    if not DB.exists():
        save_db({})
    else:
        load_db()


def load_db():
    with DB.open(encoding='utf-8') as f:
        result = json.load(f)
    if not isinstance(result, dict):
        raise ValueError('Base de dados invalida.')
    return result


def save_db(db):
    tmp = DB.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB)


def docker(*args, timeout=40, check=True):
    try:
        process = subprocess.run(['docker', *map(str, args)], capture_output=True, text=True,
                                 timeout=timeout, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        raise RuntimeError('A operacao excedeu o tempo limite.')
    if check and process.returncode:
        error = (process.stderr or process.stdout).strip()[-3000:]
        raise RuntimeError(error or 'Erro Docker desconhecido')
    return process


def container_name(slug):
    return 'zwh-' + slug


def inspect_managed(name, slug):
    p = docker('inspect', '--format', '{{json .}}', name, check=False)
    if p.returncode:
        return None
    try:
        info = json.loads(p.stdout)
    except json.JSONDecodeError:
        return None
    labels = info.get('Config', {}).get('Labels', {})
    if labels.get('org.mrstore_webhost.managed') != 'true' or labels.get('org.mrstore_webhost.slug', slug) != slug:
        raise RuntimeError('Ja existe um contentor com esse nome que nao pertence ao WebHost.')
    return info


def inspect_container(slug):
    return inspect_managed(container_name(slug), slug)


def remove_container(slug):
    if inspect_container(slug):
        docker('rm', '-f', container_name(slug), timeout=40)


def site_status(site):
    slug = site['slug']
    if slug in JOBS:
        return JOBS[slug]
    try:
        info = inspect_container(slug)
        if not info:
            return 'por publicar'
        state = info.get('State', {})
        return 'online' if state.get('Running') else 'parado'
    except Exception:
        return 'erro'


def site_list():
    with LOCK:
        site_values = [dict(site) for site in load_db().values()]
    sites = []
    for site in site_values:
        entry = dict(site)
        entry['status'] = site_status(site)
        path = SITES / site['slug'] / 'source'
        entry['uploaded'] = path.is_dir() and any(path.iterdir())
        sites.append(entry)
    return sorted(sites, key=lambda s: s['created'], reverse=True)


def run_builder(slug, release, script, timeout):
    # Dependency installation occurs only within an isolated release snapshot.
    host_source = f'{HOST_DATA_DIR}/sites/{slug}/releases/{release}'
    docker('run', '--rm', '--init', '--network', 'bridge', '--memory', '768m', '--pids-limit', '192',
           '--security-opt', 'no-new-privileges:true', '-v', f'{host_source}:/work', '-w', '/work',
           'node:22-alpine', 'sh', '-lc', script, timeout=timeout)


def site_run_args(site, release, name):
    slug, kind = site['slug'], site['kind']
    host_path = f'{HOST_DATA_DIR}/sites/{slug}/releases/{release}'
    source_path = SITES / slug / 'releases' / release
    if kind == 'react':
        dist = next((d for d in ('dist', 'build') if (source_path / d / 'index.html').is_file()), None)
        if not dist:
            raise RuntimeError('Build concluida, mas nao existe dist/index.html nem build/index.html.')
        docroot = f'{host_path}/{dist}'
    else:
        docroot = host_path
    args = ['run', '-d', '--name', name, '--label', 'org.mrstore_webhost.managed=true',
            '--label', f'org.mrstore_webhost.slug={slug}', '--restart', 'unless-stopped',
            '--security-opt', 'no-new-privileges:true', '--memory', '512m', '--pids-limit', '128']
    if kind != 'php':
        args += ['--cap-drop', 'ALL']
    if kind in ('html', 'react'):
        conf = f'{HOST_DATA_DIR}/config/nginx-{kind}.conf'
        args += ['-p', f"{site['port']}:8080", '--mount',
                 f'type=bind,source={docroot},target=/usr/share/nginx/html,readonly',
                 '--mount', f'type=bind,source={conf},target=/etc/nginx/conf.d/default.conf,readonly',
                 'nginxinc/nginx-unprivileged:stable-alpine']
    elif kind == 'php':
        conf = f'{HOST_DATA_DIR}/config/apache-security.conf'
        args += ['-p', f"{site['port']}:80", '--mount',
                 f'type=bind,source={docroot},target=/var/www/html,readonly',
                 '--mount', f'type=bind,source={conf},target=/etc/apache2/conf-enabled/mrstore_webhost-security.conf,readonly',
                 'php:8.3-apache']
    else:
        args += ['-p', f"{site['port']}:3000", '--user', '1000:1000', '-e', 'PORT=3000',
                 '-e', 'HOST=0.0.0.0', '-e', 'NODE_ENV=production', '-w', '/app',
                 '--mount', f'type=bind,source={docroot},target=/app,readonly',
                 'node:22-alpine', 'npm', 'start']
    return args


def cleanup_old_releases(slug, keep):
    releases = SITES / slug / 'releases'
    if not releases.is_dir():
        return
    for child in releases.iterdir():
        if child.is_dir() and child.name not in keep:
            shutil.rmtree(child, ignore_errors=True)


def deploy_site(slug):
    new_release = f'{int(time.time())}-{secrets.token_hex(5)}'
    new_path = SITES / slug / 'releases' / new_release
    old = None
    was_running = False
    stopped_old = False
    candidate_name = container_name(slug) + '-next'
    started_candidate = False
    promoted = False
    success = False
    try:
        with LOCK:
            site = load_db()[slug]
        kind = site['kind']
        source = SITES / slug / 'source'
        if not source.is_dir() or not any(source.iterdir()):
            raise RuntimeError('Envia primeiro um ficheiro ZIP com o website.')
        ignore = shutil.ignore_patterns('node_modules', '.git') if kind == 'node' else (
            shutil.ignore_patterns('node_modules', '.git', 'dist', 'build') if kind == 'react' else None)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, new_path, ignore=ignore)
        if kind == 'html' and not (new_path / 'index.html').is_file():
            raise RuntimeError('O site HTML necessita de index.html na raiz.')
        if kind == 'php' and not (new_path / 'index.php').is_file() and not (new_path / 'index.html').is_file():
            raise RuntimeError('O site PHP necessita de index.php ou index.html na raiz.')
        if kind in ('react', 'node'):
            pkg_path = new_path / 'package.json'
            if not pkg_path.is_file():
                raise RuntimeError('Nao foi encontrado package.json na raiz do projeto.')
            pkg = json.loads(pkg_path.read_text(encoding='utf-8'))
            scripts = pkg.get('scripts', {})
            required = 'build' if kind == 'react' else 'start'
            if not isinstance(scripts, dict) or not scripts.get(required):
                raise RuntimeError(f'package.json necessita do script "{required}".')
            install = 'if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi'
            run_builder(slug, new_release, install + (' && npm run build' if kind == 'react' else ''),
                        900 if kind == 'react' else 600)
        # Make sure a broken build does not stop the currently published container.
        site_run_args(site, new_release, candidate_name)
        with LOCK:
            JOBS[slug] = 'a publicar'
        old = inspect_container(slug)
        was_running = bool(old and old.get('State', {}).get('Running'))
        if inspect_managed(candidate_name, slug):
            docker('rm', '-f', candidate_name)
        if was_running:
            stopped_old = True
            docker('stop', container_name(slug), timeout=35)
        # The old container remains available for rollback until the new one is up.
        docker(*site_run_args(site, new_release, candidate_name), timeout=240)
        started_candidate = True
        # A running container is only a basic smoke test, not an HTTP health check.
        status = docker('inspect', '-f', '{{.State.Running}}', candidate_name, timeout=20)
        if status.stdout.strip().lower() != 'true':
            raise RuntimeError('O contentor novo terminou logo apos iniciar. Verifica os logs Docker.')
        if old:
            docker('rm', '-f', container_name(slug))
        docker('rename', candidate_name, container_name(slug))
        started_candidate = False
        promoted = True
        with LOCK:
            db = load_db()
            if slug in db:
                previous_release = db[slug].get('active_release')
                db[slug]['previous_release'] = previous_release
                db[slug]['active_release'] = new_release
                db[slug]['last_error'] = ''
                db[slug]['deployed_at'] = int(time.time())
                save_db(db)
        success = True
        for backup in (SITES / slug).glob('backup-*'):
            if backup.is_dir():
                shutil.rmtree(backup, ignore_errors=True)
        # Keep one prior successful release for recovery.
        try:
            cleanup_old_releases(slug, {new_release, previous_release} if previous_release else {new_release})
        except OSError:
            pass  # Never roll back a successful deploy because housekeeping failed.
    except Exception as exc:
        err = str(exc)[-3000:]
        try:
            if not promoted and (started_candidate or inspect_managed(candidate_name, slug)):
                docker('rm', '-f', candidate_name, timeout=30)
            if stopped_old and not promoted:
                # If the old container still exists, bring it back online.
                if inspect_container(slug):
                    docker('start', container_name(slug), timeout=45)
                else:
                    # Last-resort recovery when failure occurs after old removal.
                    old_release = site.get('active_release')
                    if old_release and (SITES / slug / 'releases' / old_release).exists():
                        docker(*site_run_args(site, old_release, container_name(slug)), timeout=240)
        except Exception as recovery_error:
            err += ' | Recuperacao automatica falhou: ' + str(recovery_error)[-1000:]
        with LOCK:
            db = load_db()
            if slug in db:
                db[slug]['last_error'] = err
                save_db(db)
    finally:
        if not success and not promoted:
            shutil.rmtree(new_path, ignore_errors=True)
        with LOCK:
            JOBS.pop(slug, None)


def safe_source_path(slug, relative):
    if not isinstance(relative, str) or len(relative) > 240 or not relative or '\\' in relative or '\x00' in relative:
        raise ValueError('Caminho de ficheiro invalido.')
    parts = relative.split('/')
    if any(x in ('', '.', '..') for x in parts) or relative.startswith('/') or ':' in parts[0]:
        raise ValueError('Caminho de ficheiro invalido.')
    if any(x in ('.git', 'node_modules') for x in parts):
        raise ValueError('Esta pasta nao pode ser editada no painel.')
    root = SITES / slug / 'source'
    path = root.joinpath(*parts)
    if root.is_symlink() or any(parent.is_symlink() for parent in (path, *path.parents) if parent == root or root in parent.parents):
        raise ValueError('Nao e permitido aceder atraves de links simbolicos.')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Ficheiro fora da pasta do website.')
    return path


def list_source_files(slug):
    source = SITES / slug / 'source'
    if not source.exists():
        return []
    found = []
    for p in source.rglob('*'):
        if any(part in ('.git', 'node_modules') for part in p.relative_to(source).parts):
            continue
        if p.is_file() and not p.is_symlink():
            found.append({'path': p.relative_to(source).as_posix(), 'size': p.stat().st_size})
            if len(found) >= MAX_LIST:
                break
    return sorted(found, key=lambda x: x['path'])



def unzip_safely(data, destination):
    """Unpack a bounded ZIP; reject traversal, links, oversized/unusual archives."""
    if len(data) > MAX_ZIP:
        raise ValueError('ZIP demasiado grande (limite 50 MB).')
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError('O ficheiro nao e um ZIP valido.')
    with archive as z:
        entries = z.infolist()
        if len(entries) > MAX_FILES:
            raise ValueError('Demasiados ficheiros (limite 2500).')
        if sum(item.file_size for item in entries) > MAX_UNPACKED:
            raise ValueError('Conteudo descomprimido excede 150 MB.')
        normalized = []
        for item in entries:
            path = item.filename.replace('\\', '/')
            bits = PurePosixPath(path).parts
            if (path.startswith('/') or not bits or any(part in ('..', '.') for part in bits)
                    or ':' in bits[0] or '\x00' in path):
                raise ValueError('ZIP contem caminhos invalidos.')
            mode = (item.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('ZIP contem links simbolicos ou ficheiros especiais.')
            normalized.append((item, bits))
        files = [(item, bits) for item, bits in normalized if not item.is_dir() and bits[0] != '__MACOSX']
        if not files:
            raise ValueError('ZIP sem ficheiros utilizaveis.')
        strip_root = (all(len(bits) > 1 for _, bits in files)
                      and len({bits[0] for _, bits in files}) == 1)
        extracted = 0
        for item, bits in files:
            parts = bits[1:] if strip_root else bits
            if not parts:
                continue
            out = destination.joinpath(*parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item, 'r') as inp, out.open('wb') as target:
                while chunk := inp.read(256 * 1024):
                    extracted += len(chunk)
                    if extracted > MAX_UNPACKED:
                        raise ValueError('ZIP expandido excede 150 MB.')
                    target.write(chunk)
    return len(files)


class Handler(BaseHTTPRequestHandler):
    server_version = 'MrStore_webhost/0.2'

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} - {fmt % args}', flush=True)

    def send_json(self, obj, status=200, headers=None):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def problem(self, msg, status=400):
        self.send_json({'error': str(msg)}, status)

    def authenticated(self):
        cookie = cookies.SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            sid = cookie['sid'].value if 'sid' in cookie else ''
        except cookies.CookieError:
            return False
        with LOCK:
            expiry = SESSIONS.get(sid, 0)
            if expiry > time.time():
                return True
            SESSIONS.pop(sid, None)
        return False

    def require_login(self):
        if not self.authenticated():
            self.problem('Autenticacao necessaria.', 401)
            return False
        return True

    def require_origin(self):
        # A non-simple custom header blocks cross-site HTML forms and CORS fetches.
        if self.headers.get('X-MrStore_webhost-Request') != '1':
            self.problem('Pedido sem protecao CSRF.', 403)
            return False
        origin = self.headers.get('Origin')
        # Browser API requests include Origin. Reject cross-origin mutations.
        if origin and urlparse(origin).netloc.lower() != self.headers.get('Host', '').lower():
            self.problem('Origem nao autorizada.', 403)
            return False
        return True

    def read_body(self, limit=1024 * 1024):
        length = self.headers.get('Content-Length', '')
        if not length.isdigit():
            raise ValueError('Content-Length obrigatorio.')
        size = int(length)
        if size > limit:
            raise ValueError('Pedido demasiado grande.')
        return self.rfile.read(size)

    def read_json(self, limit=1024 * 1024):
        return json.loads(self.read_body(limit).decode('utf-8'))

    def parse_site_action(self, parts):
        if len(parts) != 4 or parts[:2] != ['api', 'sites']:
            return None
        slug, action = parts[2], parts[3]
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,31}', slug):
            return None
        return slug, action

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            file = Path(__file__).with_name('index.html')
            data = file.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == '/api/session':
            return self.send_json({'authenticated': self.authenticated()})
        if not self.require_login():
            return
        if path == '/api/sites':
            return self.send_json({'sites': site_list()})
        parts = path.strip('/').split('/')
        parsed = self.parse_site_action(parts)
        if parsed and parsed[1] == 'files':
            slug = parsed[0]
            with LOCK:
                if slug not in load_db():
                    return self.problem('Website nao encontrado.', 404)
            selected = parse_qs(urlparse(self.path).query).get('path', [None])[0]
            if selected is None:
                return self.send_json({'files': list_source_files(slug)})
            try:
                path_file = safe_source_path(slug, selected)
                if not path_file.is_file() or path_file.stat().st_size > MAX_EDIT:
                    return self.problem('Ficheiro inexistente ou demasiado grande.', 404)
                return self.send_json({'path': selected, 'content': path_file.read_text(encoding='utf-8')})
            except (ValueError, OSError, UnicodeDecodeError) as e:
                return self.problem(e)
        if parsed and parsed[1] == 'logs':
            slug = parsed[0]
            with LOCK:
                if slug not in load_db():
                    return self.problem('Website nao encontrado.', 404)
            try:
                if not inspect_container(slug):
                    return self.send_json({'logs': 'O website ainda nao foi publicado.'})
                proc = docker('logs', '--tail', '100', container_name(slug), timeout=15, check=False)
                return self.send_json({'logs': (proc.stdout + proc.stderr)[-12000:]})
            except Exception as e:
                return self.problem(e, 500)
        return self.problem('Caminho nao encontrado.', 404)

    def do_POST(self):
        if not self.require_origin():
            return
        path = urlparse(self.path).path
        if path == '/api/login':
            try:
                body = self.read_json()
                ip = self.client_address[0]
                now = time.time()
                with LOCK:
                    old = [t for t in LOGIN_ATTEMPTS.get(ip, []) if now - t < 300]
                    if len(old) >= 8:
                        return self.problem('Demasiadas tentativas; volta a tentar dentro de alguns minutos.', 429)
                    supplied = str(body.get('password', ''))
                    if not hmac.compare_digest(supplied.encode(), ADMIN_PASSWORD.encode()):
                        LOGIN_ATTEMPTS[ip] = old + [now]
                        return self.problem('Password incorreta.', 401)
                    LOGIN_ATTEMPTS.pop(ip, None)
                    sid = secrets.token_urlsafe(32)
                    SESSIONS[sid] = now + 12 * 3600
                secure = '; Secure' if os.environ.get('COOKIE_SECURE', '') == '1' else ''
                return self.send_json({'ok': True}, headers={
                    'Set-Cookie': f'sid={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}'})
            except (ValueError, json.JSONDecodeError) as e:
                return self.problem(e)
        if not self.require_login():
            return
        if path == '/api/logout':
            cookie = cookies.SimpleCookie()
            cookie.load(self.headers.get('Cookie', ''))
            sid = cookie['sid'].value if 'sid' in cookie else ''
            with LOCK:
                SESSIONS.pop(sid, None)
            return self.send_json({'ok': True}, headers={'Set-Cookie': 'sid=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
        if path == '/api/sites':
            try:
                body = self.read_json()
                slug = str(body.get('slug', '')).lower()
                kind = body.get('kind')
                name = str(body.get('name', '')).strip()
                if not re.fullmatch(r'[a-z][a-z0-9-]{1,31}', slug):
                    return self.problem('Identificador: 2-32 caracteres, letras minusculas, numeros e hifens.')
                if kind not in ALLOWED or len(name) < 2 or len(name) > 60:
                    return self.problem('Nome ou tecnologia invalida.')
                with LOCK:
                    db = load_db()
                    if slug in db:
                        return self.problem('Ja existe um website com este identificador.', 409)
                    used = {s['port'] for s in db.values()}
                    port = next((p for p in range(9101, 9201) if p not in used), None)
                    if port is None:
                        return self.problem('Nao ha mais portas livres na gama 9101-9200.', 409)
                    item = dict(slug=slug, name=name, kind=kind, port=port,
                                created=int(time.time()), deployed_at=None, last_error='')
                    db[slug] = item
                    save_db(db)
                    (SITES / slug).mkdir(parents=True, exist_ok=True)
                return self.send_json({'site': item}, 201)
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                return self.problem(e)
        parts = path.strip('/').split('/')
        parsed = self.parse_site_action(parts)
        if not parsed:
            return self.problem('Caminho nao encontrado.', 404)
        slug, action = parsed
        with LOCK:
            if slug not in load_db():
                return self.problem('Website nao encontrado.', 404)
            if slug in JOBS:
                return self.problem('Ja ha uma operacao em curso neste website.', 409)
        if action == 'files':
            with LOCK:
                if slug in JOBS:
                    return self.problem('Ja ha uma operacao em curso neste website.', 409)
                JOBS[slug] = 'a editar'
            try:
                payload = self.read_json(MAX_EDIT * 2)
                relative = payload.get('path')
                operation = payload.get('op', 'save')
                file = safe_source_path(slug, relative)
                if operation == 'save':
                    content = payload.get('content')
                    if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_EDIT:
                        return self.problem('Conteudo demasiado grande (maximo 1 MB).')
                    file.parent.mkdir(parents=True, exist_ok=True)
                    tmp = file.with_name(file.name + '.zwh-' + secrets.token_hex(5))
                    try:
                        tmp.write_text(content, encoding='utf-8')
                        os.replace(tmp, file)
                    finally:
                        tmp.unlink(missing_ok=True)
                elif operation == 'delete':
                    if not file.is_file():
                        return self.problem('Ficheiro nao encontrado.', 404)
                    file.unlink()
                else:
                    return self.problem('Acao desconhecida.')
                return self.send_json({'ok': True, 'files': list_source_files(slug)})
            except (ValueError, OSError, TypeError, json.JSONDecodeError) as e:
                return self.problem(e)
            finally:
                with LOCK:
                    JOBS.pop(slug, None)
        if action == 'upload':
            if self.headers.get('Content-Type', '').split(';')[0] not in ('application/zip', 'application/octet-stream'):
                return self.problem('Envia o ficheiro ZIP com application/zip.')
            dest = SITES / slug
            staging = dest / ('staging-' + secrets.token_hex(6))
            with LOCK:
                if slug in JOBS:
                    return self.problem('Ja ha uma operacao em curso neste website.', 409)
                JOBS[slug] = 'a carregar'
            backup = dest / ('backup-' + secrets.token_hex(6))
            moved_old = False
            try:
                data = self.read_body(MAX_ZIP)
                staging.mkdir(parents=True)
                total = unzip_safely(data, staging)
                source = dest / 'source'
                if source.exists():
                    source.rename(backup)
                    moved_old = True
                try:
                    staging.rename(source)
                except Exception:
                    if moved_old:
                        backup.rename(source)
                        moved_old = False
                    raise
                # Do not delete files behind the old bind-mount until replacement succeeded.
                with LOCK:
                    db = load_db()
                    db[slug]['last_error'] = ''
                    save_db(db)
                return self.send_json({'ok': True, 'files': total})
            except (ValueError, OSError, RuntimeError) as e:
                return self.problem(e)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
                # Older v0.1 containers can still bind-mount the previous source.
                # Retain it until the user upgrades or republishes, to avoid live 404s.
                if moved_old:
                    # Keep a legacy backup on first migration; otherwise safe to remove.
                    try:
                        legacy_live = bool(inspect_container(slug)) and not load_db()[slug].get('active_release')
                    except Exception:
                        legacy_live = True
                    if not legacy_live:
                        shutil.rmtree(backup, ignore_errors=True)
                with LOCK:
                    JOBS.pop(slug, None)
        if action == 'deploy':
            with LOCK:
                if slug in JOBS:
                    return self.problem('Ja ha uma operacao em curso neste website.', 409)
                JOBS[slug] = 'a preparar'
            threading.Thread(target=deploy_site, args=(slug,), daemon=True).start()
            return self.send_json({'ok': True, 'message': 'Publicacao iniciada.'}, 202)
        if action == 'stop':
            try:
                with LOCK:
                    if slug in JOBS:
                        return self.problem('Ja ha uma operacao em curso neste website.', 409)
                    if inspect_container(slug):
                        docker('stop', container_name(slug), timeout=35)
                return self.send_json({'ok': True})
            except RuntimeError as e:
                return self.problem(e, 500)
        if action == 'delete':
            try:
                with LOCK:
                    if slug in JOBS:
                        return self.problem('Ja ha uma operacao em curso neste website.', 409)
                    remove_container(slug)
                    db = load_db()
                    del db[slug]
                    save_db(db)
                    shutil.rmtree(SITES / slug, ignore_errors=True)
                return self.send_json({'ok': True})
            except Exception as e:
                return self.problem(e, 500)
        return self.problem('Acao desconhecida.', 404)


if __name__ == '__main__':
    init()
    print(f'MrStore_webhost a funcionar na porta {PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()