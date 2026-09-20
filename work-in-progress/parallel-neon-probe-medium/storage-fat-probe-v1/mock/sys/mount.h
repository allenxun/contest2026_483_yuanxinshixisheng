#define MS_RDONLY 1
int mount(const char *, const char *, const char *, unsigned long, const void *);
int umount2(const char *, unsigned int);
