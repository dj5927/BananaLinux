/* Tests emulate RG DS CONFIG_PROC_CHILDREN=n even on a full desktop kernel. */
#include <stdio.h>
#include <string.h>
#include <errno.h>
FILE *__real_fopen(const char *,const char *);
FILE *__wrap_fopen(const char *path,const char *mode)
{
    size_t n=strlen(path);
    if(n>=9 && !strcmp(path+n-9,"/children")){errno=ENOENT;return NULL;}
    return __real_fopen(path,mode);
}