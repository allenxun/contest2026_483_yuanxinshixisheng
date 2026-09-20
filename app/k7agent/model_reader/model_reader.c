#define _FILE_OFFSET_BITS 64
#define _POSIX_C_SOURCE 200809L
#include "model_reader.h"
#include <errno.h>
#include <stdio.h>
#include <limits.h>
#include <string.h>
#include <sys/stat.h>
#include <fcntl.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#define MR_STAT struct _stat64
#define MR_FSTAT _fstat64
#define MR_READ _read
#define MR_SEEK _lseeki64
#define MR_CLOSE _close
#define MR_REG(s) (((s).st_mode & _S_IFMT) == _S_IFREG)
#else
#include <unistd.h>
#define MR_STAT struct stat
#define MR_FSTAT fstat
#define MR_READ read
#define MR_SEEK lseek
#define MR_CLOSE close
#define MR_REG(s) S_ISREG((s).st_mode)
#endif
#ifdef MR_TESTING
/* Test-only injection around real host syscalls, absent from production object. */
static struct { int eintr, short_read, eof, read_error, stat_error, seek_error, closes, close_error; } fault;
#endif
static int saved_errno(void) { return errno ? errno : EIO; }
int mr_close(mr_file *f) {
    int rc = 0;
    if (!f) return EINVAL;
    if (f->fd >= 0) {
        int fd = f->fd; f->fd = -1;
        /* Never retry close after EINTR: descriptor ownership may already be gone. */
        if (MR_CLOSE(fd) < 0) rc = saved_errno();
#ifdef MR_TESTING
        ++fault.closes;
        if (fault.close_error) rc = EIO; /* real close already performed */
#endif
    }
    f->length = f->position = f->max_read = 0;
    f->close_error = rc;
    return rc;
}
static int fail(mr_file *f, int e) { mr_close(f); return e; }
static int checked_size(mr_file *f) {
    MR_STAT st;
#ifdef MR_TESTING
    if (fault.stat_error) return EIO;
#endif
    if (MR_FSTAT(f->fd, &st) < 0) return saved_errno();
    if (!MR_REG(st) || st.st_size < 0 || (uint64_t)st.st_size != f->length) return EIO;
    return 0;
}
#ifdef _WIN32
static int safe_windows_path(const char *p) {
    /* Restrict to ordinary absolute drive paths; reject UNC, NT namespaces,
       alternate streams, traversal, trailing-dot/space aliases and DOS devices. */
    size_t n;
    if (!p || !((p[0]>='A'&&p[0]<='Z')||(p[0]>='a'&&p[0]<='z')) || p[1]!=':' || (p[2]!='/'&&p[2]!='\\')) return 0;
    p += 3;
    while (*p) {
        const char *s=p; char base[16]; size_t k=0;
        while (*p && *p!='/' && *p!='\\') {
            unsigned char c=(unsigned char)*p;
            if (c<32 || c>=127 || c==':' || c=='?' || c=='*' || c=='"' || c=='<' || c=='>' || c=='|') return 0;
            ++p;
        }
        n=(size_t)(p-s);
        if (!n || s[n-1]=='.' || s[n-1]==' ') return 0;
        while (k<n && s[k]!='.' && k<sizeof(base)-1) { char c=s[k]; base[k]=(c>='a'&&c<='z')?(char)(c-32):c; ++k; }
        base[k]=0;
        if (!strcmp(base,"CON") || !strcmp(base,"PRN") || !strcmp(base,"AUX") || !strcmp(base,"NUL") || !strcmp(base,"CONIN$") || !strcmp(base,"CONOUT$") || (k==4 && (!memcmp(base,"COM",3)||!memcmp(base,"LPT",3)) && base[3]>='0'&&base[3]<='9')) return 0;
        if (*p) { ++p; if (!*p) return 0; }
    }
    return 1;
}
#endif
int mr_open(mr_file *f, const char *path, uint64_t expected, uint64_t maximum, uint64_t read_budget) {
    if (!f) return EINVAL;
    if (f->fd >= 0) return fail(f, EBUSY);
    f->close_error=0;
    if (!path || !expected || expected>maximum || expected>INT64_MAX || !read_budget || read_budget>SIZE_MAX) return fail(f,EINVAL);
#ifdef _WIN32
    {
        HANDLE h; BY_HANDLE_FILE_INFORMATION info; DWORD attrs;
        if (!safe_windows_path(path)) return fail(f, EACCES);
        attrs=GetFileAttributesA(path);
        if (attrs==INVALID_FILE_ATTRIBUTES) return fail(f, ENOENT);
        if (attrs&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DEVICE)) return fail(f,EACCES);
        h=CreateFileA(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
        if (h==INVALID_HANDLE_VALUE) return fail(f,EACCES);
        if (GetFileType(h)!=FILE_TYPE_DISK || !GetFileInformationByHandle(h,&info) || (info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DEVICE))) {
            CloseHandle(h); return fail(f,EACCES);
        }
        f->fd=_open_osfhandle((intptr_t)h,_O_RDONLY|_O_BINARY);
        if (f->fd<0) { int e=saved_errno(); CloseHandle(h); return fail(f,e); }
    }
#else
    /* Explicit integrator opt-in: verified regular-file mount + trusted ancestors.
       Without real 64-bit off_t / nofollow / nonblock, reject before open. */
#if defined(MR_POSIX_TRUSTED_FILES) && defined(O_NOFOLLOW) && defined(O_NONBLOCK)
    {
        struct stat before;
        if (sizeof(off_t)<8) return fail(f,ENOTSUP);
        if (path[0]!='/' || !strncmp(path,"/dev/",5) || !strcmp(path,"/dev")) return fail(f,EACCES);
        if (lstat(path,&before)<0) return fail(f,saved_errno());
        if (!S_ISREG(before.st_mode)) return fail(f,EACCES);
        f->fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);
        if (f->fd<0) return fail(f,saved_errno());
        { struct stat after;
          if(fstat(f->fd,&after)<0) return fail(f,saved_errno());
          if(!S_ISREG(after.st_mode)||before.st_dev!=after.st_dev||before.st_ino!=after.st_ino) return fail(f,EACCES);
        }
    }
#else
    return fail(f,ENOTSUP);
#endif
#endif
    f->length=expected; f->position=0; f->max_read=read_budget;
    { int e=checked_size(f); if(e) return fail(f,e); }
    return mr_seek(f,0);
}
int mr_seek(mr_file *f, uint64_t offset) {
    int e;
    if (!f) return EINVAL;
    if (f->fd<0) return EBADF;
    if(offset>f->length || offset>INT64_MAX) return fail(f,EOVERFLOW);
    e=checked_size(f); if(e) return fail(f,e);
#ifdef MR_TESTING
    if(fault.seek_error) return fail(f,EIO);
#endif
    if(MR_SEEK(f->fd,(int64_t)offset,SEEK_SET)!=(int64_t)offset) return fail(f,saved_errno());
    f->position=offset; return 0;
}
int mr_read_exact(mr_file *f, void *dst, size_t len) {
    size_t done=0; unsigned interrupts=0; int e;
    if(!f) return EINVAL;
    if(f->fd<0) return EBADF;
    if((len&&!dst) || (uint64_t)len>f->max_read || f->position>f->length || (uint64_t)len>f->length-f->position) return fail(f,EINVAL);
    e=checked_size(f); if(e) return fail(f,e);
    while(done<len) {
        size_t chunk=len-done; int64_t got;
        if(chunk>65536) chunk=65536;
#ifdef MR_TESTING
        if(fault.eintr>0) { --fault.eintr; errno=EINTR; got=-1; }
        else if(fault.read_error) { errno=EIO; got=-1; }
        else if(fault.eof) got=0;
        else { if(fault.short_read && chunk>2) chunk=2; got=MR_READ(f->fd,(char*)dst+done,(unsigned)chunk); }
#else
        got=MR_READ(f->fd,(char*)dst+done,(unsigned)chunk);
#endif
        if(got<0) { if(errno==EINTR && ++interrupts<=16) continue; return fail(f,saved_errno()); }
        if(got==0 || (uint64_t)got>chunk) return fail(f,EIO);
        done+=(size_t)got; f->position+=(uint64_t)got;
    }
    e=checked_size(f); return e?fail(f,e):0;
}

