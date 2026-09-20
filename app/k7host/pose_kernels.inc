/* SPDX-License-Identifier: Apache-2.0 */
static void pose_pool(const float *a,float *b,int c,int h,int w,int average)
{
  for(int ch=0;ch<c;ch++)for(int y=0;y<h/2;y++)for(int x=0;x<w/2;x++) {
    const float *p=a+ch*h*w+y*2*w+x*2;
    b[(ch*h/2+y)*w/2+x]=average ? (p[0]+p[1]+p[w]+p[w+1])*.25f :
      fmaxf(fmaxf(p[0],p[1]),fmaxf(p[w],p[w+1]));
  }
}
static void pose_gemm(const float *a,const float *w,const float *bias,float *b,int m,int k,int n)
{
  for(int i=0;i<m;i++)for(int j=0;j<n;j++) {
    float v=0;for(int t=0;t<k;t++)v+=a[i*k+t]*w[j*k+t];b[i*n+j]=v+bias[j];
  }
}
static void pose_mm(const float *a,const float *w,float *b,int m,int k,int n)
{
  for(int i=0;i<m;i++)for(int j=0;j<n;j++)b[i*n+j]=0;
  for(int i=0;i<m;i++)for(int t=0;t<k;t++) {
    float v=a[i*k+t];for(int j=0;j<n;j++)b[i*n+j]+=v*w[t*n+j];
  }
}
static void pose_sum(const float *a,float *b,int outer,int dim,int inner)
{
  for(int i=0;i<outer;i++)for(int j=0;j<inner;j++) {
    float v=0;for(int k=0;k<dim;k++)v+=a[(i*dim+k)*inner+j];b[i*inner+j]=v;
  }
}
