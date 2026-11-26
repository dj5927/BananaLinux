#include <fluidsynth.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
int main(int argc,char**argv){
 if(argc!=3)return 2;
 fluid_settings_t*s=new_fluid_settings();
 fluid_settings_setnum(s,"synth.sample-rate",44100.0);
 fluid_settings_setint(s,"synth.reverb.active",0);
 fluid_settings_setint(s,"synth.chorus.active",0);
 fluid_synth_t*f=new_fluid_synth(s);
 int id=fluid_synth_sfload(f,argv[1],1);
 if(id<0)return 3;
 int16_t buf[4096]={0};
 if(fluid_synth_noteon(f,0,60,100)!=FLUID_OK)return 4;
 if(fluid_synth_write_s16(f,2048,buf,0,2,buf,1,2)!=FLUID_OK)return 5;
 long long total=0;for(int i=0;i<4096;i++)total+=abs(buf[i]);
 if(total==0)return 6;
 printf("PASS SF2 synthesis: %lld nonzero signal magnitude\n",total);
 delete_fluid_synth(f);delete_fluid_settings(s);
 FT_Library l;FT_Face face;
 if(FT_Init_FreeType(&l)||FT_New_Face(l,argv[2],0,&face))return 7;
 if(FT_Set_Pixel_Sizes(face,0,16)||FT_Load_Char(face,'A',FT_LOAD_RENDER))return 8;
 printf("PASS font render: %s %ux%u\n",face->family_name,face->glyph->bitmap.width,face->glyph->bitmap.rows);
 FT_Done_Face(face);FT_Done_FreeType(l);
 return 0;
}
