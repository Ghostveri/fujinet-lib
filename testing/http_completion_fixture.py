#!/usr/bin/env python3
"""Serve two HTTP messages, holding each socket until its completion check."""

import argparse
import math
import select
import socket
import time

BODY = bytes((0x46, 0x4E, 0x00, 0x0D, 0x0A, 0x7F, 0x80, 0xFF))
CASES = ("fixed", "chunked")


def response(body, status="200 OK"):
    return (f"HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n").encode("ascii") + body


def case_response(case):
    headers = b"HTTP/1.1 200 OK\r\nConnection: close\r\n"
    if case == "fixed":
        return headers + b"Content-Length: 8\r\n\r\n" + BODY
    return (headers + b"Transfer-Encoding: chunked\r\n\r\n"
            + b"4\r\n" + BODY[:4] + b"\r\n4\r\n" + BODY[4:]
            + b"\r\n0\r\n\r\n")


def read_path(conn, deadline):
    data = b""
    while b"\r\n\r\n" not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or len(data) >= 4096:
            raise ValueError("request timeout or oversized headers")
        conn.settimeout(remaining)
        part = conn.recv(4096 - len(data))
        if not part:
            raise ValueError("incomplete request")
        data += part
    method, path, version = data.split(b"\r\n", 1)[0].split(b" ")
    if method != b"GET" or version not in (b"HTTP/1.0", b"HTTP/1.1"):
        raise ValueError("GET required")
    return path.decode("ascii")


def serve(listener, hold_seconds, lifetime):
    held = None
    active = None
    passed = []
    end = time.monotonic() + lifetime
    deadline = end
    try:
        while len(passed) < len(CASES):
            remaining = min(end, deadline) - time.monotonic()
            if remaining <= 0:
                return False
            if not select.select([listener], [], [], remaining)[0]:
                return False
            conn, _ = listener.accept()
            try:
                path = read_path(conn, min(end, deadline, time.monotonic() + 2))
                if time.monotonic() >= min(end, deadline):
                    return False
                conn.settimeout(min(2, end - time.monotonic()))
                case = CASES[len(passed)]
                if path == "/" + case and held is None:
                    conn.sendall(case_response(case))
                    # The hold starts only after the complete message is sent.
                    deadline = time.monotonic() + hold_seconds
                    held, active, conn = conn, case, None
                elif active is not None and path == "/check/" + active:
                    # Receipt of this request proves the client finished before
                    # our close. Ignore client FIN: it closes N1 before checking.
                    conn.sendall(response(b"PASS"))
                    passed.append(active)
                    held.close()
                    held, active = None, None
                    deadline = end
                else:
                    conn.sendall(response(b"FAIL"))
            except (OSError, ValueError, UnicodeError):
                pass
            finally:
                if conn is not None:
                    conn.close()
        return True
    finally:
        if held is not None:
            held.close()


def self_test():
    import http.client
    import threading
    import unittest

    class FixtureTests(unittest.TestCase):
        def run_fixture(self, check, hold=2):
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                result = []
                worker = threading.Thread(target=lambda: result.append(
                    serve(listener, hold, 5)))
                worker.start()
                try:
                    check(listener.getsockname()[1])
                finally:
                    worker.join(6)
                self.assertFalse(worker.is_alive())
                return result[0]

        def get(self, port, path):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", path)
            reply = conn.getresponse()
            body = reply.read()
            return conn, reply, body

        def test_completion_before_close(self):
            def check(port):
                for case in CASES:
                    with socket.create_connection(("127.0.0.1", port), 2) as conn:
                        conn.sendall(f"GET /{case} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
                        reply = http.client.HTTPResponse(conn)
                        reply.begin()
                        self.assertEqual(reply.read(), BODY)
                        self.assertEqual(reply.chunked, case == "chunked")
                        reply.close()
                        # No extra bytes or peer EOF after framed HTTP completion.
                        conn.settimeout(0.02)
                        with self.assertRaises(socket.timeout):
                            conn.recv(1)
                    confirmation, _, marker = self.get(port, "/check/" + case)
                    self.assertEqual(marker, b"PASS")
                    confirmation.close()
            self.assertTrue(self.run_fixture(check))

        def test_no_response_cannot_confirm(self):
            def check(port):
                conn, _, marker = self.get(port, "/check/fixed")
                self.assertEqual(marker, b"FAIL")
                conn.close()
            self.assertFalse(self.run_fixture(check, hold=0.1))

        def test_timeout_cannot_pass(self):
            def check(port):
                conn, _, body = self.get(port, "/fixed")
                self.assertEqual(body, BODY)
                conn.close()
                # No completion confirmation: the fixture must fail and exit.
            self.assertFalse(self.run_fixture(check, hold=0.1))

    return unittest.TextTestRunner().run(
        unittest.defaultTestLoader.loadTestsFromTestCase(FixtureTests)).wasSuccessful()


def positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--hold-seconds", type=positive_seconds, default=30)
    parser.add_argument("--idle-seconds", type=positive_seconds, default=300,
                        help="total fixture lifetime, including active requests")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return 0 if self_test() else 1
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((args.bind, args.port))
        listener.listen(4)
        print(f"Fixture port {listener.getsockname()[1]}; fixed then chunked", flush=True)
        passed = serve(listener, args.hold_seconds, args.idle_seconds)
    print("PASS fixed and chunked" if passed else "FAIL completion not confirmed", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
