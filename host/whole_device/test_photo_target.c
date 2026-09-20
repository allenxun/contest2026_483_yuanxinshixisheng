#include <assert.h>
#include <stdio.h>
#include "../../app/k7host/k7_photo_target.h"
int main(void) {
 struct k7_face_s target={60,20,60,80,.99f};
 struct k7_faces_s f={.count=1,.face={target}};
 assert(k7_photo_target_count(&f,&target)==1);
 f.count=2;f.face[1]=(struct k7_face_s){5,5,15,15,.95f};
 assert(k7_photo_target_count(&f,&target)==1);
 f.face[1]=(struct k7_face_s){5,20,30,40,.95f};
 assert(k7_photo_target_count(&f,&target)==2); /* Exact 25%% boundary. */
 f.face[1]=(struct k7_face_s){65,25,15,15,.95f};
 assert(k7_photo_target_count(&f,&target)==2); /* Even small overlapping face. */
 f.face[1]=(struct k7_face_s){0,20,50,80,.95f};
 assert(k7_photo_target_count(&f,&target)==2);
 f.face[1].x=NAN;assert(k7_photo_target_count(&f,&target)==2);
 f.count=1;f.face[0]=(struct k7_face_s){0,0,10,10,.95f};
 assert(k7_photo_target_count(&f,&target)==2); /* Tracked target absent. */
 f.count=0;assert(k7_photo_target_count(&f,&target)==0);
 f.count=K7_FACE_MAX+1;assert(k7_photo_target_count(&f,&target)==2);
 puts("photo foreground/background ambiguity checks: PASS");
}
