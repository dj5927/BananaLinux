#include "filefinder.h"
#include "filesystem.h"
#include "bitmap.h"
#include <cstdio>
#include <string>
int main(int argc,char**argv){
 if(argc!=3)return 1;
 auto fs=FileFinder::Root().Create(FileFinder::MakeCanonical(argv[1],0));
 if(!fs){fprintf(stderr,"bad filesystem\n");return 2;}
 FileFinder::SetGameFilesystem(fs);
 const std::string request=argv[2];
 auto found=FileFinder::FindImage("picture",request);
 if(found.empty()){fprintf(stderr,"missing image %s\n",request.c_str());return 3;}
 auto stream=FileFinder::Game().OpenInputStream(found);
 if(!stream){fprintf(stderr,"cannot read %s\n",found.c_str());return 4;}
 Bitmap::SetFormat(DynamicFormat(32,8,16,8,8,8,0,8,24,PF::Alpha));
 auto bmp=Bitmap::Create(std::move(stream),false);
 if(!bmp||bmp->GetWidth()!=16||bmp->GetHeight()!=12){fprintf(stderr,"bad image\n");return 5;}
 printf("PASS image lookup and PNG decode: %s\n",found.c_str());
 return 0;
}
