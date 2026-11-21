#!/usr/bin/env python3
"""Serve the probe to a headless guest and collect what it reports back.

The benchmark runner starts one of these on the host while a live ISO boots.
The guest fetches the bootstrap through QEMU's user-mode network (the host is
10.0.2.2 there) and posts its results back to the same server, which needs no
SSH server in the guest, no root on the host and no distro-specific tool.

GET  /<path>      serves a file from --pub (the probe, the setup scripts)
POST /<path>      stores the request body as --in/<path>, keeping the name

Everything is plain stdlib http.server so it runs on any host Python 3 and it
never touches the guest's disks.

Usage: http-report.py --pub PUBDIR --in INDIR [--port 8099] [--logfile LOG]
Exit codes: 0 = served until SIGTERM/SIGINT, 1 = bad directory, 2 = bad arguments.
"""
import argparse
import http.server
import os
import re
import sys
import threading


SAFE = re.compile(r'^[A-Za-z0-9._/-]+$')


def safe_join(root, leaf):
    """Resolve leaf under root, refusing to leave it."""
    if not leaf or not SAFE.match(leaf):
        return None
    path = os.path.normpath(os.path.join(root, leaf))
    if not path.startswith(root + os.sep) and path != root:
        return None
    return path


class Handler(http.server.BaseHTTPRequestHandler):
    pub = None
    inbox = None
    log_path = None

    def log_message(self, fmt, *args):
        line = '%s - %s' % (self.address_string(), fmt % args)
        if Handler.log_path:
            with open(Handler.log_path, 'a', encoding='utf-8') as handle:
                handle.write(line + '\n')
        else:
            sys.stderr.write(line + '\n')

    def do_GET(self):
        path = safe_join(Handler.pub, self.path.lstrip('/'))
        if path is None or not os.path.isfile(path):
            self.send_error(404, 'no such file')
            return
        with open(path, 'rb') as handle:
            body = handle.read()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        leaf = self.path.lstrip('/')
        path = safe_join(Handler.inbox, leaf)
        length = int(self.headers.get('Content-Length') or 0)
        if path is None or length <= 0 or length > 64 * 1024 * 1024:
            self.send_error(400, 'bad upload')
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.part', 'wb') as handle:
            remaining = length
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                handle.write(chunk)
                remaining -= len(chunk)
            if remaining:
                self.send_error(400, 'truncated body')
                return
        os.replace(path + '.part', path)
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'ok')

    def do_HEAD(self):
        self.do_GET()


def serve(pub, inbox, port, log_path=None):
    Handler.pub = os.path.abspath(pub)
    Handler.inbox = os.path.abspath(inbox)
    Handler.log_path = log_path
    httpd = http.server.ThreadingHTTPServer(('0.0.0.0', port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--pub', required=True)
    parser.add_argument('--in', dest='inbox', required=True)
    parser.add_argument('--port', type=int, default=8099)
    parser.add_argument('--logfile')
    parser.add_argument('--selftest', action='store_true',
                        help='check the path handling and exit')
    args = parser.parse_args(argv)

    if args.selftest:
        inside = safe_join('/tmp/pub', 'a/b.txt')
        escapes = [safe_join('/tmp/pub', p) for p in
                   ('../etc/passwd', '/etc/passwd', 'a/../../x', 'a b')]
        print('inside=%s escapes=%s' % (inside, escapes))
        if inside != '/tmp/pub/a/b.txt' or any(e is not None and
                                              not e.startswith('/tmp/pub')
                                              for e in escapes):
            return 1
        return 0

    for directory in (args.pub, args.inbox):
        if not os.path.isdir(directory):
            print('not a directory: %s' % directory, file=sys.stderr)
            return 1
    httpd = serve(args.pub, args.inbox, args.port, args.logfile)
    print('SERVING: pub=%s inbox=%s port=%d' % (args.pub, args.inbox, args.port))
    sys.stdout.flush()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
