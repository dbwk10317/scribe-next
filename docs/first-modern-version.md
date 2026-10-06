# First modern Linux version: closeout boundary

2026-10-05 · base mainbc9ba6e · public Facebook Scribe
`fcd294faffd1e88af1643a3a8c2359c41713f7c2`.
Current build/run/config/rollback instructions are in [README](../README.md).
Company inputs are out of scope. Detailed performance remains deferred.

## Current compatibility policy supersedes prior closeout

The 2026-10-06 user decision prioritizes mixed old/new sender/receiver and existing
log-reader contracts. Semantic corrections are restored to defined upstream
behavior; harmless UB/crash repairs remain. See [current policy](legacy-compatibility-policy.md).
The results below describe their recorded source stages, not the reverted candidate.

## Prior named first-version closeout

| Boundary | Evidence |
| --- | --- |
| Modern build/install | Debian 13/GCC 14 and Ubuntu 26/GCC 15; C++17, Thrift compiler/runtime 0.25, prepared fb303, Boost 1.83; root make, Python scheme, DESTDIR/help |
| Static/shared RPC | Default static and separately selected shared build/staged loader on both Linux lanes |
| Public original behavior | Limited actual old/new framed binary/fb303 and all 10 normal store types; ordinary spool/relay recovery, rotation/reinitialize and process restart append |
| Dynamic/config | Actual direct/unpooled RPC: A/cacheA/strict TTL B/failed-refresh-retainedB/recoveryA; missing bucket_id and updater_port warning/static fallbacks |
| Modern optional HDFS | Hadoop 3.5/JDK 17 single-DN,9→10 exact binary bytes, fresh counters 2/1, regular marker/readback, live DN/safemode OFF/healthy blocks/owned cleanup; JDK 21 local client JNI |
| Regression | Default Linux 201 with failure/error/skip0; Mac focused mapping 7 and repaired HDFS offline 9. Offline tests and actual daemon results are separate |

The named dynamic/config gap is closed by PR21; no additional startup matrix is
required to close this supported first-version scope. Existing permissive parser,
handler/store/inheritance and limit tests remain evidence. Two actual missing-key cases do not establish universal rejection or all config
options.

README now consolidates supported prerequisites, build/staged usage, original
config behavior, approved exceptions, limits and rollback preparation. Prior
step counts/failures and raw records remain in Git/Library history. Repaired Mac
fixture results do not turn Mac into a supported daemon/build platform.

## What this completion means

This is a documented, tested **initial modern Linux candidate**, not proof of
complete original-feature equivalence, production readiness or operational soak.
No original store is deleted. IDL/wire/config/store architecture is retained;
current preserved UB repairs and explicit finite wire limits are not disguised as
complete old-runtime equivalence. OK is queue acceptance, flush is not fsync, and no durable/exactly-once
contract is added. The HDFS lane retains its declared nonempty-directory seed and
is modern distributed validation, not historical libhdfs binary equivalence.

No additional framework, C++ stylistic rewrite, exhaustive fault factory or
benchmark is needed merely to finish this named documentation/build scope.
Any newly discovered functional-policy difference must be reported before fixing.

## Declared deeper limits

- Full dynamic/config/store-option/fault matrix, response-loss/partial-replay daemon
  campaigns beyond existing component evidence; original partial-replay loss remains
- Historical HDFS binaries; empty-directory/delete/permissions/replication,
  multi-DN faults and secure production clusters
- Actual old/new shared-daemon whole-path comparison, non-Linux/other toolchains
- Old language-client runtime combinations beyond preserved IDL/wire and verified
  Python3 packaging; original example helpers are not all modernized
- Detailed performance/cause analysis/tuning, total daemon leak/TSan/operational soak
- >256 MiB retained spool retry boundary; original ThriftFile empty/oversized
  delegate/drop/log/success accounting remains the selected policy

## Remaining user decisions

1. Whether/when to assign a version/tag and publish a release artifact
2. Artifact packaging and its exact dependency/ABI/license-notice bundle; existing
   private staged install is not a portable redistributable binary package
3. Whether/where to perform service deployment and real rollback validation
4. When to resume the deferred detailed performance comparison

None of these actions is performed by this docs closeout. Rollback instructions
preserve prior artifact/runtime/config and data, prohibit concurrent writers and
avoid automatic conversion/deletion; they are guidance, not a verified production
rollback claim. Redistribution must include the original license/attributions,
modified-file notices and applicable dependency material.

Evidence: [actual harness](daemon-differential.md), [Linux build](linux-build-mvp.md),
[HDFS](hdfs-compatibility.md), [approved changes](review-fixes-status.md),
[ThriftFile policy](thriftfile-fix-options.md), [design](design.ko.md).
