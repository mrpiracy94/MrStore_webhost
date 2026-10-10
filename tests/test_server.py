import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('server', ROOT / 'app/server.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


def create_zip(files, symlink=False):
    f = io.BytesIO()
    with zipfile.ZipFile(f, 'w') as z:
        for key, value in files.items():
            if symlink:
                zi = zipfile.ZipInfo(key)
                zi.create_system = 3
                zi.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(zi, value)
            else:
                z.writestr(key, value)
    return f.getvalue()


class FakeDocker:
    def __init__(self):
        self.containers = {}
        self.calls = []
        self.fail_next_run = False
        self.health_fail_count = 0
        self.fail_promote = False
        self.fail_preview_health = False
        self.fail_candidate_health = False

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        cmd = args[0]
        output = ''
        rc = 0
        if cmd == 'inspect':
            name = args[-1]
            c = self.containers.get(name)
            if c is None:
                rc = 1
            elif '-f' in args:
                output = 'true' if c['State']['Running'] else 'false'
            else:
                output = json.dumps(c)
        elif cmd == 'run':
            if self.fail_next_run:
                self.fail_next_run = False
                raise RuntimeError('forced run failure')
            name = args[args.index('--name') + 1]
            labelvals = [args[i+1] for i,x in enumerate(args[:-1]) if x=='--label']
            labels = dict(x.split('=', 1) for x in labelvals)
            self.containers[name] = {'Config':{'Labels':labels}, 'State':{'Running':True}}
            output = 'new-container-id'
        elif cmd == 'exec':
            if (self.fail_preview_health and args[1].endswith('-probe')) or (self.fail_candidate_health and args[1].endswith('-next')):
                rc = 1
            if self.health_fail_count > 0:
                self.health_fail_count -= 1
                rc = 1
        elif cmd == 'stop':
            self.containers[args[1]]['State']['Running'] = False
        elif cmd == 'start':
            self.containers[args[1]]['State']['Running'] = True
        elif cmd == 'rm':
            self.containers.pop(args[-1], None)
        elif cmd == 'rename':
            if self.fail_promote and args[1].endswith('-next'):
                self.fail_promote = False
                raise RuntimeError('forced promotion failure')
            self.containers[args[2]] = self.containers.pop(args[1])
        class Result:
            pass
        r = Result()
        r.stdout, r.stderr, r.returncode = output, '', rc
        return r


class TestZip(unittest.TestCase):
    def test_flat(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(web.unzip_safely(create_zip({'index.html': '<h1>hi</h1>'}), Path(d)), 1)
            self.assertEqual((Path(d) / 'index.html').read_text(), '<h1>hi</h1>')

    def test_strips_wrapper_dir(self):
        with tempfile.TemporaryDirectory() as d:
            web.unzip_safely(create_zip({'project/index.html': 'OK', 'project/style.css': 'style'}), Path(d))
            self.assertTrue((Path(d) / 'index.html').exists())
            self.assertFalse((Path(d) / 'project').exists())

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                web.unzip_safely(create_zip({'../outside.txt': 'attack'}), Path(d))
            self.assertFalse((Path(d).parent / 'outside.txt').exists())

    def test_windows_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                web.unzip_safely(create_zip({'hello\\..\\..\\outside.txt': 'attack'}), Path(d))

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                web.unzip_safely(create_zip({'link': '../outside'}, symlink=True), Path(d))

    def test_uncompressed_limit(self):
        with tempfile.TemporaryDirectory() as d:
            old=web.MAX_UNPACKED
            try:
                web.MAX_UNPACKED=10
                with self.assertRaises(ValueError):
                    web.unzip_safely(create_zip({'large.txt':'a'*11}), Path(d))
            finally:
                web.MAX_UNPACKED=old


class TestHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        web.ROOT = Path(self.tmp.name)
        web.DB = web.ROOT / 'sites.json'
        web.SITES = web.ROOT / 'sites'
        web.CONFIG = web.ROOT / 'config'
        web.ADMIN_PASSWORD = 'test-admin-password-very-long'
        web.SESSIONS.clear()
        web.LOGIN_ATTEMPTS.clear()
        web.JOBS.clear()
        web.init()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def call(self, method, path, body=None, cookie=None, headers=None):
        con = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        allheaders = {'Host': f'127.0.0.1:{self.port}'}
        if cookie: allheaders['Cookie'] = cookie
        if method == 'POST': allheaders['X-MrStore_webhost-Request'] = '1'
        if headers: allheaders.update(headers)
        if isinstance(body, dict):
            body = json.dumps(body)
            allheaders['Content-Type'] = 'application/json'
        con.request(method, path, body=body, headers=allheaders)
        response = con.getresponse()
        result = json.loads(response.read().decode())
        status = response.status
        set_cookie = response.getheader('Set-Cookie')
        con.close()
        return status, result, set_cookie

    def login(self):
        status, _, cookie = self.call('POST', '/api/login', {'password': web.ADMIN_PASSWORD})
        self.assertEqual(status, 200)
        return cookie.split(';')[0]


    def test_preflight_http_failure_preserves_running_site(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'pagina', 'name': 'Pagina', 'kind': 'html'}, cookie=cookie)
        src = web.SITES / 'pagina/source'
        src.mkdir()
        (src / 'index.html').write_text('first')
        fake = FakeDocker()
        with patch.object(web, 'docker', side_effect=fake):
            web.deploy_site('pagina')
            old_release = web.load_db()['pagina']['active_release']
            (src / 'index.html').write_text('second')
            fake.fail_preview_health = True
            with patch.object(web, 'HEALTH_ATTEMPTS', 2), patch.object(web.time, 'sleep'):
                web.deploy_site('pagina')
        self.assertTrue(fake.containers['zwh-pagina']['State']['Running'])
        self.assertEqual(web.load_db()['pagina']['active_release'], old_release)
        self.assertIn('HTTP', web.load_db()['pagina']['last_error'])
        self.assertFalse('zwh-pagina-probe' in fake.containers)
        self.assertFalse('pending_release' in web.load_db()['pagina'])

    def test_candidate_http_failure_rolls_back(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'pagina', 'name': 'Pagina', 'kind': 'html'}, cookie=cookie)
        src = web.SITES / 'pagina/source'
        src.mkdir()
        (src / 'index.html').write_text('first')
        fake = FakeDocker()
        with patch.object(web, 'docker', side_effect=fake):
            web.deploy_site('pagina')
            original = web.load_db()['pagina']['active_release']
            (src / 'index.html').write_text('second')
            fake.fail_candidate_health = True
            with patch.object(web, 'HEALTH_ATTEMPTS', 2), patch.object(web.time, 'sleep'):
                web.deploy_site('pagina')
        self.assertTrue(fake.containers['zwh-pagina']['State']['Running'])
        self.assertEqual(web.load_db()['pagina']['active_release'], original)
        self.assertNotIn('zwh-pagina-next', fake.containers)
        self.assertNotIn('pending_release', web.load_db()['pagina'])

    def test_promotion_error_restores_backup(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'pagina', 'name': 'Pagina', 'kind': 'html'}, cookie=cookie)
        src = web.SITES / 'pagina/source'
        src.mkdir()
        (src / 'index.html').write_text('first')
        fake = FakeDocker()
        with patch.object(web, 'docker', side_effect=fake):
            web.deploy_site('pagina')
            original = web.load_db()['pagina']['active_release']
            (src / 'index.html').write_text('second')
            fake.fail_promote = True
            web.deploy_site('pagina')
        self.assertTrue(fake.containers['zwh-pagina']['State']['Running'])
        self.assertEqual(web.load_db()['pagina']['active_release'], original)
        self.assertNotIn('zwh-pagina-prev', fake.containers)
        self.assertIn('forced promotion failure', web.load_db()['pagina']['last_error'])

    def test_startup_recovers_interrupted_rename(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'pagina', 'name': 'Pagina', 'kind': 'html'}, cookie=cookie)
        src = web.SITES / 'pagina/source'
        src.mkdir()
        (src / 'index.html').write_text('first')
        fake = FakeDocker()
        with patch.object(web, 'docker', side_effect=fake):
            web.deploy_site('pagina')
            fake('stop', 'zwh-pagina')
            fake('rename', 'zwh-pagina', 'zwh-pagina-prev')
            db = web.load_db()
            db['pagina']['pending_release'] = 'new-but-uncommitted'
            db['pagina']['pending_was_running'] = True
            web.save_db(db)
            web.recover_interrupted_deployments()
        self.assertTrue(fake.containers['zwh-pagina']['State']['Running'])
        self.assertNotIn('pending_release', web.load_db()['pagina'])
        self.assertNotIn('zwh-pagina-prev', fake.containers)
        self.assertIn('recuperada', web.load_db()['pagina']['last_error'])

    def test_deployment_audit_events_returned_with_logs(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'pagina', 'name': 'Pagina', 'kind': 'html'}, cookie=cookie)
        src = web.SITES / 'pagina/source'
        src.mkdir()
        (src / 'index.html').write_text('first')
        fake = FakeDocker()
        with patch.object(web, 'docker', side_effect=fake):
            web.deploy_site('pagina')
            status, body, _ = self.call('GET', '/api/sites/pagina/logs', cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn('events', body)
        self.assertIn('publicada', [e['event'] for e in body['events']])

    def test_probe_commands_use_real_http_clients(self):
        for kind, runtime in [('html', 'wget'), ('react', 'wget'), ('php', 'php'), ('node', 'node')]:
            with self.subTest(kind=kind):
                cmd = web.probe_command(kind, 'zwh-site-probe')
                self.assertEqual(cmd[:2], ('exec', 'zwh-site-probe'))
                self.assertEqual(cmd[2], runtime)

    def test_site_ports_are_bound_to_configured_ip(self):
        site = {'slug': 'example', 'port': 9123, 'kind': 'html'}
        args = web.site_run_args(site, 'r1', 'zwh-example-probe')
        self.assertIn(f'{web.SITE_BIND_IP}:9123:8080', args)
        preview = web.site_run_args(site, 'r1', 'zwh-example-probe', published=False)
        self.assertNotIn('-p', preview)

    def test_panel_html_renders_and_has_editor(self):
        con = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        con.request('GET', '/')
        response = con.getresponse()
        body = response.read().decode('utf-8')
        self.assertEqual(response.status, 200)
        self.assertIn('filesOverlay', body)
        self.assertIn('MrStore_webhost', body)
        self.assertIn('href="https://mrpiracy94.github.io/MrStore/"', body)
        self.assertIn('Catálogo de apps', body)
        self.assertIn("X-MrStore_webhost-Request", body)
        con.close()

    def test_requires_login(self):
        status, _, _ = self.call('GET', '/api/sites')
        self.assertEqual(status, 401)

    def test_login_create_and_upload(self):
        cookie = self.login()
        status, site, _ = self.call('POST', '/api/sites', {'slug': 'meu-site', 'name': 'Meu site', 'kind': 'html'}, cookie=cookie)
        self.assertEqual(status, 201)
        self.assertEqual(site['site']['port'], 9101)
        z = create_zip({'index.html': 'ola'})
        status, _, _ = self.call('POST', '/api/sites/meu-site/upload', z, cookie=cookie,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(status, 200)
        self.assertEqual((web.SITES / 'meu-site/source/index.html').read_text(), 'ola')
        status, data, _ = self.call('GET', '/api/sites', cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data['sites'][0]['slug'], 'meu-site')

    def test_html_deploy_with_mock_docker(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'pagina', 'name': 'Pagina', 'kind': 'html'}, cookie=cookie)
        src = web.SITES / 'pagina/source'
        src.mkdir()
        (src / 'index.html').write_text('ola')
        docker = FakeDocker()
        with patch.object(web, 'docker', side_effect=docker):
            web.JOBS['pagina'] = 'a preparar'
            web.deploy_site('pagina')
        self.assertTrue(any('nginxinc/nginx-unprivileged:stable-alpine' in a for a in docker.calls))
        self.assertTrue(any('/config/nginx-html.conf' in arg for call in docker.calls for arg in call))
        self.assertTrue(web.load_db()['pagina']['active_release'])
        self.assertFalse(web.load_db()['pagina']['last_error'])
        self.assertTrue((web.SITES / 'pagina/releases' / web.load_db()['pagina']['active_release'] / 'index.html').exists())

    def test_react_deploy_with_mock_builder(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'reactsite', 'name': 'React Site', 'kind': 'react'}, cookie=cookie)
        src = web.SITES / 'reactsite/source'
        src.mkdir()
        (src / 'package.json').write_text('{"scripts":{"build":"vite build"}}')
        docker = FakeDocker()
        def fake_build(slug, release, script, timeout):
            build = web.SITES / slug / 'releases' / release / 'dist'
            build.mkdir()
            (build / 'index.html').write_text('react')
        with patch.object(web, 'docker', side_effect=docker), patch.object(web, 'run_builder', side_effect=fake_build):
            web.JOBS['reactsite'] = 'a preparar'
            web.deploy_site('reactsite')
        self.assertTrue(any('/dist' in arg for call in docker.calls for arg in call))
        self.assertTrue(any('/config/nginx-react.conf' in arg for call in docker.calls for arg in call))
        self.assertFalse(web.load_db()['reactsite']['last_error'])

    def test_publish_failed_build_keeps_old_release(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'pagina', 'name': 'Pagina', 'kind': 'html'}, cookie=cookie)
        src = web.SITES / 'pagina/source'
        src.mkdir()
        (src / 'index.html').write_text('version-one')
        docker = FakeDocker()
        with patch.object(web, 'docker', side_effect=docker):
            web.deploy_site('pagina')
            original_release = web.load_db()['pagina']['active_release']
            (src / 'index.html').write_text('version-two')
            docker.fail_next_run = True
            web.deploy_site('pagina')
            self.assertTrue(docker.containers['zwh-pagina']['State']['Running'])
        self.assertEqual(web.load_db()['pagina']['active_release'], original_release)
        self.assertEqual((web.SITES / 'pagina/releases' / original_release / 'index.html').read_text(), 'version-one')
        self.assertIn('forced run failure', web.load_db()['pagina']['last_error'])

    def test_publish_invalid_project_does_not_stop_live_site(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'pagina', 'name': 'Pagina', 'kind': 'html'}, cookie=cookie)
        src = web.SITES / 'pagina/source'
        src.mkdir()
        (src / 'index.html').write_text('valid')
        docker = FakeDocker()
        with patch.object(web, 'docker', side_effect=docker):
            web.deploy_site('pagina')
            (src / 'index.html').unlink()
            (src / 'other.txt').write_text('bad')
            web.deploy_site('pagina')
            self.assertTrue(docker.containers['zwh-pagina']['State']['Running'])
        self.assertIn('index.html', web.load_db()['pagina']['last_error'])

    def test_online_release_unchanged_after_file_edit(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug':'pagina', 'name':'Pagina', 'kind':'html'}, cookie=cookie)
        self.call('POST', '/api/sites/pagina/files', {'path':'index.html', 'content':'original'}, cookie=cookie)
        docker = FakeDocker()
        with patch.object(web, 'docker', side_effect=docker):
            web.deploy_site('pagina')
            release = web.load_db()['pagina']['active_release']
            self.call('POST', '/api/sites/pagina/files', {'path':'index.html', 'content':'modificado'}, cookie=cookie)
        self.assertEqual((web.SITES/'pagina/releases'/release/'index.html').read_text(), 'original')
        self.assertEqual((web.SITES/'pagina/source/index.html').read_text(), 'modificado')

    def test_online_release_unchanged_after_zip_upload(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug':'pagina', 'name':'Pagina', 'kind':'html'}, cookie=cookie)
        z1 = create_zip({'index.html': 'original'})
        z2 = create_zip({'index.html': 'modificado'})
        self.call('POST', '/api/sites/pagina/upload', z1, cookie=cookie, headers={'Content-Type':'application/zip'})
        docker = FakeDocker()
        with patch.object(web, 'docker', side_effect=docker):
            web.deploy_site('pagina')
            release = web.load_db()['pagina']['active_release']
            status, _, _ = self.call('POST', '/api/sites/pagina/upload', z2, cookie=cookie,
                                      headers={'Content-Type':'application/zip'})
        self.assertEqual(status, 200)
        self.assertEqual((web.SITES/'pagina/releases'/release/'index.html').read_text(), 'original')
        self.assertEqual((web.SITES/'pagina/source/index.html').read_text(), 'modificado')

    def test_file_manager_crud_and_traversal(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug':'files', 'name':'Files', 'kind':'html'}, cookie=cookie)
        status, data, _ = self.call('POST', '/api/sites/files/files',
            {'path':'index.html', 'content':'<h1>hey</h1>', 'op':'save'}, cookie=cookie)
        self.assertEqual(status, 200)
        status, data, _ = self.call('GET', '/api/sites/files/files?path=index.html', cookie=cookie)
        self.assertEqual(data['content'], '<h1>hey</h1>')
        status, data, _ = self.call('GET', '/api/sites/files/files', cookie=cookie)
        self.assertEqual(data['files'][0]['path'], 'index.html')
        status, data, _ = self.call('POST', '/api/sites/files/files',
            {'path':'../evil', 'content':'oops', 'op':'save'}, cookie=cookie)
        self.assertEqual(status, 400)
        status, data, _ = self.call('POST', '/api/sites/files/files',
            {'path':'index.html', 'op':'delete'}, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertFalse((web.SITES / 'files/source/index.html').exists())

    def test_csrf_header_required(self):
        status, data, _ = self.call('POST', '/api/login', {'password':web.ADMIN_PASSWORD},
                                    headers={'X-MrStore_webhost-Request': ''})
        self.assertEqual(status, 403)

    def test_missing_node_package_is_reported(self):
        cookie = self.login()
        self.call('POST', '/api/sites', {'slug': 'nodeapp', 'name': 'Node app', 'kind': 'node'}, cookie=cookie)
        src = web.SITES / 'nodeapp/source'
        src.mkdir()
        (src / 'index.js').write_text('test')
        web.JOBS['nodeapp'] = 'a preparar'
        web.deploy_site('nodeapp')
        self.assertIn('package.json', web.load_db()['nodeapp']['last_error'])
        self.assertNotIn('nodeapp', web.JOBS)

    def test_cross_origin_rejected(self):
        cookie = self.login()
        status, _, _ = self.call('POST', '/api/sites', {'slug': 'evil', 'name': 'Evil', 'kind':'php'}, cookie=cookie,
                                 headers={'Origin': 'http://evil.example'})
        self.assertEqual(status, 403)


if __name__ == '__main__':
    unittest.main()
