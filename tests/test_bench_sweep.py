"""Offline checks for the cross-OS benchmark sweep of issue #424 (task b01).

These cases never start QEMU and never boot another operating system: the
matrix is only parsed, the disk-free gate is exercised with an impossible
minimum, the HTTP collector is round-tripped over loopback, and the QMP typer
is checked against the exact command the runner types into a live desktop.
"""
from pathlib import Path
import os
import re
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'scripts/vm/bench'
RUNNER = BENCH / 'run-bench.sh'
MATRIX = BENCH / 'matrix.conf'
QMP_TYPE = BENCH / 'qmp-type.py'
HTTP_REPORT = BENCH / 'http-report.py'
BOOTSTRAP = BENCH / 'guest-bootstrap.sh'
GUEST_PTS = BENCH / 'guest-pts.sh'

ISO_DIR = '/media/rhy/data/bench-isos'


def matrix_entries():
    entries = []
    for line in MATRIX.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        entries.append(line.split())
    return entries


class BenchSweepTests(unittest.TestCase):
    def run_command(self, argv, env=None, cwd=None):
        environ = {'PATH': '/usr/bin:/bin:/usr/local/bin'}
        if env:
            environ.update(env)
        return subprocess.run([str(item) for item in argv], text=True,
                              capture_output=True, timeout=120, env=environ,
                              cwd=str(cwd) if cwd else None)

    def test_matrix_is_the_popular_distro_sweep(self):
        entries = matrix_entries()
        self.assertEqual(len(entries), 9,
                         'the sweep measures Spaced plus eight live ISOs')
        self.assertEqual(entries[0][0], 'spaced-linux')
        labels = [entry[0] for entry in entries]
        # rhY 2026-11-21: "make sure we test VOID and MX linux as well".
        for wanted in ('void', 'mx'):
            self.assertIn(wanted, labels)
        for entry in entries:
            self.assertTrue(entry[1].startswith(ISO_DIR + '/'),
                            '%s iso must live under %s' % (entry[0], ISO_DIR))
            self.assertTrue(entry[1].endswith('.iso'))
            options = dict(pair.split('=', 1) for pair in entry[2:])
            for key in ('distro', 'version', 'desktop', 'access'):
                self.assertIn(key, options, '%s option %s' % (entry[0], key))
            self.assertIn(options['access'], ('ssh', 'qmp'))
            if options['access'] == 'qmp':
                self.assertIn('terminal', options)

    def test_runner_refuses_without_free_disk_and_keeps_vms_off_tmp(self):
        text = RUNNER.read_text(encoding='utf-8')
        self.assertIn('/media/rhy/data/bench-vms', text)
        self.assertIn('BENCH_VM_DIR', text)
        self.assertIn('rm -rf "$CURRENT_VM_DIR"', text,
                      'the VM disk must be destroyed when the OS is done')
        self.assertIn('BENCH_OS_CAP_SECONDS', text)
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_command(['bash', RUNNER, MATRIX, '1'],
                                      env={'BENCH_OUT_DIR': tmp,
                                           'BENCH_VM_DIR': str(Path(tmp) / 'vms'),
                                           'BENCH_FREE_MIN_GB': '999999'})
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('REFUSED:', result.stdout)
            self.assertIn('RESULT: measured=0 skipped=9', result.stdout)

    def test_runner_types_only_supported_characters_into_the_guest(self):
        # The one command typed into every live desktop: whatever it contains
        # has to be typeable through QMP, because a lost character is a guest
        # that is never measured.
        sys.path.insert(0, str(BENCH))
        import importlib.util
        spec = importlib.util.spec_from_file_location('qmp_type', str(QMP_TYPE))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        command = 'wget -qO- http://10.0.2.2:8099/debian/b.sh | sh'
        for char in command:
            if char.isalnum():
                continue
            self.assertTrue(char in module.CHAR_KEYS or char in module.SHIFTED,
                            'typed command carries %r, which qmp-type cannot send'
                            % char)

    def test_qmp_type_refuses_without_the_socket(self):
        result = self.run_command(['python3', QMP_TYPE, '--qmp', '/nope/qmp',
                                   'type', 'ls'])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('no QMP socket', result.stdout + result.stderr)

    def test_http_report_round_trips_a_probe_and_its_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = Path(tmp) / 'pub'
            inbox = Path(tmp) / 'inbox'
            pub.mkdir()
            inbox.mkdir()
            (pub / 'guest-probe.sh').write_text('# probe\n', encoding='utf-8')
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            server = subprocess.Popen(['python3', HTTP_REPORT, '--pub', str(pub),
                                       '--in', str(inbox), '--port', str(port)],
                                      text=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
            try:
                def request(method, path, body=None):
                    # A raw socket keeps the path exactly as written: urllib
                    # would normalise away the ".." this test needs.
                    sock = None
                    for _ in range(40):
                        try:
                            sock = socket.create_connection(('127.0.0.1', port),
                                                            timeout=10)
                            break
                        except OSError:
                            import time
                            time.sleep(0.25)
                    self.assertIsNotNone(sock, 'the collector never listened')
                    payload = '%s %s HTTP/1.1\r\nHost: 127.0.0.1\r\n' % (method, path)
                    if body is not None:
                        payload += ('Content-Length: %d\r\n' % len(body))
                    payload += 'Connection: close\r\n\r\n'
                    data = payload.encode()
                    if body is not None:
                        data += body
                    sock.sendall(data)
                    chunks = []
                    while True:
                        piece = sock.recv(4096)
                        if not piece:
                            break
                        chunks.append(piece)
                    sock.close()
                    return b''.join(chunks)

                import time
                served = b''
                for _ in range(40):
                    served = request('GET', '/guest-probe.sh')
                    if b'200 OK' in served.split(b'\r\n', 1)[0]:
                        break
                    time.sleep(0.25)
                self.assertIn(b'# probe\n', served,
                              'the probe was not served to the guest')
                posted = request('POST', '/debian/probe.txt',
                                 b'INFO: mem_used_mib=1189\n')
                self.assertIn(b'200 OK', posted.split(b'\r\n', 1)[0])
                landed = inbox / 'debian/probe.txt'
                self.assertTrue(landed.is_file(), 'the POST did not land in inbox')
                self.assertIn('mem_used_mib', landed.read_text(encoding='utf-8'))
                escaped = request('POST', '/../../escape', b'nope')
                self.assertIn(b'400', escaped.split(b'\r\n', 1)[0])
                self.assertFalse((inbox.parent / 'escape').exists(),
                                 'an escaping POST wrote outside the inbox')
            finally:
                server.terminate()
                for pipe in (server.stdout, server.stderr):
                    pipe.read()
                    pipe.close()
                server.wait(timeout=10)

    def test_http_report_refuses_path_escapes(self):
        result = self.run_command(['python3', HTTP_REPORT, '--pub', '/tmp',
                                   '--in', '/tmp', '--selftest'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('escapes=[', result.stdout)

    def test_guest_scripts_are_posix_sh_and_report_every_stage(self):
        for script in (BOOTSTRAP, GUEST_PTS):
            result = subprocess.run(['sh', '-n', str(script)], text=True,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
        bootstrap = BOOTSTRAP.read_text(encoding='utf-8')
        for marker in ('beacon', 'probe.txt', 'pts.tsv', 'done'):
            self.assertIn(marker, bootstrap)
        self.assertIn('guest-pts.sh', bootstrap)
        pts = GUEST_PTS.read_text(encoding='utf-8')
        self.assertIn('CAP_SECONDS', pts)
        self.assertIn('timeout', pts)
        for manager in ('apt-get', 'dnf', 'xbps-install', 'pacman'):
            self.assertIn(manager, pts)
        self.assertIn('batch-benchmark', pts)
        self.assertIn('pts-results.tar', pts)
        self.assertIn('phoronix-test-suite', pts)


if __name__ == '__main__':
    unittest.main()
