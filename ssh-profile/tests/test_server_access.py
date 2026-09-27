"""Offline profile/adapter tests. All filesystem fixtures stay in project temp/."""

import argparse
import base64
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml


BUNDLE = Path(__file__).resolve().parents[1]
# Tests may run from a consuming project's root or from the bundle itself.
ROOT = Path.cwd().resolve()
if not BUNDLE.is_relative_to(ROOT):
    raise RuntimeError("Run bundle tests from the consuming project root or bundle directory")
spec = importlib.util.spec_from_file_location("server_access", BUNDLE / "server_access.py")
access = importlib.util.module_from_spec(spec)
spec.loader.exec_module(access)


def key(byte):
    fields = (b"ssh-ed25519", bytes([byte]) * 32)
    blob = b"".join(struct.pack(">I", len(field)) + field for field in fields)
    return "ssh-ed25519 " + base64.b64encode(blob).decode()


HOST_KEY, USER_KEY, OTHER_KEY = key(1), key(2), key(3)


def profile():
    return access.make_profile("test-server", "192.0.2.10", 22, "alice",
                               access.fingerprint(USER_KEY), HOST_KEY)


def result(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)


class ProfileTests(unittest.TestCase):
    def test_profile_roundtrip_has_no_machine_local_paths(self):
        original = profile()
        normalized = access.validate_profile(access.parse_yaml(yaml.safe_dump(original)))
        self.assertEqual(normalized, original)
        self.assertNotIn("SSH_AUTH_SOCK", yaml.safe_dump(normalized))
        self.assertNotIn("ansible_", yaml.safe_dump(normalized))

    def test_strict_schema_rejects_secret_and_execution_fields(self):
        for field in ("password", "private_key", "proxy_command", "socket_path", "ansible_password"):
            value = profile()
            value["ssh"][field] = "not-allowed"
            with self.subTest(field=field), self.assertRaises(access.AccessError):
                access.validate_profile(value)

    def test_invalid_version_port_and_privileges(self):
        cases = [("version", None, 2), ("version", None, True),
                 ("server", "port", True), ("server", "port", "22"),
                 ("server", "port", 0), ("server", "port", 65536),
                 ("privileges", "password_required", True),
                 ("privileges", "password_required", 0), ("privileges", "method", "su")]
        for parent, child, value in cases:
            data = profile()
            if child is None:
                data[parent] = value
            else:
                data[parent][child] = value
            with self.subTest(parent=parent, child=child, value=value), self.assertRaises(access.AccessError):
                access.validate_profile(data)

    def test_no_password_auth_or_relaxed_host_verification(self):
        for branch, field, value in (("authentication", "method", "password"),
                                     ("verification", "policy", "accept-new"),
                                     ("authentication", "key_fingerprint", "MD5:bad")):
            data = profile()
            data["ssh"][branch][field] = value
            with self.subTest(field=field), self.assertRaises(access.AccessError):
                access.validate_profile(data)

    def test_hosts_names_and_users_cannot_inject_options_or_templates(self):
        for parent, field, value in (("server", "host", "-oProxyCommand=id"),
                                     ("server", "host", "host\nUser root"),
                                     ("server", "host", "{{ lookup('pipe','id') }}"),
                                     ("server", "host", "fe80::1%eth0"),
                                     ("server", "name", "all"), ("server", "name", "a b"),
                                     ("ssh", "user", "root"), ("ssh", "user", "a;id")):
            data = profile()
            data[parent][field] = value
            with self.subTest(parent=parent, field=field), self.assertRaises(access.AccessError):
                access.validate_profile(data)

    def test_dns_ipv6_and_nonstandard_port(self):
        self.assertEqual(access.normalize_host("SERVER.Example.org."), "server.example.org")
        data = profile()
        data["server"].update(host="2001:db8::1", port=2222)
        self.assertEqual(access.host_reference(access.validate_profile(data)), "[2001:db8::1]:2222")

    def test_duplicate_yaml_and_unsafe_tags_fail(self):
        for text in ("version: 1\nversion: 2\n", "!!python/object:object {}", "[unterminated",
                     "1: value", "---\na: 1\n---\na: 2", "[" * 1500 + "]" * 1500):
            with self.subTest(text=text), self.assertRaises(access.AccessError):
                access.parse_yaml(text)

    def test_public_key_normalization_and_fingerprint(self):
        self.assertEqual(access.normalize_key(USER_KEY + " comment"), USER_KEY)
        self.assertEqual(access.fingerprint(USER_KEY), access.fingerprint(USER_KEY + " comment"))
        for value in (USER_KEY + "\n", USER_KEY.replace("ssh-ed25519 ", "ssh-rsa "),
                      "ssh-ed25519 !!!", "command=whoami " + USER_KEY, "PRIVATE KEY"):
            with self.subTest(value=value), self.assertRaises(access.AccessError):
                access.normalize_key(value)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "temp"
        if parent.is_symlink():
            raise RuntimeError("Refusing linked test temp")
        parent.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="profile-unit-", dir=parent)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.workspace = access.Workspace(self.root)

    def test_bundle_defaults_follow_script_not_original_workspace(self):
        script = self.root / "ssh-profile/server_access.py"
        for command in ("validate", "check", "ansible"):
            args = access.bundle_defaults(access.parser().parse_args([command]), self.workspace, script)
            self.assertEqual(args.profile, str(self.root / "ssh-profile/server-access.local.yml"))
        self.assertEqual(args.output_dir, "temp/ssh-profile")

    def test_bundle_explicit_profile_and_export_default(self):
        script = self.root / "ssh-profile/server_access.py"
        args = access.bundle_defaults(access.parser().parse_args(["check", "--profile", "other.local.yml"]),
                                      self.workspace, script)
        self.assertEqual(args.profile, "other.local.yml")
        args = access.bundle_defaults(access.parser().parse_args([
            "export", "--name", "test-server", "--user", "alice", "--known-hosts", "known_hosts",
            "--key-fingerprint", access.fingerprint(USER_KEY)]), self.workspace, script)
        self.assertEqual(args.output, str(self.root / "ssh-profile/server-access.local.yml"))

    def test_bundle_outside_consuming_workspace_is_rejected(self):
        with self.assertRaises(access.AccessError):
            access.bundle_defaults(access.parser().parse_args(["check"]), self.workspace,
                                    self.root.parent / "other-project/server_access.py")

    def test_reject_external_and_secret_paths_before_reading(self):
        for value in ("../outside.yml", str(self.root.parent / "outside.yml"),
                      ".env", ".env.example", "nested/.env.yaml", "private.pem", "private.key"):
            with self.subTest(path=value), self.assertRaises(access.AccessError):
                self.workspace.read_text(value)

    def test_reject_resolved_escape_or_secret(self):
        for target in (self.root.parent / "outside.yml", self.root / ".env.yaml"):
            with patch.object(access.Path, "resolve", return_value=target):
                with self.assertRaises(access.AccessError):
                    self.workspace.path("innocent.yml")

    def test_material_is_scoped_and_removed_after_check(self):
        with access.material(self.workspace, profile(), USER_KEY) as files:
            folder = files["ssh_config"].parent
            self.assertTrue(folder.is_relative_to(self.root / "temp"))
            config = files["ssh_config"].read_text()
            for setting in ("StrictHostKeyChecking yes", "PasswordAuthentication no", "BatchMode yes",
                            "IdentityAgent SSH_AUTH_SOCK", "IdentitiesOnly yes", "ForwardAgent no",
                            "ControlMaster no", "GlobalKnownHostsFile /dev/null", "ProxyCommand none"):
                self.assertIn(setting, config)
            self.assertEqual(files["known_hosts"].read_text(), "192.0.2.10 " + HOST_KEY + "\n")
            self.assertEqual(files["identity.pub"].read_text(), USER_KEY + "\n")
        self.assertFalse(folder.exists())

    def test_ssh_config_paths_escape_spaces_and_percent(self):
        self.assertEqual(access.config_quote('/project/a b%/identity.pub'), '"/project/a b%%/identity.pub"')

    def test_runtime_discards_bootstrap_password_environment(self):
        with patch.dict(os.environ, {"SSH_AUTH_SOCK": "/agent/socket", "BOOTSTRAP_PASSWORD": "dummy",
                                     "BOOTSTRAP_BECOME_PASSWORD": "dummy", "SSHPASS": "dummy",
                                     "SSH_ASKPASS": "/unused"}, clear=True), patch.object(access.os, "name", "posix"):
            env = access.runtime_environment(self.workspace)
        for name in ("BOOTSTRAP_PASSWORD", "BOOTSTRAP_BECOME_PASSWORD", "SSHPASS", "SSH_ASKPASS"):
            self.assertNotIn(name, env)
        self.assertEqual(env["TMPDIR"], str(self.root / "temp"))

    def test_missing_agent_stops_without_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(access.os, "name", "posix"):
            with self.assertRaises(access.AccessError):
                access.runtime_environment(self.workspace)

    def test_check_selects_identity_and_runs_only_fixed_readonly_command(self):
        with patch.object(access, "run_local", side_effect=[result(USER_KEY + " user-comment\n"),
                                                           result("alice\n0\n")]) as run:
            self.assertEqual(access.verify_connection(self.workspace, profile(), {}), USER_KEY)
        self.assertEqual(run.call_args_list[0].args[0], ["ssh-add", "-L"])
        self.assertEqual(run.call_args_list[1].args[0][-2:],
                         ["test-server", "/usr/bin/id -un && /usr/bin/sudo -n /usr/bin/id -u"])

    def test_wrong_agent_identity_stops_before_ssh(self):
        with patch.object(access, "run_local", return_value=result(OTHER_KEY)) as run:
            with self.assertRaises(access.AccessError):
                access.verify_connection(self.workspace, profile(), {})
        self.assertEqual(run.call_count, 1)

    def test_failed_host_auth_or_sudo_never_exposes_raw_output(self):
        for stderr, code, stdout in (("Host key verification failed. sensitive endpoint", 255, ""),
                                     ("Permission denied: sensitive endpoint", 255, ""),
                                     ("sudo: a password is required sensitive endpoint", 1, "alice\n"),
                                     ("sensitive endpoint", 1, ""), ("", 0, "root\n0\n")):
            with patch.object(access, "run_local", side_effect=[result(USER_KEY), result(stdout, stderr, code)]):
                with self.subTest(code=code), self.assertRaises(access.AccessError) as caught:
                    access.verify_connection(self.workspace, profile(), {})
                self.assertNotIn("sensitive endpoint", str(caught.exception))

    def test_known_hosts_supports_hashed_records(self):
        (self.root / "known_hosts").write_text("placeholder")
        with patch.object(access, "run_local", return_value=result("# matched\n|1|hash|hash " + HOST_KEY + "\n")) as run:
            key_value = access.trusted_key(self.workspace, {}, "known_hosts", "192.0.2.10", 22)
        self.assertEqual(key_value, HOST_KEY)
        self.assertEqual(run.call_args.args[0][:3], ["ssh-keygen", "-F", "192.0.2.10"])

    def test_revoked_ca_or_conflicting_host_records_fail(self):
        (self.root / "known_hosts").write_text("placeholder")
        for output in ("@revoked host " + HOST_KEY, "@cert-authority host " + HOST_KEY,
                       "host " + HOST_KEY + "\nhost " + OTHER_KEY, ""):
            with patch.object(access, "run_local", return_value=result(output)):
                with self.subTest(output=output), self.assertRaises(access.AccessError):
                    access.trusted_key(self.workspace, {}, "known_hosts", "192.0.2.10", 22)

    def export_args(self):
        return argparse.Namespace(output="server-access.local.yml", host="192.0.2.10", port=22,
                                  name="test-server", user="alice", known_hosts="known_hosts",
                                  team_file=None, key_fingerprint=access.fingerprint(USER_KEY))

    def test_export_is_verified_and_contains_only_profile_fields(self):
        with patch.object(access, "agent_keys", return_value={access.fingerprint(USER_KEY): USER_KEY}), \
             patch.object(access, "trusted_key", return_value=HOST_KEY), \
             patch.object(access, "verify_connection", return_value=USER_KEY) as verify:
            exported = access.export_profile(self.workspace, self.export_args(), {})
        verify.assert_called_once()
        self.assertEqual(exported, profile())
        self.assertEqual(self.workspace.load_profile("server-access.local.yml"), profile())

    def test_failed_verification_does_not_export(self):
        with patch.object(access, "agent_keys", return_value={access.fingerprint(USER_KEY): USER_KEY}), \
             patch.object(access, "trusted_key", return_value=HOST_KEY), \
             patch.object(access, "verify_connection", side_effect=access.AccessError("Check failed")):
            with self.assertRaises(access.AccessError):
                access.export_profile(self.workspace, self.export_args(), {})
        self.assertFalse((self.root / "server-access.local.yml").exists())

    def test_existing_export_not_overwritten(self):
        target = self.root / "server-access.local.yml"
        target.write_text("keep existing")
        with patch.object(access, "verify_connection") as verify:
            with self.assertRaises(access.AccessError):
                access.export_profile(self.workspace, self.export_args(), {})
        verify.assert_not_called()
        self.assertEqual(target.read_text(), "keep existing")

    def test_team_identity_selection(self):
        data = {"users": [{"username": "alice", "state": "present", "sudo": True, "ssh_keys": [USER_KEY]}]}
        (self.root / "users.yaml").write_text(yaml.safe_dump(data))
        args = self.export_args()
        args.team_file, args.key_fingerprint = "users.yaml", None
        with patch.object(access, "agent_keys", return_value={access.fingerprint(USER_KEY): USER_KEY}), \
             patch.object(access, "trusted_key", return_value=HOST_KEY), \
             patch.object(access, "verify_connection", return_value=USER_KEY):
            self.assertEqual(access.export_profile(self.workspace, args, {}), profile())

    def test_inventory_is_regenerated_in_consuming_workspace(self):
        with patch.object(access, "verify_connection", return_value=USER_KEY):
            inventory = access.generate_ansible(self.workspace, profile(), "temp/access", {})
        variables = inventory["all"]["hosts"]["test-server"]
        self.assertNotIn("ansible_password", variables)
        self.assertNotIn("ansible_become_password", variables)
        self.assertNotIn("ansible_become", variables)  # -b/playbook controls escalation.
        self.assertEqual(variables["ansible_become_flags"], "-H -S -n")
        self.assertIn(str(self.root / "temp/access/ssh_config"), variables["ansible_ssh_args"])
        self.assertEqual(yaml.safe_load((self.root / "temp/access/inventory.yml").read_text()), inventory)

    def test_adapter_cannot_write_outside_temp_or_overwrite(self):
        (self.root / "temp/existing").mkdir(parents=True)
        for path in ("artifacts", "../outside", "temp", "temp/existing"):
            with patch.object(access, "verify_connection") as verify:
                with self.subTest(path=path), self.assertRaises(access.AccessError):
                    access.generate_ansible(self.workspace, profile(), path, {})
                verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
