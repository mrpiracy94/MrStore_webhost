#!/usr/bin/env python3
"""End-to-end smoke test against an actual Docker daemon. Designed for GitHub Actions Ubuntu runners.

Do not run this against a NAS with valuable containers or projects: this test creates
four ephemeral ZimaWebHost containers and uses ports 9101-9104, 8484 (host 18484).
"""
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PANEL_NAME = 'mrstore-ci-panel'
ENGINE_NAME = 'mrstore-ci-rootless-engine'


def docker(*args, check=True):
    return subprocess.run(['docker', *args], check=check, capture_output=True, text=True)


def request(method, path, obj=None, cookie=None, binary=None):
    headers = {'X-MrStore_webhost-Request': '1'} if method == 'POST' else {}
    if cookie:
        headers['Cookie'] = cookie
    if binary is not None:
        body = binary
        headers['Content-Type'] = 'application/zip'
    elif obj is not None:
        body = json.dumps(obj).encode()
        headers['Content-Type'] = 'application/json'
    else:
        body = None
    connection = http.client.HTTPConnection('127.0.0.1', 18484, timeout=10)
    try:
        connection.request(method, path, body=body, headers=headers)
        result = connection.getresponse()
        status, raw, session = result.status, result.read(), result.getheader('Set-Cookie')
        return status, json.loads(raw.decode()), session
    finally:
        connection.close()


def wait_for_panel(seconds=45):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        try:
            request('GET', '/api/session')
            return
        except OSError:
            time.sleep(1)
    raise RuntimeError('Painel nao abriu a API HTTP em 45 segundos')


def wait_for_rootless(sock_dir, seconds=100):
    socket = str(Path(sock_dir) / 'docker.sock')
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            info = subprocess.run(['sudo', '-n', 'docker', '--host', 'unix://' + socket, 'info',
                                   '--format', '{{json .SecurityOptions}}'],
                                  capture_output=True, text=True, timeout=5)
            if info.returncode == 0 and isinstance(json.loads(info.stdout), list) and 'name=rootless' in json.loads(info.stdout):
                return
        except (subprocess.SubprocessError, ValueError, OSError):
            pass
        time.sleep(2)
    report = docker('logs', '--tail', '100', ENGINE_NAME, check=False)\n    state = docker('inspect', '--format', '{{.State.Status}} {{.State.ExitCode}}', ENGINE_NAME, check=False)\n    nested = docker('exec', ENGINE_NAME, 'sh', '-lc',\n                    'docker info --format \"{{json .SecurityOptions}}\" 2>&1; ls -la /run/user/1000; ps aux | tail -15',\n                    check=False)
    raise RuntimeError('Docker rootless de teste nao iniciou/nao passou validacao de seguranca. '
                       + ' state=' + state.stdout[-120:] + ' nested=' + (nested.stdout or nested.stderr)[-1800:]\n                       + ' logs=' + (report.stdout or report.stderr)[-1800:])


def run_tests():
    # CI isolation only: privileged outer DIND is an ephemeral GitHub runner fixture,
    # NEVER part of the user's ZimaOS deployment. The panel accesses ONLY the
    # inner, rootless daemon via a dedicated socket mount, never the system socket.
    folder = tempfile.mkdtemp(prefix='mrstore_ci_')
    sock_dir = tempfile.mkdtemp(prefix='mrstore_rootless_socket_')
    os.chmod(folder, 0o777)
    # Rootlesskit refuses an XDG_RUNTIME_DIR writable by other users.
    # GitHub-hosted CI permits sudo; NEVER do this on a production NAS.
    subprocess.run(['sudo', '-n', 'chown', '1000:1000', sock_dir], check=True)
    subprocess.run(['sudo', '-n', 'chmod', '700', sock_dir], check=True)
    try:
        docker('run', '-d', '--privileged', '--name', ENGINE_NAME,\n               '-e', 'DOCKER_TLS_CERTDIR=',
               '-v', f'{folder}:{folder}',
               '-v', f'{sock_dir}:/run/user/1000',
               '-p', '127.0.0.1:9101:9101', '-p', '127.0.0.1:9102:9102',
               '-p', '127.0.0.1:9103:9103', '-p', '127.0.0.1:9104:9104',
               'docker:27-dind-rootless')
        wait_for_rootless(sock_dir)
        docker('run', '-d', '--name', PANEL_NAME, '--user', '1000:1000',
               '-p', '127.0.0.1:18484:8484',
               '-e', 'ADMIN_PASSWORD=ci-only-password-12345',
               '-e', 'DOCKER_HOST=unix:///run/mrstore/docker.sock',
               '-e', f'HOST_DATA_DIR={folder}',
               '-e', 'SITE_BIND_IP=0.0.0.0',
               '-e', 'HEALTH_ATTEMPTS=30',
               '-v', f'{sock_dir}:/run/mrstore',
               '-v', f'{folder}:/data', 'mrstore_webhost:ci')
        wait_for_panel()
        code, _, set_cookie = request('POST', '/api/login', {'password':'ci-only-password-12345'})
        assert code == 200, 'Login HTTP falhou'
        cookie = set_cookie.split(';', 1)[0]
        for i, kind in enumerate(('html', 'php', 'node', 'react'), 1):
            slug = 'ci-' + kind
            code, body, _ = request('POST', '/api/sites', {'slug':slug,'name':'CI '+kind, 'kind':kind}, cookie)
            assert code == 201, (kind, body)
            archive = ROOT / 'examples/zips' / f'exemplo-{kind}.zip'
            code, body, _ = request('POST', '/api/sites/' + slug + '/upload', cookie=cookie, binary=archive.read_bytes())
            assert code == 200, (kind, body)
            code, body, _ = request('POST', '/api/sites/' + slug + '/deploy', cookie=cookie)
            assert code == 202, (kind, body)
            until = time.monotonic() + 240
            while time.monotonic() < until:
                code, body, _ = request('GET', '/api/sites', cookie=cookie)
                site = next(s for s in body['sites'] if s['slug'] == slug)
                if site.get('last_error'):
                    raise AssertionError(f"{kind} deploy failed: {site['last_error']}")
                if site.get('active_release') and site['status'] == 'online':
                    break
                time.sleep(2)
            else:
                raise AssertionError(f'{kind} deploy exceeded 240 seconds')
            con = http.client.HTTPConnection('127.0.0.1', 9100 + i, timeout=10)
            con.request('GET', '/')
            resp = con.getresponse()
            body = resp.read()
            assert 200 <= resp.status < 400 and body, (kind, resp.status, body[:250])
            con.close()
            print(f'{kind}: HTTP {resp.status}, {len(body)} bytes', flush=True)
            code, log, _ = request('GET', '/api/sites/' + slug + '/logs', cookie=cookie)
            assert code == 200 and any(x['event'] == 'publicada' for x in log['events'])
    finally:
        # Cleanup must happen in the inner rootless engine, not the rootful host.
        rootless_host = 'unix://' + str(Path(sock_dir) / 'docker.sock')
        for kind in ('html', 'php', 'node', 'react'):
            subprocess.run(['docker', '--host', rootless_host, 'rm', '-f', 'zwh-ci-' + kind],
                           capture_output=True, check=False)
            for suffix in ('-probe', '-next', '-prev'):
                subprocess.run(['docker', '--host', rootless_host, 'rm', '-f', 'zwh-ci-' + kind + suffix],
                               capture_output=True, check=False)
        docker('rm', '-f', PANEL_NAME, check=False)
        docker('rm', '-f', ENGINE_NAME, check=False)
        # Privileged CI cleanup only; subordinate UID ownership can be opaque to runner.
        for path in (folder, sock_dir):
            subprocess.run(['sudo', '-n', 'rm', '-rf', '--', path], check=True)


if __name__ == '__main__':
    if not shutil.which('docker'):
        raise SystemExit('Docker e obrigatorio para este teste de integracao.')
    run_tests()
    print('4 testes de integracao Docker reais passaram')
