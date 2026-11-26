#define _GNU_SOURCE
#include <locale.h>
#include <langinfo.h>
#include <iconv.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
static int roundtrip(const char* enc,const char* text){
 char a[256],b[256],*src=(char*)text,*dst=a;
 size_t in=strlen(text),out=sizeof(a);
 iconv_t cd=iconv_open(enc,"UTF-8");
 if(cd==(iconv_t)-1){perror(enc);return 1;}
 if(iconv(cd,&src,&in,&dst,&out)==(size_t)-1 || in){perror("encode");return 2;}
 iconv_close(cd);size_t len=sizeof(a)-out;
 src=a;dst=b;in=len;out=sizeof(b);
 cd=iconv_open("UTF-8",enc);
 if(cd==(iconv_t)-1 || iconv(cd,&src,&in,&dst,&out)==(size_t)-1 || in){perror("decode");return 3;}
 iconv_close(cd);
 if(sizeof(b)-out!=strlen(text)||memcmp(text,b,strlen(text)))return 4;
 printf("PASS %s round trip\n",enc);return 0;
}
int main(void){
 if(!setlocale(LC_ALL,"")){fprintf(stderr,"locale missing\n");return 1;}
 printf("locale %s codeset %s\n",setlocale(LC_CTYPE,NULL),nl_langinfo(CODESET));
 if(strcmp(nl_langinfo(CODESET),"UTF-8"))return 2;
 const char* ko="\xed\x95\x9c\xea\xb8\x80 \xed\x8c\x8c\xec\x9d\xbc";
 const char* jp="\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e";
 if(roundtrip("CP949",ko)||roundtrip("EUC-KR",ko)||roundtrip("CP932",jp)||roundtrip("SHIFT_JIS",jp)||roundtrip("UTF-16LE",ko)||roundtrip("CP1252","caf\xc3\xa9")||roundtrip("CP437","caf\xc3\xa9"))return 3;
 return 0;
}
