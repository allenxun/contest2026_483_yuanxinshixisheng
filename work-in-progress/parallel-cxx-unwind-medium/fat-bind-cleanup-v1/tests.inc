static void reset(void){assert(!live&&!io_live&&!locks);fail_kind=opened=closed=open_error=close_error=0;}
int main(void){
 struct bops ops={mock_open,mock_close,mock_geo};struct inode inode={{&ops},7};
 void *handle;struct inode *returned;unsigned checks=0;
 int expected[]={0,-ENOMEM,-ENODEV,-ENOMEM,-EIO,-EINVAL,-EILSEQ};
 for(int f=1;f<=6;f++)for(int cerr=0;cerr<=1;cerr++){
   reset();fail_kind=f;close_error=cerr?-EIO:0;handle=(void*)(uintptr_t)1;
   int result=fat_bind(&inode,NULL,&handle);
   assert(result==expected[f]&&opened==1&&closed==1&&handle==(void*)(uintptr_t)1);
   assert(inode.i_crefs==7&&!live&&!io_live&&!locks);checks++;
 }
 reset();open_error=-EACCES;handle=NULL;assert(fat_bind(&inode,NULL,&handle)==-ENODEV&&opened==1&&!closed&&!live);checks++;
 reset();assert(fat_bind(NULL,NULL,&handle)==-ENODEV&&!opened&&!closed);checks++;
 reset();ops.open=NULL;fail_kind=1;assert(fat_bind(&inode,NULL,&handle)==-ENOMEM&&!opened&&!closed);ops.open=mock_open;checks++;
 reset();ops.close=NULL;fail_kind=1;assert(fat_bind(&inode,NULL,&handle)==-ENOMEM&&opened==1&&!closed);ops.close=mock_close;checks++;
 reset();handle=NULL;assert(fat_bind(&inode,NULL,&handle)==0&&handle&&opened==1&&!closed&&live==1&&io_live==1);
 returned=NULL;assert(fat_unbind(handle,&returned,0)==0&&returned==&inode&&closed==1&&!live&&!io_live&&!locks&&inode.i_crefs==7);checks++;
 /* Open files make unbind busy: do not close/release the retained mount. */
 reset();assert(!fat_bind(&inode,NULL,&handle));struct fat_file_s file={0,NULL};
 ((struct fat_mountpt_s*)handle)->fs_head=&file;assert(fat_unbind(handle,&returned,0)==-EBUSY&&!closed&&live==1);
 ((struct fat_mountpt_s*)handle)->fs_head=NULL;assert(!fat_unbind(handle,&returned,0)&&closed==1&&!live);checks++;
 /* VFS successful bind followed by mountpoint allocation failure uses unbind. */
 reset();assert(!fat_bind(&inode,NULL,&handle));assert(!fat_unbind(handle,&returned,0)&&closed==1&&inode.i_crefs==7);checks++;
 printf("PASS %u actual fat_bind/fat_mount/fat_unbind ownership paths\n",checks);return 0;
}
