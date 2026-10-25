# Integration tests

Build and run the ordinary platform test products using `testing/Makefile`.
The `html` product includes the HTTP304 completion regression.

The test uses public network OPEN/STATUS/CLOSE and FujiNet Clock binary time
with hundredths. A terminal STATUS with a valid sampled total below4.99s
passes; sampled5s or more fails. The centisecond boundary, failed/malformed/
reversed/frozen clock, failed OPEN/STATUS or exhausted pending observations
prints `INVALID/INCONCLUSIVE` and fails closed in the existing harness.
Cleanup precedes any aborting assertion. Availability and particular network
or CLOSE error values are printed, not asserted by this timing test.

The public WPT endpoint is intended to send HTTP304, exactly one declared
Content-Length123 and no body, then hold the peer open23 seconds. Development
wire qualification is not a prerequisite script for normal users. The public
network API cannot authenticate every HTTP response header at runtime: endpoint
changes/outages can invalidate the test or mimic a result. An endpoint outage
is not itself evidence of a firmware regression.

FujiNet Clock is calendar time, not monotonic. Undetectable clock corrections,
timezone changes or slow/stale clock behavior can distort the result. Clock
call overhead is included conservatively; no overhead is subtracted. A poll
cap cannot bound one synchronous call. A passing build does not establish
runtime accuracy, device coexistence or compatibility on every platform.
