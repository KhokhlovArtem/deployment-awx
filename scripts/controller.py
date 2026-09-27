#!/usr/bin/env python3
"""Project-local controller. Never loads dotenv or reads SSH private keys."""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings

ROOT = Path(__file__).resolve().parents[1]
SSH_OPTIONS = ('-F /dev/null -o StrictHostKeyChecking=yes -o BatchMode=yes '
               '-o PreferredAuthentications=publickey -o PasswordAuthentication=no '
               '-o KbdInteractiveAuthentication=no -o ForwardAgent=no')


def host(value):
    if re.search(r'[^A-Za-z0-9.:-]', value):
        raise argparse.ArgumentTypeError('Expected an unscoped IP address or DNS hostname')
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        if len(value) <= 253 and all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p)
                                     for p in value.split('.')):
            return value
    raise argparse.ArgumentTypeError('Expected an IP address or DNS hostname')


def identifier(value):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', value):
        raise argparse.ArgumentTypeError('Invalid Linux user name')
    return value


def namespace(value):
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', value):
        raise argparse.ArgumentTypeError('Invalid namespace')
    return value


def port(value):
    try:
        number = int(value)
        if 1 <= number <= 65535:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('Port must be 1..65535')


def key_path(value):
    if not value.startswith('/') or re.search(r'[{}\x00-\x1f\x7f]', value):
        raise argparse.ArgumentTypeError('Use an absolute WSL key path without braces or control characters')
    return value


def public_url(value):
    try:
        url = urllib.parse.urlsplit(value)
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username is not None
                or url.password is not None or url.query or url.fragment or url.path not in ('', '/')
                or re.search(r'[\s\\\x00-\x1f\x7f]', value)):
            raise ValueError()
        host(url.hostname)
        if url.port is not None:
            port(str(url.port))
    except (ValueError, argparse.ArgumentTypeError):
        raise argparse.ArgumentTypeError('Use http(s)://host[:port], without credentials or path') from None
    return value.rstrip('/')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('bootstrap', 'install', 'uninstall'))
    p.add_argument('--host', type=host)
    p.add_argument('--user', type=identifier)
    p.add_argument('--port', type=port, default=22)
    p.add_argument('--identity', type=key_path)
    p.add_argument('--namespace', type=namespace, default='awx')
    p.add_argument('--nodeport', type=port, default=30080)
    p.add_argument('--public-url', type=public_url)
    p.add_argument('--ask-become-pass', '-K', action='store_true')
    p.add_argument('--confirm-delete', help='Must equal the namespace to delete it and its PVCs')
    return p


def local_dir(relative):
    """Reject symlinks (including internal ones) before creating runtime directories."""
    path = ROOT
    for component in Path(relative).parts:
        path = path / component
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError('Unsafe project runtime directory: ' + relative)
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError('Runtime directory escapes project')
        path.mkdir(exist_ok=True, mode=0o700)
    return path


def environment():
    # Deliberate allowlist: inherited Ansible configuration/callbacks cannot log secrets.
    env = {name: os.getenv(name) for name in ('PATH', 'HOME', 'USER', 'SSH_AUTH_SOCK', 'TERM')
           if os.getenv(name) is not None}
    temp = str(local_dir('temp'))
    env.update(TMP=temp, TEMP=temp, TMPDIR=temp, LANG='C.UTF-8', LC_ALL='C.UTF-8',
               ANSIBLE_CONFIG=str(ROOT / 'ansible.cfg'),
               ANSIBLE_COLLECTIONS_PATH=str(local_dir('.ansible/collections')),
               ANSIBLE_LOCAL_TEMP=str(local_dir('temp/ansible')),
               ANSIBLE_HOME=str(local_dir('.ansible')),
               XDG_CACHE_HOME=str(local_dir('temp/cache')),
               PIP_CACHE_DIR=str(local_dir('temp/pip')),
               PIP_CONFIG_FILE='/dev/null',
               ANSIBLE_HOST_KEY_CHECKING='True', ANSIBLE_DISPLAY_ARGS_TO_STDOUT='False',
               ANSIBLE_DIFF_ALWAYS='False', ANSIBLE_NOCOLOR='1')
    return env


def collect_secrets(env):
    for name in ('AWX_ADMIN_PASSWORD', 'AWX_POSTGRES_PASSWORD'):
        value = os.getenv(name)
        if not value:
            if not sys.stdin.isatty():
                raise ValueError('Configure ' + name + ' in the WSL process environment or use a terminal')
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', getpass.GetPassWarning)
                    value = getpass.getpass(name + ': ')
            except getpass.GetPassWarning:
                raise ValueError('A terminal with hidden input is required for ' + name) from None
        if len(value) < 16 or value in ('change-me-db-strong', 'change-me-strong'):
            raise ValueError(name + ' must contain at least 16 non-example characters')
        env[name] = value


def inventory(args):
    common = SSH_OPTIONS
    if args.identity:
        common += ' -o IdentitiesOnly=yes -i ' + shlex.quote(args.identity)
    return {'awx': {'hosts': {'awx_target': {
        'ansible_host': args.host, 'ansible_user': args.user, 'ansible_port': args.port,
        'ansible_connection': 'ssh', 'ansible_ssh_common_args': common,
        'ansible_ssh_args': '-C',
        'awx_namespace': args.namespace, 'awx_nodeport': args.nodeport,
        'awx_delete_confirmed': args.confirm_delete == args.namespace,
    }}}}


def run(argv, env):
    subprocess.run([str(item) for item in argv], cwd=ROOT, env=env, check=True)


def readiness(url, attempts=20):
    # Direct route from WSL; do not silently follow redirects to login/proxy pages.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for attempt in range(attempts):
        try:
            with opener.open(url + '/api/v2/ping/', timeout=15) as response:
                data = json.loads(response.read(1048576))
                if (response.status == 200 and isinstance(data, dict)
                        and isinstance(data.get('version'), str) and data['version']
                        and isinstance(data.get('instances'), list)
                        and isinstance(data.get('instance_groups'), list)):
                    return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        if attempt + 1 < attempts:
            time.sleep(15)
    raise ValueError('AWX ping JSON unavailable from WSL at ' + url)


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if sys.platform != 'linux' or sys.version_info < (3, 12):
        p.error('Run under WSL Ubuntu with Python 3.12+')
    if args.mode != 'bootstrap' and (not args.host or not args.user):
        p.error('--host and --user are required')
    if not 30000 <= args.nodeport <= 32767:
        p.error('--nodeport must be 30000..32767')
    if args.mode == 'uninstall' and args.confirm_delete != args.namespace:
        p.error('Destructive namespace/PVC deletion requires --confirm-delete ' + args.namespace)
    for name in ('AWX_RECEPTOR_CA_CERT_PATH', 'AWX_RECEPTOR_CA_KEY_PATH', 'AWX_RECEPTOR_CA_GENERATION'):
        if os.getenv(name):
            p.error('Custom Receptor CA is not supported by this entry point; unset ' + name)
    env = environment()
    venv = local_dir('.venv')
    if args.mode == 'bootstrap':
        run([sys.executable, '-m', 'venv', venv], env)
        run([venv / 'bin/python', '-m', 'pip', 'install', '-r', ROOT / 'requirements.txt'], env)
        run([venv / 'bin/ansible-galaxy', 'collection', 'install', '-r', ROOT / 'requirements.yml',
             '-p', ROOT / '.ansible/collections'], env)
        print('Controller ready: .venv and .ansible/collections')
        return 0
    executable = venv / 'bin/ansible-playbook'
    if not executable.is_file():
        raise ValueError('Run bash scripts/bootstrap.sh in WSL first')
    if args.mode == 'install':
        collect_secrets(env)
    with tempfile.TemporaryDirectory(prefix='awx-', dir=env['TMPDIR']) as directory:
        inv = Path(directory) / 'inventory.json'
        inv.write_text(json.dumps(inventory(args)), encoding='utf-8')
        command = [executable, '-i', inv, ROOT / 'playbooks' / (args.mode + '.yml')]
        if args.ask_become_pass:
            command.append('--ask-become-pass')
        run(command, env)
    if args.mode == 'install':
        address = '[' + args.host + ']' if ':' in args.host else args.host
        url = args.public_url or f'http://{address}:{args.nodeport}'
        readiness(url)
        print('AWX API verified from WSL: ' + url + ' (login: admin)')
        print('Windows/browser connectivity must be checked separately.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        sys.exit(130)
