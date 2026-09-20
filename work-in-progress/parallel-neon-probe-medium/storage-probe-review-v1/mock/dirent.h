typedef struct mock_dir {int unused;} DIR;
struct dirent {char d_name[256];};
DIR *opendir(const char*);
struct dirent *readdir(DIR*);
int closedir(DIR*);
