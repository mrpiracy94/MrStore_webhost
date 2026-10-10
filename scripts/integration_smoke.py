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


def run_tests():
    # The host path must also be visible to the Docker daemon outside the panel container.
    with tempfile.TemporaryDirectory(prefix='mrstore_ci_') as folder:
        data = Path(folder)
        docker('run', '-d', '--name', PANEL_NAME, '-p', '127.0.0.1:18484:8484',
               '-e', 'ADMIN_PASSWORD=ci-only-password-12345',
               '-e', f'HOST_DATA_DIR={folder}',
               '-e', 'SITE_BIND_IP=127.0.0.1',
               '-e', 'HEALTH_ATTEMPTS=30',
               '-v', '/var/run/docker.sock:/var/run/docker.sock',
               '-v', f'{folder}:/data', 'mrstore_webhost:ci')
        try:
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
                print(f'{kind}: HTTP {resp.status}, {len(body)} bytes')
                code, log, _ = request('GET', '/api/sites/' + slug + '/logs', cookie=cookie)
                assert code == 200 and any(x['event'] == 'publicada' for x in log['events'])
        finally:
            for kind in ('html', 'php', 'node', 'react'):
                docker('rm', '-f', 'zwh-ci-' + kind, check=False)
                for suffix in ('-probe', '-next', '-prev'):
                    docker('rm', '-f', 'zwh-ci-' + kind + suffix, check=False)
            docker('rm', '-f', PANEL_NAME, check=False)
            # Website build images can write root-owned files into bind mounts.
            # Reclaim only this temporary CI directory using our existing local
            # test image, without mounting the Docker socket into the helper.
            permissions = docker(
                'run', '--rm', '--user', '0:0',
                '-v', f'{folder}:/cleanup', '--entrypoint', 'sh',
                'mrstore_webhost:ci', '-c', 'chmod -R a+rwX /cleanup',
                check=False,
            )
            if permissions.returncode:
                print('Warning: cannot restore CI temporary directory permissions:',
                      permissions.stderr, flush=True)


if __name__ == '__main__':
    if not shutil.which('docker'):
        raise SystemExit('Docker e obrigatorio para este teste de integracao.')
    run_tests()
    print('4 testes de integracao Docker reais passaram')
