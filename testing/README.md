# HTTP completion integration tests

`httpdone` checks fixed Content-Length and chunked responses through the normal
FujiNet `network_*` APIs. Each case requires the exact eight bytes
`46 4e 00 0d 0a 7f 80 ff`, then STATUS reporting no bytes waiting, disconnected,
and `NETWORK_ERROR_END_OF_FILE`. Body receipt alone cannot pass.

Run the standard-library Python fixture on a host reachable by FujiNet:

```sh
python3 testing/http_completion_fixture.py --bind 0.0.0.0 --port 8080
```

`/fixed` sends Content-Length: 8; `/chunked` sends two chunks and the terminal
`0\r\n\r\n`. Both advertise Connection: close but intentionally hold the TCP
socket open. After checking body and EOF, the test closes N1 and requests
`/check/fixed` or `/check/chunked`. The fixture returns PASS only while the
matching response socket is still held, before its deadline. It ignores client
FIN for this decision. Timeout closes the socket and exits with failure, so
completion caused by fixture close cannot pass. Restart the fixture per run;
fixed must precede chunked.

The standard `httpdone` executable is Atari-only. Build using the existing
platform/product rules:

```sh
make -f makefiles/platforms/atari.mk product
make -C testing -f ../makefiles/platforms/atari.mk MEKKO_PRODUCT=fnlib-test.lib HTTP_COMPLETION_BASE=http://fixture-host:8080 product
make -C testing -f ../makefiles/platforms/atari.mk MEKKO_PRODUCT=httpdone HTTP_COMPLETION_BASE=http://fixture-host:8080 product
```

Replace `fixture-host` with a reachable hostname or address. The base has no
`N1:` prefix or trailing slash. Changing it requires rebuilding the shared test
library and executable from clean output. With no base configured, both cases
print SKIP; this is not validation. Run `testing/r2r/atari/httpdone.com` using a
connected FujiNet or a configured Atari/NetSIO/FujiNet-PC setup.

The default hold is 30 seconds and total fixture lifetime is 300 seconds.
Override with `--hold-seconds` and `--idle-seconds` if needed. Requests have a
two-second deadline; the device status loop is limited to 1000 polls. Use an
external runtime timeout for a stuck bus call. The fixture exits successfully
only after both completion confirmations. The existing test harness reports
PASS/FAIL and waits for a key at exit.

Cheap host checks (these do not exercise FujiNet):

```sh
python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("testing/http_completion_fixture.py").read_text())'
python3 testing/http_completion_fixture.py --self-test
git diff --check
```
