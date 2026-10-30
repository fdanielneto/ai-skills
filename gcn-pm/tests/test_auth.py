import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import auth  # noqa: E402

TOKEN = "tok-PLACEHOLDER-001"


def _write(path, text):
    with open(path, "w") as f:
        f.write(text)


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.cookie_file = os.path.join(self.dir.name, "cookie.txt")

    def test_grafana_token_uses_bearer_and_is_not_refreshable(self):
        with mock.patch.dict(os.environ, {auth.GRAFANA_TOKEN_ENV: TOKEN}, clear=True):
            a = auth.grafana(self.cookie_file, "refresh")
        self.assertEqual(a.headers, {"Authorization": f"Bearer {TOKEN}"})
        self.assertFalse(a.refreshable)

    def test_kibana_key_uses_apikey_scheme(self):
        with mock.patch.dict(os.environ, {auth.KIBANA_API_KEY_ENV: TOKEN}, clear=True):
            a = auth.kibana(self.cookie_file, "refresh")
        self.assertEqual(a.headers, {"Authorization": f"ApiKey {TOKEN}"})
        self.assertFalse(a.refreshable)

    def test_token_wins_over_cookie_file(self):
        _write(self.cookie_file, "VouchCookie=abc\n")
        with mock.patch.dict(os.environ, {auth.GRAFANA_TOKEN_ENV: TOKEN}, clear=True):
            a = auth.grafana(self.cookie_file, "refresh")
        self.assertNotIn("Cookie", a.headers)

    def test_falls_back_to_cookie_and_is_refreshable(self):
        _write(self.cookie_file, "VouchCookie=abc\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            a = auth.grafana(self.cookie_file, "refresh")
        self.assertEqual(a.headers, {"Cookie": "VouchCookie=abc"})
        self.assertTrue(a.refreshable)

    def test_blank_token_is_treated_as_unset(self):
        _write(self.cookie_file, "VouchCookie=abc\n")
        with mock.patch.dict(os.environ, {auth.GRAFANA_TOKEN_ENV: "  "}, clear=True):
            a = auth.grafana(self.cookie_file, "refresh")
        self.assertIn("Cookie", a.headers)

    def test_missing_everything_names_the_env_var_and_hint(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(auth.MissingCredentials) as cm:
                auth.kibana(self.cookie_file, "run: kibana refresh")
        msg = str(cm.exception)
        self.assertIn(auth.KIBANA_API_KEY_ENV, msg)
        self.assertIn("run: kibana refresh", msg)

    def test_empty_cookie_file_raises(self):
        _write(self.cookie_file, "\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(auth.MissingCredentials):
                auth.grafana(self.cookie_file, "refresh")


class AtlassianTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.secrets = os.path.join(self.dir.name, "secrets")

    def test_env_takes_precedence(self):
        _write(self.secrets, 'ATLASSIAN_USERNAME=file@example.com\nATLASSIAN_API_TOKEN=file-tok\n')
        env = {auth.ATLASSIAN_USERNAME_ENV: "env@example.com", auth.ATLASSIAN_TOKEN_ENV: TOKEN}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(auth.atlassian_credentials(self.secrets), ("env@example.com", TOKEN))

    def test_secrets_file_fallback_strips_quotes(self):
        _write(self.secrets, 'OTHER=1\nATLASSIAN_USERNAME="file@example.com"\nATLASSIAN_API_TOKEN=\'file-tok\'\n')
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(auth.atlassian_credentials(self.secrets), ("file@example.com", "file-tok"))

    def test_partial_env_is_completed_from_file(self):
        _write(self.secrets, "ATLASSIAN_API_TOKEN=file-tok\n")
        with mock.patch.dict(os.environ, {auth.ATLASSIAN_USERNAME_ENV: "env@example.com"}, clear=True):
            self.assertEqual(auth.atlassian_credentials(self.secrets), ("env@example.com", "file-tok"))

    def test_missing_raises_without_leaking_values(self):
        _write(self.secrets, "ATLASSIAN_USERNAME=file@example.com\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(auth.MissingCredentials) as cm:
                auth.atlassian_credentials(self.secrets)
        self.assertNotIn("file@example.com", str(cm.exception))

    def test_absent_secrets_file_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(auth.MissingCredentials):
                auth.atlassian_credentials(os.path.join(self.dir.name, "nope"))


if __name__ == "__main__":
    unittest.main()
