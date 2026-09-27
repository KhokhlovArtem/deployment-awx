#!/usr/bin/env python3
"""Portable ssh-profile folder. Run from the consuming project root.

Runtime: Python 3.11+, PyYAML, Linux/WSL and OpenSSH. No .env loader, private-key
reader, password authentication, host-key discovery or global configuration edits.
"""

import argparse
import base64
import binascii
from contextlib import contextmanager
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import tempfile

import yaml


KEY_TYPES = ("ssh-ed25519", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384",
             "ecdsa-sha2-nistp521", "ssh-rsa")
MAX_INPUT = 256 * 1024


class AccessError(Exception):
    """Only fixed, safe messages: never include subprocess output or credentials."""


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise AccessError("YAML mapping keys must be unique strings.")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def parse_yaml(text):
    if len(text.encode("utf-8")) > MAX_INPUT:
        raise AccessError("Input document is too large.")
    try:
        return yaml.load(text, Loader=UniqueLoader)
    except (yaml.YAMLError, RecursionError):
        raise AccessError("Invalid YAML; raw input is not logged.") from None


def exact_keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise AccessError("Profile fields do not match the version 1 schema.")


def normalize_host(value):
    if not isinstance(value, str) or not value or len(value) > 253 or "%" in value:
        raise AccessError("Invalid server host.")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        labels = value.rstrip(".").split(".")
        if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                   for label in labels):
            raise AccessError("Invalid server host.") from None
        return value.rstrip(".").lower()


def normalize_key(value):
    if (not isinstance(value, str) or len(value) > 16384
            or any(ord(char) < 32 and char != "\t" or ord(char) == 127 for char in value)):
        raise AccessError("Expected a single OpenSSH public key line.")
    parts = value.strip().split()
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        raise AccessError("Unsupported public key type or key options.")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (ValueError, binascii.Error):
        raise AccessError("Invalid public key encoding.") from None
    remainder, fields = blob, []
    while remainder:
        if len(remainder) < 4:
            raise AccessError("Truncated public key.")
        length = struct.unpack(">I", remainder[:4])[0]
        if length > len(remainder) - 4:
            raise AccessError("Truncated public key field.")
        fields.append(remainder[4:4 + length])
        remainder = remainder[4 + length:]
    if not fields or fields[0] != parts[0].encode("ascii"):
        raise AccessError("Public key type does not match its payload.")
    if parts[0] == "ssh-ed25519":
        valid = len(fields) == 2 and len(fields[1]) == 32
    elif parts[0] == "ssh-rsa":
        valid = (len(fields) == 3 and bool(fields[1]) and bool(fields[2]))
        if valid:
            exponent, modulus = (int.from_bytes(field, "big") for field in fields[1:])
            valid = (not fields[1][0] & 128 and not fields[2][0] & 128 and exponent >= 3
                     and exponent % 2 == 1 and modulus.bit_length() >= 2048 and modulus % 2 == 1)
    else:
        curve = parts[0].removeprefix("ecdsa-sha2-")
        size = {"nistp256": 65, "nistp384": 97, "nistp521": 133}[curve]
        valid = (len(fields) == 3 and fields[1] == curve.encode("ascii")
                 and len(fields[2]) == size and fields[2][:1] == b"\x04")
    if not valid:
        raise AccessError("Malformed or weak public key.")
    return parts[0] + " " + base64.b64encode(blob).decode("ascii")


def fingerprint(public_key):
    payload = normalize_key(public_key).split()[1]
    return "SHA256:" + base64.b64encode(hashlib.sha256(base64.b64decode(payload)).digest()).decode().rstrip("=")


def validate_profile(profile):
    exact_keys(profile, ("version", "server", "ssh", "privileges"))
    if type(profile["version"]) is not int or profile["version"] != 1:
        raise AccessError("Unsupported profile version.")
    server, ssh, privileges = profile["server"], profile["ssh"], profile["privileges"]
    exact_keys(server, ("name", "host", "port"))
    if (not isinstance(server["name"], str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", server["name"])
            or server["name"] in {"all", "ungrouped", "localhost"}):
        raise AccessError("Invalid server alias.")
    host = normalize_host(server["host"])
    if type(server["port"]) is not int or not 1 <= server["port"] <= 65535:
        raise AccessError("Invalid server port.")
    exact_keys(ssh, ("user", "authentication", "verification"))
    if (not isinstance(ssh["user"], str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", ssh["user"])
            or ssh["user"] in {"root", "nobody"}):
        raise AccessError("Expected a personal or explicitly provisioned service account.")
    auth, verification = ssh["authentication"], ssh["verification"]
    exact_keys(auth, ("method", "key_fingerprint"))
    if (auth["method"] != "agent" or not isinstance(auth["key_fingerprint"], str)
            or not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", auth["key_fingerprint"])):
        raise AccessError("Expected an SSH-agent identity with a SHA256 fingerprint.")
    exact_keys(verification, ("policy", "host_public_key"))
    if verification["policy"] != "strict":
        raise AccessError("Strict host key verification is required.")
    host_key = normalize_key(verification["host_public_key"])
    exact_keys(privileges, ("method", "password_required"))
    if privileges["method"] != "sudo" or privileges["password_required"] is not False:
        raise AccessError("Version 1 requires passwordless sudo; passwords are not supported.")
    return {"version": 1, "server": {**server, "host": host}, "ssh": {
        "user": ssh["user"], "authentication": dict(auth),
        "verification": {"policy": "strict", "host_public_key": host_key}},
        "privileges": dict(privileges)}


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if any(char in str(self.root) for char in ("\n", "\r", "\x00", "{{", "{%")):
            raise AccessError("Unsupported workspace path.")

    def path(self, value):
        given = Path(value)
        for component in given.parts:
            if component.lower().startswith(".env") or component.lower().endswith((".pem", ".key")):
                raise AccessError("Secret file paths are not accepted.")
        path = (self.root / given).resolve()
        if not path.is_relative_to(self.root):
            raise AccessError("Path escapes the current project.")
        for component in path.relative_to(self.root).parts:
            if component.lower().startswith(".env") or component.lower().endswith((".pem", ".key")):
                raise AccessError("Resolved secret file paths are not accepted.")
        return path

    def read_text(self, value):
        path = self.path(value)
        if not path.is_file() or path.stat().st_size > MAX_INPUT:
            raise AccessError("Required local input is missing or too large.")
        return path.read_text(encoding="utf-8")

    def temp(self):
        path = self.root / "temp"
        if path.is_symlink():
            raise AccessError("Refusing a linked temp directory.")
        path.mkdir(exist_ok=True)
        return path

    def load_profile(self, value):
        return validate_profile(parse_yaml(self.read_text(value)))


def run_local(argv, workspace, env, timeout=60):
    try:
        return subprocess.run(argv, cwd=workspace.root, env=env, capture_output=True,
                              text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        raise AccessError("Required OpenSSH executable is not available.") from None
    except subprocess.TimeoutExpired:
        raise AccessError("Connection check timed out; raw output is withheld.") from None


def runtime_environment(workspace, socket_file=None):
    if os.name != "posix":
        raise AccessError("Network operations require Linux or WSL; native Windows supports validate only.")
    env = os.environ.copy()
    for name in ("TMPDIR", "TMP", "TEMP"):
        env[name] = str(workspace.temp())
    if socket_file:
        socket = workspace.read_text(socket_file).strip()
        if not socket.startswith("/") or any(ord(char) < 32 for char in socket):
            raise AccessError("Invalid SSH-agent socket reference.")
        env["SSH_AUTH_SOCK"] = socket
    if not env.get("SSH_AUTH_SOCK"):
        raise AccessError("Missing variable: SSH_AUTH_SOCK. Start from the terminal with the active agent.")
    # This tool must never need bootstrap credentials, askpass or inherited passwords.
    for name in tuple(env):
        if name.startswith("BOOTSTRAP_") or name in {"SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "SSHPASS"}:
            env.pop(name)
    return env


def agent_keys(workspace, env):
    result = run_local(["ssh-add", "-L"], workspace, env, timeout=15)
    if result.returncode != 0:
        raise AccessError("SSH-agent is unavailable or contains no identities.")
    keys = {}
    for line in result.stdout.splitlines():
        if line.split() and line.split()[0] in KEY_TYPES:
            key = normalize_key(line)
            keys[fingerprint(key)] = key
    return keys


def host_reference(profile):
    host, port = profile["server"]["host"], profile["server"]["port"]
    return host if port == 22 else f"[{host}]:{port}"


def trusted_key(workspace, env, known_hosts, host, port):
    source = workspace.path(known_hosts)
    if not source.is_file() or source.stat().st_size > MAX_INPUT:
        raise AccessError("Trusted known_hosts input is missing or too large.")
    reference = host if port == 22 else f"[{host}]:{port}"
    result = run_local(["ssh-keygen", "-F", reference, "-f", str(source)], workspace, env)
    if result.returncode != 0:
        raise AccessError("Trusted known_hosts entry for this endpoint was not found.")
    by_type = {}
    for line in result.stdout.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0].startswith("@"):
            raise AccessError("Marked/revoked/CA known_hosts records need manual review; not supported in version 1.")
        if len(parts) < 3 or parts[1] not in KEY_TYPES:
            raise AccessError("Unsupported trusted host record.")
        key = normalize_key(" ".join(parts[1:3]))
        by_type.setdefault(parts[1], set()).add(key)
    if not by_type or any(len(keys) != 1 for keys in by_type.values()):
        raise AccessError("Missing or conflicting host keys; review the trusted input.")
    return next(next(iter(by_type[kind])) for kind in KEY_TYPES if kind in by_type)


def config_quote(path):
    # OpenSSH path options perform percent-token expansion, even inside quotes.
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def write_material(directory, profile, identity):
    directory = Path(directory)
    paths = {name: directory / name for name in ("known_hosts", "identity.pub", "ssh_config")}
    host_key = profile["ssh"]["verification"]["host_public_key"]
    algorithm = host_key.split()[0]
    algorithms = "rsa-sha2-512,rsa-sha2-256" if algorithm == "ssh-rsa" else algorithm
    config = [f'Host {profile["server"]["name"]}',
              f'  HostName {profile["server"]["host"]}', f'  Port {profile["server"]["port"]}',
              f'  User {profile["ssh"]["user"]}',
              "  StrictHostKeyChecking yes", "  GlobalKnownHostsFile /dev/null",
              "  UserKnownHostsFile " + config_quote(paths["known_hosts"]),
              "  IdentityFile " + config_quote(paths["identity.pub"]),
              "  IdentityAgent SSH_AUTH_SOCK", "  IdentitiesOnly yes",
              "  HostKeyAlgorithms " + algorithms,
              "  UpdateHostKeys no", "  VerifyHostKeyDNS no", "  BatchMode yes",
              "  PreferredAuthentications publickey", "  PubkeyAuthentication yes",
              "  PasswordAuthentication no", "  KbdInteractiveAuthentication no",
              "  ForwardAgent no", "  ForwardX11 no", "  ClearAllForwardings yes",
              "  ControlMaster no", "  ControlPersist no", "  ControlPath none",
              "  ConnectionAttempts 1", "  ConnectTimeout 15", "  ServerAliveInterval 15",
              "  ServerAliveCountMax 2", "  RequestTTY no", "  LogLevel ERROR",
              "  PermitLocalCommand no", "  ProxyCommand none", "  ProxyJump none",
              "  CanonicalizeHostname no"]
    contents = {"known_hosts": host_reference(profile) + " " + host_key + "\n",
                "identity.pub": identity + "\n", "ssh_config": "\n".join(config) + "\n"}
    for name, content in contents.items():
        with paths[name].open("x", encoding="utf-8") as stream:
            stream.write(content)
        paths[name].chmod(0o600)
    return paths


@contextmanager
def material(workspace, profile, identity):
    with tempfile.TemporaryDirectory(prefix="server-access-", dir=workspace.temp()) as directory:
        yield write_material(directory, profile, identity)


def verify_connection(workspace, profile, env):
    keys = agent_keys(workspace, env)
    identity = keys.get(profile["ssh"]["authentication"]["key_fingerprint"])
    if identity is None:
        raise AccessError("The profile's personal key is not loaded in this SSH-agent.")
    with material(workspace, profile, identity) as files:
        result = run_local(["ssh", "-F", str(files["ssh_config"]), profile["server"]["name"],
                            "/usr/bin/id -un && /usr/bin/sudo -n /usr/bin/id -u"],
                           workspace, env, timeout=60)
        if result.returncode != 0:
            if any(token in result.stderr for token in ("REMOTE HOST IDENTIFICATION HAS CHANGED",
                                                        "Host key verification failed", "strict checking")):
                raise AccessError("Server host key verification failed. Trust was NOT changed.")
            if "Permission denied" in result.stderr:
                raise AccessError("Personal public-key authentication was rejected.")
            if "a password is required" in result.stderr:
                raise AccessError("The account does not have the required passwordless sudo.")
            raise AccessError("SSH/sudo check failed; raw connection output is withheld.")
        if result.stdout.splitlines() != [profile["ssh"]["user"], "0"]:
            raise AccessError("Unexpected remote identity or sudo result.")
    return identity


def make_profile(name, host, port, user, identity_fingerprint, host_key):
    return validate_profile({"version": 1, "server": {"name": name, "host": host, "port": port},
        "ssh": {"user": user, "authentication": {"method": "agent", "key_fingerprint": identity_fingerprint},
                "verification": {"policy": "strict", "host_public_key": host_key}},
        "privileges": {"method": "sudo", "password_required": False}})


def export_profile(workspace, args, env):
    output = workspace.path(args.output)
    if not output.name.endswith((".local.yml", ".local.yaml")):
        raise AccessError("Export filename must end in .local.yml or .local.yaml (ignored by Git).")
    if output.exists() or not output.parent.is_dir():
        raise AccessError("Export destination already exists or its parent is missing; no overwrite is performed.")
    supplied_host = args.host or os.getenv("BOOTSTRAP_HOST")
    if not supplied_host:
        raise AccessError("Missing variable: BOOTSTRAP_HOST. Configure it or supply --host.")
    host = normalize_host(supplied_host)
    try:
        port = int(args.port if args.port is not None else (os.getenv("BOOTSTRAP_PORT") or "22"))
    except ValueError:
        raise AccessError("Invalid port; check --port or BOOTSTRAP_PORT.") from None
    if not 1 <= port <= 65535:
        raise AccessError("Invalid port; check --port or BOOTSTRAP_PORT.")
    keys = agent_keys(workspace, env)
    if args.team_file:
        document = parse_yaml(workspace.read_text(args.team_file))
        if not isinstance(document, dict) or not isinstance(document.get("users"), list):
            raise AccessError("Team document must contain a users list.")
        accounts = [u for u in document["users"] if isinstance(u, dict) and u.get("username") == args.user]
        if (len(accounts) != 1 or accounts[0].get("state", "present") != "present"
                or accounts[0].get("sudo", True) is not True
                or not isinstance(accounts[0].get("ssh_keys"), list)):
            raise AccessError("Expected one active administrative team account with public keys.")
        matches = {fingerprint(key) for key in accounts[0]["ssh_keys"]} & set(keys)
        if len(matches) != 1:
            raise AccessError("Team account must match exactly one agent identity; select a fingerprint explicitly instead.")
        selected = next(iter(matches))
    else:
        selected = args.key_fingerprint
        if selected not in keys:
            raise AccessError("Selected key fingerprint is not available in the SSH-agent.")
    profile = make_profile(args.name, host, port, args.user, selected,
                           trusted_key(workspace, env, args.known_hosts, host, port))
    verify_connection(workspace, profile, env)
    with output.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(profile, stream, sort_keys=False)
    output.chmod(0o600)
    return profile


def ansible_inventory(profile, ssh_config):
    return {"all": {"hosts": {profile["server"]["name"]: {
        "ansible_connection": "ssh", "ansible_user": profile["ssh"]["user"],
        "ansible_port": profile["server"]["port"],
        "ansible_ssh_args": shlex.join(["-F", str(ssh_config)]),
        "ansible_ssh_common_args": "", "ansible_ssh_extra_args": "",
        "ansible_ssh_transfer_method": "piped", "ansible_python_interpreter": "auto_silent",
        "ansible_become_method": "ansible.builtin.sudo", "ansible_become_flags": "-H -S -n",
    }}}}


def generate_ansible(workspace, profile, output_dir, env):
    output = workspace.path(output_dir)
    temp = workspace.temp()
    if not output.is_relative_to(temp) or output == temp or output.exists():
        raise AccessError("Ansible output must be a NEW directory under this project's temp/.")
    identity = verify_connection(workspace, profile, env)
    output.mkdir(parents=True, mode=0o700)
    files = write_material(output, profile, identity)
    inventory = ansible_inventory(profile, files["ssh_config"])
    with (output / "inventory.yml").open("x", encoding="utf-8") as stream:
        yaml.safe_dump(inventory, stream, sort_keys=False)
    (output / "inventory.yml").chmod(0o600)
    return inventory


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate a profile offline; no agent or network required")
    validate.add_argument("--profile", help="Default: server-access.local.yml beside this script")
    export = sub.add_parser("export", help="Export only AFTER a successful pinned key login and sudo check")
    export.add_argument("--name", required=True)
    export.add_argument("--host", help="IP/DNS; otherwise use BOOTSTRAP_HOST from process environment")
    export.add_argument("--port", type=int)
    export.add_argument("--user", required=True)
    export.add_argument("--known-hosts", required=True)
    selector = export.add_mutually_exclusive_group(required=True)
    selector.add_argument("--team-file")
    selector.add_argument("--key-fingerprint")
    export.add_argument("--output", help="Default: server-access.local.yml beside this script")
    check = sub.add_parser("check", help="Verify pinned SSH identity and passwordless sudo, read-only")
    check.add_argument("--profile", help="Default: server-access.local.yml beside this script")
    ansible = sub.add_parser("ansible", help="Verify access and generate project-local Ansible connection artifacts")
    ansible.add_argument("--profile", help="Default: server-access.local.yml beside this script")
    ansible.add_argument("--output-dir", default="temp/ssh-profile",
                         help="New project-local directory; default: temp/ssh-profile")
    for command in (export, check, ansible):
        command.add_argument("--agent-socket-file", help="Optional local socket reference; never stored in the profile")
    return result


def bundle_defaults(args, workspace, script_file=__file__):
    """Locate the transferred profile by the script, never by the old project path."""
    default_profile = workspace.path(Path(script_file).resolve().parent / "server-access.local.yml")
    if args.command == "export":
        if args.output is None:
            args.output = str(default_profile)
    elif args.profile is None:
        args.profile = str(default_profile)
    return args


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        workspace = Workspace(Path.cwd())
        args = bundle_defaults(args, workspace)
        if args.command == "validate":
            workspace.load_profile(args.profile)
            print("Profile schema valid. No connection was attempted.")
            return 0
        env = runtime_environment(workspace, args.agent_socket_file)
        print("Checking the selected SSH-agent identity, pinned server key and passwordless sudo...", flush=True)
        if args.command == "export":
            export_profile(workspace, args, env)
            print("Verified profile exported. No passwords or private keys were included.")
        else:
            profile = workspace.load_profile(args.profile)
            if args.command == "check":
                verify_connection(workspace, profile, env)
                print("Personal SSH identity and passwordless sudo verified. Server settings were not changed.")
            else:
                generate_ansible(workspace, profile, args.output_dir, env)
                print("Access verified; Ansible inventory and pinned SSH configuration generated under temp/.")
        return 0
    except AccessError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        print("ERROR: Local input or runtime failure; raw data is not logged.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
