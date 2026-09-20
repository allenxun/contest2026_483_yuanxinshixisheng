# FAT explicit read-only candidate

This is an unintegrated candidate against the frozen SDK FAT sources. No SDK, formal source, device, model, or central log was changed. Enable `CONFIG_FAT_FORCE_READONLY=y` explicitly; its Kconfig default is `n`. It applies to **every FAT mount in that firmware**, not a per-mount flag. Do not enable in a firmware that requires writable FAT volumes.

The frozen VFS uses mount flags in `find_blockdriver` but passes only driver/data/handle to FAT bind. The original bind invokes `fat_mount(fs, true)`. This candidate changes the enabled branch to false and forces false in the direct mount entry as defense in depth. `geo_writeenabled=false` can therefore mount. MS_RDONLY alone does not establish this policy.

## Changes and mutation audit

| Path | Enabled behavior / reviewed chain |
| --- | --- |
| open | Reject non-O_RDONLY access and any CREAT/TRUNC/APPEND/EXCL flag before lookup. Actual NuttX flags are used in tests, including O_RDONLY=1. |
| write, truncate, unlink, mkdir, rmdir, rename | Immediate -EROFS; no mutation. fchstat/chstat slots are NULL in this frozen operations table. |
| fat_setattrib / common attribute helper | Setter denied even for a zero-bit request; common helper rejects nonzero set/clear. Getter preserves bits and cannot enter changed-attributes branch. |
| FAT/cluster helpers | zero_cluster, putcluster, removechain, extendchain, dirtruncate, dirshrink, dirextend denied. |
| Directory helpers | allocatedirentry, freedirentry, dirnamewrite, dirwrite, dircreate, remove denied. Private short/long-name writers remain compiled but are behind denied public mutation entries; they are not individually instrumented. |
| sync | Lock/check mount; clean sync succeeds; dirty/modified file or filesystem/FSInfo returns -EROFS without clearing flags. No timestamp encoding or directory update. |
| cache flush / updatefsinfo | Clean succeeds; dirty rejects without write or dirty-flag clearing. Free-cluster scan may cache a count in RAM but never marks FSInfo dirty. |
| fat_hwwrite | Immediate -EROFS: final FAT-to-block-write barrier. No direct block write callback remains in the enabled preprocessed sources tested. |
| read / seek / directory iteration | Read chain calls get_sectors(read=true), which exits before extension logic. Seek only changes positioning/cache state. nextdirentry follows existing chains. No access-time update. |
| close / unbind | Original cleanup retained. close calls guarded sync then frees file resources. unbind calls guarded updatefsinfo then frees mount resources and closes driver. Dirty unbind may fail safely instead of pretending a flush succeeded. |
| ioctl | Frozen implementation returns -ENOTTY; it does not forward to block ioctl despite its comment. |

Default-disabled original bodies remain in #else branches. Header is unchanged. The candidate deliberately does not fix unrelated baseline ownership issues (for example bind failure after block open does not pair every path with block close), forced-unmount lifetime hazards, or malformed-media parsing.

## Reproduction and evidence

From this directory, using Python `C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`:

```
python prepare_candidate.py
python run_tests.py
python seal_delivery.py
```

`prepare_candidate.py` regenerates only this candidate from its frozen input. `run_tests.py` extracts full function definitions directly from candidate C into a host harness; it does not substitute new implementations of those functions. Compiler is MinGW GCC 12.2.0. Compilation timeout is 30 seconds, execution/preprocessing 15 seconds. Exact command arrays and stdout/stderr are in `evidence/host-tests.json`. The first extractor failure is retained separately and was fixed before final passing results.

Actual C tests pass in both direct and FORCE_INDIRECT + COMPUTE_FSINFO modes: `reads=9 writes=0 allocs=4 frees=4`. They exercise bind on non-writable geometry, hardware short/error reads, aligned and cross-sector file reads, EOF, dirty cache rejection, clean/dirty sync, FSInfo suppression, FAT32 count scan, close/unbind cleanup, and all denial wrappers. `fat_open` coverage is only its exact new flag-policy fragment, not the entire lookup/open implementation.

Mocked pieces: block device geometry/data/open/close, mutex/allocator environment, boot-record and FSInfo validators, contiguous get_sectors mapping, and FAT12 getcluster. Real FAT32 free-cluster counting runs on a tiny mocked FAT cache. These results are **selected real C functions with mock dependencies**, not a complete filesystem or target mount test. No actual media or image file was mounted.

Original and default-disabled candidate mount/hwread/hwwrite harnesses both reject non-writable geometry for writable mounts, accept writable geometry, and dispatch one write. Four complete C sources (with includes removed only for preprocessing) have identical non-whitespace output with the option disabled in two feature sets. Enabled preprocessing with LFN/COMPUTE_FSINFO finds zero block-write callback calls, zero timestamp encoder calls, and zero FSInfo-dirty=true assignments. This static check is not a full target compile or proof of all configurations.

## Main-session integration checklist

1. Compare current SDK inputs to `evidence/input-hashes.json`; resolve any mismatch before applying `fat-force-readonly.patch` from the NuttX root. It changes Kconfig and four C files only.
2. Enable FS_FAT and FAT_FORCE_READONLY explicitly in the isolated diagnostic configuration; retain MS_RDONLY at mount for block-driver discovery. Do not interpret that flag as the FAT enforcement mechanism.
3. Compile complete target translation units and check unused-helper/configuration warnings; full target compile was not available to this agent. Test both default-disabled and enabled builds as appropriate.
4. After MSC enumeration succeeds, main session can separately validate mount, real boot/FAT/partition parsing, lookup/open/readdir including LFNs, reader consumption, close/unmount, and failed reads on target. Confirm denied mutator calls and zero low-level write requests with actual driver evidence.
5. Enforce read-only behavior in the lower MSC block layer too. FAT cannot guarantee that driver open/close or an independent raw block user has no side effects. This candidate makes no device-wide write-protection claim.
6. Test actual allocation failures and forced unmount separately. Host balanced allocation counts cover the normal tested lifecycle, not every baseline failure path. No hardware, complete VFS mount, concurrency, corruption robustness, or long-duration acceptance is claimed.

`delivery.json` hashes all candidate artifacts other than itself. Input provenance records source bytes, not an invented upstream version. Original Apache license headers are retained.
