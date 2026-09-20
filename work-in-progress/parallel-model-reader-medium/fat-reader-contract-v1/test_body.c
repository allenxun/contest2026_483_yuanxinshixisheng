/* Runs exact extracted FAT functions; cache, clock, lock and mount health mocked. */
static void size_field(uint8_t*p,uint32_t n){for(unsigned i=0;i<4;i++)p[28+i]=(uint8_t)(n>>(8*i));}
int main(void){
 uint8_t sector[512]={0};
 struct fat_mountpt_s fs={sector,0,512,8};
 struct inode ino={&fs};
 struct fat_file_s ff={0,0,123,2};
 struct file f={&ino,&ff,0};
 struct stat a,b;
 size_field(sector,123);
 memset(&a,0xa5,sizeof a);
 assert(fat_stat_file(&fs,sector,&a)==0);
 assert(a.st_dev==0 && a.st_ino==0 && a.st_size==123 && (a.st_mode&S_IFREG));
 size_field(sector+32,456);sector[32]='B';ff.ff_dirindex=1;
 assert(fat_fstat(&f,&b)==0 && b.st_size==456);
 assert(a.st_dev==b.st_dev && a.st_ino==b.st_ino);
 /* fstat uses directory cache size, not the file-open ff_size snapshot. */
 assert(ff.ff_size==123);
 cache_error=-EIO;assert(fat_fstat(&f,&b)==-EIO);cache_error=0;
 health_error=-ENODEV;assert(fat_fstat(&f,&b)==-ENODEV);health_error=0;
#if OFF_BITS == 64
 const uint32_t sizes[]={0,1,0x7fffffffU,0x80000000U,0xfffffffeU,0xffffffffU};
 for(unsigned i=0;i<sizeof sizes/sizeof sizes[0];i++){
  size_field(sector,sizes[i]);assert(fat_stat_file(&fs,sector,&a)==0);
  assert(a.st_size==(int64_t)sizes[i]);ff.ff_size=a.st_size;
  assert(fat_seek(&f,a.st_size,SEEK_SET)==a.st_size);
 }
 /* FAT permits beyond EOF; mr absolute-range check must reject it first. */
 assert(fat_seek(&f,INT64_C(0x100000000),SEEK_SET)==INT64_C(0x100000000));
 assert(fat_seek(&f,-1,SEEK_SET)==-EINVAL);
 flush_error=-EROFS;assert(fat_seek(&f,0,SEEK_SET)==-EROFS);flush_error=0;
 printf("PASS off64: FAT sizes 0..UINT32_MAX; exact SEEK_SET >2GiB; beyond EOF allowed; stat/fstat identity collision; errors preserved\n");
#else
 assert(fat_seek(&f,123,SEEK_SET)==123);
 /* Current GCC narrowing behavior, not a portable C promise for out-of-range casts. */
 size_field(sector,UINT32_MAX);assert(fat_stat_file(&fs,sector,&a)==0);
 assert(a.st_size==-1);
 printf("PASS off32 mock: UINT32_MAX narrows to -1 on this GCC; reader must require target off_t64\n");
#endif
 return 0;
}
