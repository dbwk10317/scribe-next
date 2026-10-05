# First modern Linux version: completion boundary

2026-10-05 · public Facebook Scribe fcd294f · base main7867878.
Company inputs are out of scope. Detailed performance comparison remains deferred.
A first release can have an explicit supported boundary without claiming every
original option/fault/platform combination is proven equivalent.

## Established evidence

- Modern C++17/Thrift+fb3030.25/Boost1.83 Linux x86_64 build, default/static,
  Python installation, DESTDIR and help on Debian13/GCC14 and Ubuntu26/GCC15
- Original shared RPC selection, clean build and private staged loader on both
- Limited actual old/new framed binary/fb303 and all10 normal store types
- Ordinary spool/downstream-off/full replay, file rotation/reinitialize,
  owned process crash/restart append, fb303 options/counters/unknown method
- Optional HDFS modern compile/JNI and actual single-DN Hadoop3.5/JDK17:
  exact binary9→10 bytes, fresh counters2/1, regular marker, registered DataNode,
  safemode OFF, healthy block locations and owned child/listener cleanup

The HDFS result is a modern distributed lane, not historical libhdfs binary
old/new equivalence. Its directory has the declared nonempty seed precondition.
The first hostname-resolution failure and successful localhost rerun remain raw
evidence. Existing194 regression tests and focused9 are separate from actual runs.
Mac focused9 previously had7PASS+2ERROR because `/bin/true` was absent; the small
fixture-only portability repair uses the current interpreter, preserving checks.
The repaired fixture subsequently passed all9 Mac offline tests (failure/error/skip0)
and server full194 tests (failure/error/skip0) using the existing matching build.
Production and the actual distributed runner are byte-identical to PR19. No new
build, cluster run, dependency/environment change or benchmark was performed; the
previous7PASS/2ERROR and actual PR19 evidence remain historical records.

## Essential next closeout

1. **Actual dynamic bucket mapping/TTL routing.** This is an original feature,
   not another variation of the static bucket case. Existing dynamic store tests
   replace the resolver, while the real mapping RPC test only fetches once.
   Reuse the current actual harness/relay peer/mapping wire fixture for one batch:
   initial destination A, cached use, observed expiry/remap to B, one failed
   expired refresh and recovery. Compare exact payload routing, peer call trace,
   statuses/counters and owned-process cleanup against the public old baseline.
   Respect `lastUpdated + ttl < now`; bound observation without faking clocks.
2. **Representative actual config outcomes in that batch.** Existing parser,
   invalid handler/store, inheritance and wire-limit tests already cover many
   contracts. Add only named startup/reload observations, such as valid dynamic
   config, a missing required dynamic key and missing config file. Compare original
   exit/readiness/status/ACK behavior. Do not invent a universal rejection rule;
   the original deliberately permits some malformed/unrouted configurations.
3. **Release support/usage closeout.** Reconcile the support table and historical
   notes with the actual HDFS/shared results. State exact prerequisites, example
   config, private loader/staged installation and rollback to a prior artifact.
   Keep approved bug-fix differences and known wire/spool limits explicit. Decide
   version/tag/artifact publication separately from service deployment permission.

Stop after these named observations and the release checklist; more component
counts are not a substitute for closing a feature's real path. No C++ stylistic
rewrite or new architecture is required to label the supported first version.
If a public-original behavioral difference is found, report it before changing
production policy. Existing approved fixes are exceptions, not new blanket permission.

## Optional deeper follow-up / declared limits

- Full dynamic mapping/config/store-option matrix and scheduler races
- Actual response-loss/partial-replay fault campaigns beyond existing component
  evidence and approved partial-replay fix
- Historical HDFS binary equivalence, empty-directory behavior, distributed delete,
  multi-DN replication, permissions, NameNode/DataNode faults and secure clusters
- Actual old/new shared daemon differential and non-Linux/other toolchain support
- Broad old-language-client runtime combinations beyond preserved IDL/wire and
  verified Python3 packaging
- Detailed performance/cause analysis, tuning and deployment/operational soak

These remain visible limits. Performance is postponed by the user, not silently
passed. Original OK acknowledges queue acceptance, not durability/exactly-once.
Empty/oversized Thrift delegation/drop/log/success counts stay as selected. The
explicit256MiB RPC candidate and larger retained spool retry boundary remain.
No original store/backend is removed just because a deeper matrix is deferred.

Source/evidence: [current support](linux-build-mvp.md),
[actual harness](daemon-differential.md), [HDFS](hdfs-compatibility.md),
[design](design.ko.md), [approved exceptions](review-fixes-status.md).
The actual dynamic gap follows `src/dynamic_bucket_updater.cpp`,
`test/cpp/store_review_contracts.h`, `test/cpp/review_limits_contracts.h` and the
original remapping intent in `test/bucketupdater.php`.

The next [dynamic mapping batch](daemon-differential.md#dynamic-mappingttl-batch)
passed its bounded actual old/new direct/unpooled case: cached A, strict TTL
expiry to B, failed refresh retaining B, recovery to A, and two missing-key static
fallbacks. Server201/Mac focused7 passed with zero skips. Exact wire/payload,
ordinary counters/status, chronological raw evidence and owned cleanup were
verified. This closes that named representative gap; the optional full dynamic
matrix and release support/usage closeout remain separate. No version/tag,
artifact publication or deployment is implied.
