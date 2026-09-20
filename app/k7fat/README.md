# Explicit read-only FAT diagnostic

Fixed /dev/sda to /mnt/k7model. Separate mount/list/unmount commands; no mkdir, file writes, formatting or model loading. One mount attempt per boot; bounded hex directory names; failed close/umount state retained. Caller must establish that sda is the newly enumerated owned USB media.
