# FAT readonly target build fix

Root reported the first complete target build failing on unused static fat_putsfdirentry with readonly enabled and LFN disabled. This was an uncovered limitation of the earlier selected-function harness. It is not a runtime FAT failure, and target success is not claimed here.

Frozen input: port/tracked/nuttx/fs/fat/fs_fat32dirent.c, SHA256 2cb3dfec0c3005ebcf283108e9646241339dd3724f0091d0f79f7bb6e6285338. Candidate SHA256 8de2d42642d1bc9303f603706f37d533762c0b1414b9cd962c6d0b64c10633a4. Apply fix.patch from NuttX root only after comparing input; or integrate the complete candidate file.

The change wraps declarations and definitions of ten private mutation-only helpers with `#ifndef CONFIG_FAT_FORCE_READONLY`. No function body is changed, no warning is suppressed, no unused attribute is added, and public -EROFS stubs remain present.

| Helpers | Why absent in readonly builds |
| --- | --- |
| fat_putsfdirentry, fat_putsfname | Only called by denied directory writers or each other. |
| fat_putlfname, fat_initlfname, fat_putlfnchunk | Long filename construction, behind denied public writers. |
| fat_createalias, fat_uniquealias, fat_findalias | Alias creation/uniqueness dependency of fat_putlfname. Even read-shaped findalias is private to name creation. |
| fat_allocatesfnentry, fat_allocatelfnentry | Slot allocation dependency of denied fat_allocatedirentry. |

LFN reader checksum, name parsing, matching, lookup, UTF8 conversion and name extraction are retained. Existing LFN conditionals remain nested with the new readonly guards. The fix removes whole unreachable helper chains so that enabling LFN does not merely reveal the next unused writer.

prepare.py freezes the input, generates the patch/candidate, and runs MinGW GCC preprocessing with a15-second timeout per process. LFN disabled, LFN enabled, and LFN+UTF8+LCNAMES+ALIAS_HASH configurations pass: readonly-disabled non-whitespace output is identical; readonly-enabled output contains no declaration/definition/call of all ten helper symbols; key read helpers remain. Includes are stripped solely for this preprocessing check; **this is not complete target compilation**, ABI validation, FAT file I/O or hardware testing. Werror policy was not modified. Root must rerun the actual target build and retain its first failed-build record; additional translation-unit warnings, if any, remain separate findings.

Only this new candidate directory was written. Old candidate and formal sources remain unchanged by this agent. No SDK/device/central-log access or additional agents.
