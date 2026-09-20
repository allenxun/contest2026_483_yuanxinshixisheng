# FAT → model_reader contract audit

Unintegrated read-only audit and selected-function host tests. No SDK, USB device, model, formal source or central log access/write. Input hashes are in evidence/inputs.json. This supplements parallel-neon-probe-medium/model-file-integration-v1/HANDOFF.md; its loader reopen analysis is not duplicated or solved here.

## Findings that affect enablement

**Current FAT st_dev/st_ino are not usable file identities.** fs_fat32.c:2960 fat_stat_file zeroes the entire stat then fills mode, times, size and block accounting; neither identity field is assigned. fat_stat and fat_fstat share this function. VFS fs_stat.c:131 and fs_fstat.c:200 directly call mountpoint methods and do not subsequently fill identity fields. The pseudo-filesystem inode_stat assignment of inode->i_ino does not cover this FAT path. Two different FAT directory entries both report (0,0), as the host test confirms. Consequently mr_open's before/after equality check accepts that collision and cannot detect a path replacement. It does not check that identities are nonzero or meaningful.

**FAT directory length remains 32 bits with off_t64.** DIR_FILESIZE is four bytes at offset 28, decoded as uint32_t; open snapshots it into off_t ff_size (fs_fat32.c:361), and stat_common assigns it to st_size (:2944). Require CONFIG_FS_LARGEFILE=y in the actual target: types.h selects int64_t versus int32_t with this switch. _FILE_OFFSET_BITS=64 in reader does not control the NuttX typedef. The representation ceiling for this single FAT file is UINT32_MAX = 4,294,967,295 bytes, not 4 GiB inclusive. Files above that cannot be represented by this FAT implementation. Under off_t32, lengths above INT32_MAX cannot be represented; host ABI-shape test demonstrates UINT32_MAX→-1 on this GCC (the out-of-range C conversion is implementation-defined). Do not silently advertise a 2 GiB fallback: current mr_open explicitly rejects sizeof(off_t)<8.

**fstat is not a fresh-media truncation oracle.** fat_fstat reads the stored directory sector/index and reports the directory-entry size, not ff_size. fat_fscacheread (util:1819) skips the hardware read when that sector is already cached. Meanwhile fat_read uses the open-time ff_size. An external rewrite/truncation may therefore remain invisible to fstat, and cached file sectors may remain readable. No stat comparison, same-fd ownership, or one-time SHA can alone guarantee subsequent immutable USB content.

| Reader contract | Frozen FAT behavior and minimal integration requirement |
| --- | --- |
| Regular file | stat_file reports S_IFREG or S_IFDIR; volume-ID entries rejected. Writable mode bits reflect directory attributes even in forced read-only mode; mode bits do not certify enforcement. |
| Path identity | Equality of st_dev/st_ino offers no FAT identity protection. Do not call it same-file verification. Keep generic reader default closed until explicit trusted-volume policy is installed. |
| Absolute seek | fat_seek permits any nonnegative position, including beyond EOF. mr_seek rejects offsets >expected length/INT64_MAX and exclusively uses SEEK_SET, avoiding FAT SEEK_CUR/END unchecked signed additions. |
| Seek health | FAT same-sector shortcut precedes mount check. mr_seek performs checked_size **before** lseek, not after; retain its exact-return check, but do not claim atomic media/position validation. |
| Exact read | FAT caps to ff_size; mr loops positive short reads, uses <=65536-byte syscalls, rejects premature zero/over-return, checks fstat before/after, and closes on error. Partial caller buffer must be discarded. |
| Truncation | Visible directory size mismatch causes checked_size EIO. A short EOF before expected length fails closed. Cached same-size changes or unseen external truncation are not necessarily detected. |
| EINTR/error | Public VFS wrappers convert negative FAT errno to -1/errno. mr permits at most 16 EINTR retries per entire read_exact, then closes; other error closes immediately. No hardware deadline is implied. |
| Ownership | fd is cleared before close; close not retried after EINTR; close_error retained. mr_seek failure closes; closed operations return EBADF. No duplicated fd or second I/O owner. |
| Zero length | FAT represents empty files, but current mr_open rejects expected=0; test/stat support for zero must not be advertised as acceptance of an empty model. |

## Minimal actionable wiring

1. Preserve MR_POSIX_TRUSTED_FILES disabled in general builds. For a dedicated validated target only, add compile-time assertions for sizeof(off_t)>=8 and sizeof(stat.st_size)>=8 and verify CONFIG_FS_LARGEFILE in that exact image. Set trusted manifest limits: 0 < expected <= min(product model budget, UINT32_MAX), read budget bounded (for example 64 KiB). Reject an oversized manifest before opening. Do not derive trusted expected length/SHA from the same untrusted USB file.
2. Use one fixed, canonical regular-file path beneath a main-session configured mount root. No caller-controlled root, traversal, aliases, symlink ancestors, remount or hot-swap during the owner lifetime. Establish a mount/media session owner before lstat/open and hold it through hash and final reader close. Abort the session on disconnect/media change. Physical external writes are outside what this software policy can prove.
3. Explicitly document FAT identity as unsupported in that policy; merely setting MR_POSIX_TRUSTED_FILES does not upgrade the zero fields. If no trustworthy mount/path exclusivity can be provided, retain refusal. If general mutable-volume support is required later, a separate FAT identity design needs per-mount generation plus directory location and lifecycle semantics; synthesizing st_ino from a cluster or setting every st_dev nonzero is insufficient and is outside this minimal candidate.
4. Require the separate FAT_FORCE_READONLY and lower MSC write barriers, validated against the integrated image; ordinary MS_RDONLY alone is insufficient in this frozen mount API. Retain clean unbind ownership through final close. Any media epoch abstraction must come from the real driver, not a constant mock getter.
5. Pass the same opened owner to the integrity gate and reset its successful position to zero before parsing. Follow C's single-owner loader adapter proposal; its reopen problem remains unresolved. No model-load readiness claim until both that adapter and this filesystem policy are implemented and tested.

## Host evidence and precise limits

Run `C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe run_tests.py` from this directory. Command arrays, stdout and timeouts are in evidence/results.json. Compile timeout 30 seconds; executable timeout 15 seconds. First off32 build failed only because the extracted seek helper was unused under -Werror; attempt-01.json is retained, and final test calls it in both modes.

The runner extracts full unchanged fat_stat_common, fat_stat_file, fat_fstat and fat_seek definitions from the frozen source. ABI-shape structs/macros, mutex, timestamp conversion, mount-health and cache dependencies are explicitly mocked. It is not compiled against complete target headers and does not mount a filesystem. No model_reader runtime test was added; its short-read/error behavior above is a source audit, with prior host reader tests remaining separate evidence.

Passing off64 cases: sizes 0, 1, INT32_MAX, INT32_MAX+1, UINT32_MAX-1, UINT32_MAX; absolute seeks at those sizes; FAT acceptance of 4 GiB beyond EOF; negative seek rejection; directory-versus-open-size difference; two-entry identity collision; fstat cache/health and seek flush error propagation. Off32 mock confirms an ordinary seek and nonrepresentable maximum-size behavior on GCC. The stat mock uses widened accounting members to isolate st_size; it does not validate target st_blocks arithmetic/ABI.

No real reads near 2/4 GiB were run here, no large file was created, and these tests are not real USB acceptance. The earlier fat-readonly-v1 selected-read harness remains separate evidence and is not promoted to full FAT chain coverage.

## Required target tests before opening the gate

- Exact image shape/link checks plus two distinct real regular files: record stat/fstat identities, sizes and modes; expect identity limitations above rather than requiring invented distinct numbers.
- Fixed small file: cross-sector and cross-cluster read_exact, EOF, seek0, bounded read, close/unmount. Trusted SHA match/mismatch and restoration of offset zero. Record all actual errors and no writes.
- Readonly denial tests and disconnect/read-error behavior only under the main session's device procedure; do not promise O_NONBLOCK hard deadlines.
- Where controlled FAT media preparation is separately authorized, directory sizes/real reads around 2 GiB and the FAT ceiling. This task creates no such media. Metadata-only mock boundaries do not establish actual cluster-chain support at those sizes.
- Verify mount exclusivity/path whitelist/media invalidation policy and same-owner loader wiring. A filename reopen, cached fstat result, or (0,0) identity equality cannot satisfy these tests.
