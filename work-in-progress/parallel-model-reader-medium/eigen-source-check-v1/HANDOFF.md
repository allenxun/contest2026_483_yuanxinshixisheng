# Eigen source check: archive mismatch, exact source tree verified

**The original ORT SHA1 lock was not changed and no archive matching it was found. However, a source-tree verification route now succeeds against the official fixed Git commit.** This permits root to review a separate Git-source provenance path; it does not make the mismatched ZIP pass its original archive checksum.

## Reproduced facts

ORT1.17.1 cmake/deps.txt expects Eigen commit `e7248b26a1ed53fa030c5c459f7ea095dfd276ac`, archive SHA1 `be8be39fdbc6e60e94fa7870b280707069b5b81a`. Its comment says this commit corresponds to previously consumed3.4 branch contents; that comment alone does not prove which ZIP metadata changed.

Downloaded only the same official [GitLab commit ZIP](https://gitlab.com/libeigen/eigen/-/archive/e7248b26a1ed53fa030c5c459f7ea095dfd276ac/eigen-e7248b26a1ed53fa030c5c459f7ea095dfd276ac.zip), bounded8MiB. Reproduced3840681 bytes, SHA1 `32b145f525a8308d7ab1c09388b2e288312d8eba`, SHA256 `a50ef69dad8d694136806051841a382f09290c9af811b13a2955b56640484007`. Kept as **unaccepted-eigen.zip** only in this evidence directory. Its ZIP comment names the fixed commit, but that comment was not accepted as proof.

Official [commit API](https://gitlab.com/api/v4/projects/libeigen%2Feigen/repository/commits/e7248b26a1ed53fa030c5c459f7ea095dfd276ac) confirms the referenced commit metadata; response frozen. Independently fetched the exact commit from `https://gitlab.com/libeigen/eigen.git` with `--depth=1 --no-tags`. First Git schannel attempt failed SEC_E_NO_CREDENTIALS; Git OpenSSL retry passed with normal certificate validation, no credential helper/prompt or private config. Exact commands/results retained.

## Stronger verification than archive filename/comment

`compare_tree.py` reads the real Git commit object and verifies Git's SHA1(`commit <size>\0<bytes>`) equals the required commit. Its root tree is **3142f2e6ec15a2cb94c6d1bb751953cbc5f1c948**. `git ls-tree -rz` freezes all1784 path/mode/blob IDs. Every ZIP file path and content hashes to the corresponding Git blob; no missing/extra files, total uncompressed15447515 bytes.29 executable files carry100755;1755 ordinary ZIP entries use DOS format and omit POSIX mode, whose100644 value is taken from the fixed Git tree. There are no symlinks/gitlinks in this tree.

Initial strict raw-mode comparison recorded1755 zero-vs100644 mode differences; no content differences. This is preserved in tree-comparison.json, not hidden. `prove_tree.py` checks executable bits, uses verified Git modes, reconstructs all Git directory/tree objects from ZIP content identities and modes, and reproduces the exact root tree. **tree-proof.json is the final source-tree proof.** Ordinary-file mode absence is archive metadata, not a source-byte discrepancy.

We also regenerated ZIPs via local Git archive with both commit-name and eigen-3.4 prefixes. Neither matches the ORT archive hash; regenerated.json records both. Their different byte hashes show same-commit archives are not inherently byte-identical, but the precise historical change (GitLab ZIP tool/version/compression/root prefix/timestamps) remains unknown without the original matching archive. Do not assert a specific metadata cause as proven.

## Minimum root action

Keep original deps.txt and rejected-archive evidence unchanged. Either obtain the exact old archive later, or use the **official Git commit/tree** as an explicitly reviewed alternative source acquisition mode, recording commit, root tree, content/mode manifest and any produced archive SHA256. The fetched Git object database is local `git-proof/.git`; do not execute source scripts. Root can archive/extract this fixed tree in a new dependency staging location after verification. Do not overwrite an existing eigen.zip and claim old SHA1 passed; any CMake source override should point to the separately verified source tree with its provenance manifest.

Reproduce offline: `python -B compare_tree.py`, then `python -B prove_tree.py` (each Git subprocess bounded20s). Fetch scripts have explicit timeouts and only public official remote. No SDK/formal/dependency-lock modification, no builds, no devices, no other dependency investigation. The local fetched pack and3 ZIP variants are evidence of this narrow Eigen check, not a new generic dependency mirror.
