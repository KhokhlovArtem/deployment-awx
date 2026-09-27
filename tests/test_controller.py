"""Offline controller tests; no SSH, Ansible, environment files or private keys."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controller', ROOT / 'scripts/controller.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class InputTests(unittest.TestCase):
    def test_hosts(self):
        for value in ('192.0.2.10', 'server.example', '2001:db8::1'):
            self.assertEqual(c.host(value), value)
        for value in ('-oProxyCommand=evil', 'host;id', 'a\nb', 'a b', 'user@host', '$(id)', '',
                      'fe80::1%eth0', 'fe80::1%{{lookup}}'):
            with self.assertRaises(argparse.ArgumentTypeError):
                c.host(value)

    def test_other_inputs(self):
        for fn, values in ((c.identifier, ['root;id', '-root', 'root\n']),
                           (c.namespace, ['awx/x', 'AWX', 'awx\n']),
                           (c.port, ['0', '65536', '22;id']),
                           (c.key_path, ['relative', '/tmp/a\nb', '/tmp/{{lookup}}']),
                           (c.public_url, ['http://u:p@host', 'http://host/path',
                                           'http://host:bad', 'file:///x', 'http://host?a=b',
                                           'http://host\\other', 'http://host\n'])):
            for value in values:
                with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                    fn(value)
        self.assertEqual(c.public_url('https://[2001:db8::1]:8443/'), 'https://[2001:db8::1]:8443')

    def test_inventory_key_quoting_and_no_secrets(self):
        key = "/home/test/a 'quoted' key;echo nope"
        args = c.parser().parse_args(['install', '--host', '192.0.2.10', '--user', 'ubuntu',
                                      '--identity', key])
        data = c.inventory(args)
        target = data['awx']['hosts']['awx_target']
        tokens = shlex.split(target['ansible_ssh_common_args'])
        self.assertEqual(tokens[tokens.index('-i') + 1], key)
        self.assertIn('BatchMode=yes', tokens)
        self.assertIn('StrictHostKeyChecking=yes', tokens)
        self.assertIn('PreferredAuthentications=publickey', tokens)
        self.assertNotIn('AWX_ADMIN_PASSWORD', json.dumps(data))

    def test_destructive_confirmation_before_execution(self):
        with patch.object(c.sys, 'platform', 'linux'), patch.object(c.sys, 'version_info', (3, 12)), \
                patch.object(c, 'environment') as environment, patch.object(c, 'run') as run:
            with self.assertRaises(SystemExit):
                c.main(['uninstall', '--host', 'server', '--user', 'ubuntu'])
            environment.assert_not_called()
            run.assert_not_called()

    def test_profile_rejects_mixed_connection_options(self):
        with patch.object(c.sys, 'platform', 'linux'), patch.object(c.sys, 'version_info', (3, 12)), \
                patch.object(c, 'environment') as environment:
            for options in (['--ssh-profile', '--host', 'server'],
                            ['--ssh-profile', '--identity', '/project/identity'],
                            ['--agent-socket-file', 'temp/socket.txt']):
                with self.assertRaises(SystemExit):
                    c.main(['install'] + options)
            environment.assert_not_called()


class RuntimeTests(unittest.TestCase):
    def test_runtime_subdirectory_and_boundary(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as directory, \
                patch.object(c, 'ROOT', Path(directory)):
            env = c.environment('temp/r')
            self.assertEqual(Path(env['TMPDIR']), Path(directory) / 'temp/r')
            self.assertTrue(Path(env['ANSIBLE_LOCAL_TEMP']).is_relative_to(Path(env['TMPDIR'])))
            for value in ('/tmp', '../temp', 'temp/../outside', '.venv'):
                with self.assertRaises(ValueError):
                    c.environment(value)

    def test_runtime_environment_is_local_and_filtered(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as directory, \
                patch.object(c, 'ROOT', Path(directory)), \
                patch.dict(os.environ, {'ANSIBLE_LOG_PATH': '/outside/log', 'AWX_ADMIN_PASSWORD': 'dummy'}, clear=True):
            env = c.environment()
            self.assertNotIn('ANSIBLE_LOG_PATH', env)
            self.assertNotIn('AWX_ADMIN_PASSWORD', env)
            self.assertEqual(env['TMP'], env['TEMP'])
            self.assertTrue(Path(env['TMPDIR']).is_relative_to(Path(directory)))
            self.assertEqual(env['ANSIBLE_HOST_KEY_CHECKING'], 'True')

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as directory, patch.object(c, 'ROOT', Path(directory)):
            with patch.object(Path, 'is_symlink', return_value=True):
                with self.assertRaises(ValueError):
                    c.local_dir('temp')

    def test_secret_prompt_and_environment(self):
        env = {}
        with patch.dict(os.environ, {}, clear=True), patch.object(c.sys.stdin, 'isatty', return_value=True), \
                patch.object(c.getpass, 'getpass', return_value='test-only-password-123') as prompt:
            c.collect_secrets(env)
            self.assertEqual(prompt.call_count, 2)
        with patch.dict(os.environ, env, clear=True), patch.object(c.getpass, 'getpass') as prompt:
            result = {}
            c.collect_secrets(result)
            self.assertEqual(result, env)
            prompt.assert_not_called()

    def test_noninteractive_and_weak_password_fail_closed(self):
        for values in ({}, {'AWX_ADMIN_PASSWORD': 'short'}):
            with patch.dict(os.environ, values, clear=True), patch.object(c.sys.stdin, 'isatty', return_value=False):
                with self.assertRaises(ValueError):
                    c.collect_secrets({})

    def test_prompt_cannot_fall_back_to_echo(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(c.sys.stdin, 'isatty', return_value=True), \
                patch.object(c.getpass, 'getpass', side_effect=c.getpass.GetPassWarning):
            with self.assertRaises(ValueError):
                c.collect_secrets({})

    def test_readiness_requires_awx_json(self):
        for body, valid in ((b'<html>OK</html>', False), (b'{}', False), (b'[]', False),
                            (b'{"version":"24.6.1","instances":[],"instance_groups":[]}', True)):
            response = MagicMock()
            response.status = 200
            response.read.return_value = body
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value = response
            with patch.object(c.urllib.request, 'build_opener', return_value=opener):
                if valid:
                    c.readiness('http://server:30080', attempts=1)
                else:
                    with self.assertRaises(ValueError):
                        c.readiness('http://server:30080', attempts=1)

    def test_inventory_cleanup_on_ansible_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as directory, patch.object(c, 'ROOT', Path(directory)):
            executable = Path(directory) / '.venv/bin/ansible-playbook'
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.object(c.sys, 'platform', 'linux'), patch.object(c.sys, 'version_info', (3, 12)), \
                    patch.dict(os.environ, {}, clear=True), \
                    patch.object(c, 'run', side_effect=c.subprocess.CalledProcessError(7, ['ansible'])):
                with self.assertRaises(c.subprocess.CalledProcessError):
                    c.main(['uninstall', '--host', 'server', '--user', 'ubuntu', '--confirm-delete', 'awx'])
            self.assertFalse(list((Path(directory) / 'temp').glob('awx-*')))


if __name__ == '__main__':
    c.local_dir('temp')
    unittest.main()
