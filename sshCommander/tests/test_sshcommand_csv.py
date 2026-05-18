"""Unit tests for CSV filtering and SDM port validation (no network)."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sshcommand  # noqa: E402


class TestIsValidSdmPort(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(sshcommand.is_valid_sdm_port(""))
        self.assertIsNone(sshcommand.is_valid_sdm_port("   "))

    def test_non_numeric(self):
        self.assertIsNone(sshcommand.is_valid_sdm_port("abc"))
        self.assertIsNone(sshcommand.is_valid_sdm_port("65a"))

    def test_in_range(self):
        self.assertEqual(sshcommand.is_valid_sdm_port("443"), 443)
        self.assertEqual(sshcommand.is_valid_sdm_port("65279"), 65279)
        self.assertEqual(sshcommand.is_valid_sdm_port(" 60799 "), 60799)

    def test_out_of_range(self):
        self.assertIsNone(sshcommand.is_valid_sdm_port("0"))
        self.assertIsNone(sshcommand.is_valid_sdm_port("65536"))
        self.assertIsNone(sshcommand.is_valid_sdm_port("999999"))


class TestIterTargetDevices(unittest.TestCase):
    def test_all_rows_with_valid_port(self):
        p = ROOT / "tests" / "fixtures" / "sample_inventory.csv"
        rows = list(
            sshcommand.iter_target_devices(
                p,
                port_column="SDM Port",
                name_column="Name",
                require_sdm_enabled=False,
            )
        )
        names = {r.name for r in rows}
        ports = {r.sdm_port for r in rows}
        self.assertEqual(names, {"EnabledWithPort", "DisabledButPort"})
        self.assertEqual(ports, {65279, 60799})

    def test_require_enabled(self):
        p = ROOT / "tests" / "fixtures" / "sample_inventory.csv"
        rows = list(
            sshcommand.iter_target_devices(
                p,
                port_column="SDM Port",
                name_column="Name",
                require_sdm_enabled=True,
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "EnabledWithPort")
        self.assertEqual(rows[0].sdm_port, 65279)

    def test_utf8_sig_header(self):
        raw = "\ufeffName,SDM Port\nDev1,22\n"
        # Exercise utf-8-sig via a temp file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(raw)
            tpath = Path(tmp.name)
        try:
            rows = list(
                sshcommand.iter_target_devices(
                    tpath,
                    port_column="SDM Port",
                    name_column="Name",
                    require_sdm_enabled=False,
                )
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].sdm_port, 22)
        finally:
            tpath.unlink(missing_ok=True)


class TestParseUserAtHost(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(sshcommand.parse_user_at_host("vvdn@smbshells.netgear.com"), ("vvdn", "smbshells.netgear.com"))


class TestParseCommandsFromFileText(unittest.TestCase):
    def test_comments_and_blanks(self):
        text = "\n  # c\nfoo  \n\n  bar \n"
        self.assertEqual(sshcommand.parse_commands_from_file_text(text), ["foo", "bar"])


class TestResolveCommandArg(unittest.TestCase):
    def test_inline_when_not_a_file(self):
        src = sshcommand.resolve_command_arg("uptime; date")
        self.assertEqual(src.kind, "inline")
        self.assertIsNone(src.path)
        self.assertEqual(src.commands, ["uptime; date"])

    def test_file_fixture(self):
        p = ROOT / "tests" / "fixtures" / "sample_cmds.txt"
        src = sshcommand.resolve_command_arg(str(p))
        self.assertEqual(src.kind, "file")
        self.assertEqual(src.commands, ["uptime", "date"])


class TestBuildProgressLogger(unittest.TestCase):
    def test_quiet_writes_nothing(self):
        import io

        buf = io.StringIO()
        log = sshcommand.build_progress_logger(True, stream=buf)
        log("hello")
        self.assertEqual(buf.getvalue(), "")

    def test_verbose_writes(self):
        import io

        buf = io.StringIO()
        log = sshcommand.build_progress_logger(False, stream=buf)
        log("hello")
        self.assertEqual(buf.getvalue().strip(), "hello")


class TestNormalizeTerminalText(unittest.TestCase):
    def test_crlf(self):
        self.assertEqual(sshcommand._normalize_terminal_text("a\r\nb\rc\r"), "a\nb\nc")


class TestStripLeadingEchoLine(unittest.TestCase):
    def test_strips_prompt_plus_cmd(self):
        before = "root@h:/path# uptime\n15:00 up\n"
        self.assertEqual(sshcommand._strip_leading_echo_line(before, "uptime"), "15:00 up")

    def test_no_strip_when_output_only(self):
        before = "15:00 up\n"
        self.assertEqual(sshcommand._strip_leading_echo_line(before, "uptime"), "15:00 up")


class TestDevicePromptLineRegex(unittest.TestCase):
    def test_echo_line_does_not_match(self):
        r = sshcommand.PATTERN_DEVICE_PROMPT_LINE
        echoed = "root@7D81427VD0007:/etc/insight/support# uptime; echo stuff\n"
        self.assertIsNone(r.search(echoed))

    def test_prompt_line_with_newline(self):
        r = sshcommand.PATTERN_DEVICE_PROMPT_LINE
        buf = "banner\nroot@7D81427VD0007:/etc/insight/support#\n"
        self.assertIsNotNone(r.search(buf))

    def test_prompt_at_eof_cr_only(self):
        r = sshcommand.PATTERN_DEVICE_PROMPT_LINE
        buf = "BusyBox v1\rroot@7D81427VD0007:/etc/insight/support#"
        self.assertIsNotNone(r.search(buf))

    def test_serial_style_prompt_without_root(self):
        r = sshcommand.PATTERN_DEVICE_PROMPT_LINE
        buf = "banner\n7D81427VD0007:/etc/insight/support#\n"
        self.assertIsNotNone(r.search(buf))

    def test_prompt_with_ansi_before_root(self):
        r = sshcommand.PATTERN_DEVICE_PROMPT_LINE
        buf = "banner\n\x1b[0m\x1b[32mroot@7D81427VD0007:/etc/insight/support#\n"
        self.assertIsNotNone(r.search(buf))

    def test_prompt_with_csi_question_form(self):
        r = sshcommand.PATTERN_DEVICE_PROMPT_LINE
        buf = "x\n\x1b[?25h\x1b[0mroot@7D81427VD0007:/etc/insight/support#\n"
        self.assertIsNotNone(r.search(buf))

    def test_prompt_with_ctrl_c_after_hash(self):
        r = sshcommand.PATTERN_DEVICE_PROMPT_LOOSE
        buf = "x\nroot@7D81427VD0007:/etc/insight/support#\x03\n"
        self.assertIsNotNone(r.search(buf))


class TestBatchedUploadHeredocLines(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(sshcommand._batched_upload_heredoc_lines([]), [])

    def test_reconstructs_one_line(self):
        lines = ["YWJj"]
        batches = sshcommand._batched_upload_heredoc_lines(lines)
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0], "YWJj\n")

    def test_reconstructs_many_mime_width_lines(self):
        lines = [f"{i:076d}" for i in range(500)]
        merged = "".join(sshcommand._batched_upload_heredoc_lines(lines))
        self.assertEqual(merged, "\n".join(lines) + "\n")

    def test_batches_respect_size_cap(self):
        lines = ["x" * 76 for _ in range(400)]
        batches = sshcommand._batched_upload_heredoc_lines(lines)
        self.assertGreater(len(batches), 1)
        for b in batches:
            self.assertTrue(b.endswith("\n"), msg=b[-20:])
            # default cap 8192; MIME lines are 76 so a batch stays bounded
            self.assertLessEqual(len(b), 8200)


class TestUploadHeredocBashRoundTrip(unittest.TestCase):
    """Decode path matches BusyBox/bash heredoc + base64 -d (no SDM hardware)."""

    def test_batched_body_decodes(self):
        import base64
        import hashlib
        import os
        import shlex
        import subprocess
        import tempfile

        data = os.urandom(42_294)
        b64 = base64.b64encode(data).decode("ascii")
        chunks = [b64[i : i + 76] for i in range(0, len(b64), 76)]
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            dst = tf.name
        try:
            quoted = shlex.quote(dst)
            pieces = [f"base64 -d > {quoted} <<'__UPLOAD_B64EOF__'\n"]
            pieces.extend(sshcommand._batched_upload_heredoc_lines(chunks))
            pieces.append("__UPLOAD_B64EOF__\n")
            r = subprocess.run(
                ["bash", "--norc", "-"],
                input="".join(pieces),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(r.returncode, 0, msg=(r.stderr or "") + (r.stdout or ""))
            got = Path(dst).read_bytes()
            self.assertEqual(hashlib.md5(got).digest(), hashlib.md5(data).digest())
        finally:
            Path(dst).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
