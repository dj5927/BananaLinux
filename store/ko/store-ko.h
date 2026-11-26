// Korean Store UI and package-manager display strings. Installation IDs,
// command verbs and machine-readable package-manager protocol stay unchanged.
#pragma once
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

static int store_ko(void) {
    const char *lang = getenv("BANANA_UI_LANG");
    return lang && !strcmp(lang, "ko");
}
static const char *K(const char *en, const char *ko) { return store_ko() ? ko : en; }

static const char *store_job_text(const char *s, char *buf, size_t n) {
    if (!store_ko()) return s;
    static const struct { const char *en, *ko; } exact[] = {
        {"Starting","시작 중"}, {"It didn't run","실행하지 못했습니다"},
        {"No thread","작업 스레드를 만들지 못했습니다"}, {"No network","네트워크 연결 없음"},
        {"It failed","작업 실패"}, {"Putting it back on the menu","메뉴에 다시 추가하는 중"},
        {"Looking for it","패키지를 찾는 중"}, {"Checking it","파일을 검증하는 중"},
        {"Setting it up","설정하는 중"}, {"Adding it to the menu","메뉴에 추가하는 중"},
        {"Taking it off the menu","메뉴에서 제거하는 중"}, {"Removing it","제거하는 중"},
        {"Not made for this handheld","이 기종에서는 지원하지 않습니다"},
        {"Needs a newer BananaOS","최신 BananaOS가 필요합니다"},
        {"It's running: quit it first","실행 중인 앱을 먼저 종료하세요"},
        {"Package damaged","패키지가 손상되었습니다"}, {"Not in this BananaOS","현재 BananaOS에 포함되어 있지 않습니다"},
        {"No release yet","아직 릴리스가 없습니다"}, {"Download failed","다운로드 실패"},
        {"No checksum published for it","공개된 체크섬이 없습니다"}, {"Download damaged","다운로드 파일이 손상되었습니다"},
        {"Wrong app inside","다른 앱이 포함되어 있습니다"}, {"Package incomplete","패키지가 불완전합니다"},
        {"Wrong version inside","패키지 버전이 일치하지 않습니다"}, {"Run it as root","root 권한이 필요합니다"},
        {"The Store is busy with another job","스토어에서 다른 작업을 실행 중입니다"},
        {"The Store doesn't remove itself (RNDS_STORE_FORCE=1 to insist)","스토어 자체는 제거할 수 없습니다"},
    };
    for (size_t i=0;i<sizeof exact/sizeof exact[0];i++) if (!strcmp(s,exact[i].en)) return exact[i].ko;
    static const struct { const char *en, *ko; } prefixes[] = {
        {"Downloading ","다운로드 중: "}, {"Installing ","설치 중: "},
        {"Needs ","필요 버전: "}, {"No app called ","앱을 찾을 수 없음: "},
        {"Its setup script failed (","설정 스크립트 실패 ("},
        {"bad path in the package's layout: ","잘못된 패키지 경로: "},
    };
    for (size_t i=0;i<sizeof prefixes/sizeof prefixes[0];i++) {
        size_t len=strlen(prefixes[i].en);
        if (!strncmp(s,prefixes[i].en,len)) {
            snprintf(buf,n,"%s%s",prefixes[i].ko,s+len);
            return buf;
        }
    }
    return s; // external error details remain intact
}

static void store_localize_catalog(App *a) {
    if (!store_ko()) return;
    static const struct {const char *id,*genre,*summary,*desc;} rows[] = {
        {"ereaderds", "전자책", "책처럼 기기를 옆으로 잡고 두 화면으로 읽는 전자책 뷰어.", "각 화면에 한 페이지씩 표시합니다. EPUB, TXT, 만화(.cbz)를 읽을 수 있습니다. 책갈피, 하이라이트, 사전, 테마, 글꼴, KOReader 동기화, Standard Ebooks·Project Gutenberg 등의 카탈로그 및 Wi-Fi 파일 전송을 지원합니다.\n책은 카드의 roms/ebook 폴더에 넣으세요. 앱을 제거해도 책, 설정 및 읽던 위치는 유지됩니다. casualducko가 RG DS Plus용으로 제작했으며 앱 자체 업데이트와 스토어 업데이트를 지원합니다."},
        {"gbads", "에뮬레이터", "두 화면에서 즐기는 GBA: 한 화면은 게임, 다른 화면은 게임의 지도.", "mGBA 기반의 듀얼 화면용 GBA 에뮬레이터입니다. 위 화면에 게임, 아래 화면에 지원 게임 37종(캐슬바니아, 메트로이드, 젤다, Golden Sun, Advance Wars, Mario Kart 등)의 지도, 레이스 정보 또는 유닛 정보를 실시간 표시합니다.\n카드의 roms/gba를 자동 검색합니다. store/apps/gbads/gba-ds.cfg에서 show_all = 1로 설정하면 모든 게임을 표시합니다(미지원 게임은 한 화면으로 실행). HOME 또는 아래 화면 터치로 상태 저장, 되감기, 치트, 화면 설정, 종료 메뉴를 엽니다.\nv1.4.10부터 saves/gba의 .srm 저장 데이터를 BananaOS 에뮬레이터와 공유합니다. 상태 저장 및 설정은 store/apps/gbads에 남으며 앱을 삭제해도 유지됩니다. 앱의 설정에서 BananaOS GBA 목록 연동을 켜면 지원 게임을 GBA DS로 실행합니다. 미지원 게임은 BananaOS의 보조 화면 없이 RetroArch로 실행하므로 보조 화면을 사용한다면 끄세요. v1.4.10부터 앱을 제거하면 기존 목록이 기본 에뮬레이터로 돌아갑니다. kyannon 제작(GPL-3.0), 앱 자체 및 스토어 업데이트 지원."},
        {"bananaplayer", "미디어", "두 화면으로 영화, 음악, 사진, 만화 감상: 위 화면에 영상, 아래 화면에 조작 버튼.", "두 화면 전용 미디어 플레이어입니다. 위 화면에서 영상을 재생하고 아래 화면에서 버튼이나 터치로 조작합니다. MP4, MKV 등의 영상과 자막, 오디오 트랙, 챕터, 이어보기를 지원합니다. 음악 폴더를 앨범으로 재생하고 표지, 20종 시각화 효과, 10밴드 이퀄라이저를 제공합니다. 사진 확대 및 이동, 양쪽 화면 만화 읽기(선택 확장)를 지원합니다.\nWi-Fi로 PC 또는 NAS의 파일을 재생할 수 있고 웹 대시보드에서 업로드, 재생 목록 작성, 원격 재생을 지원합니다. 영상, 음악, 사진은 카드 어느 폴더에나 넣을 수 있습니다. 설정과 재생 위치는 home/.config/banana-player에 저장되어 제거 후에도 유지됩니다. 대부분의 1080p 영상은 원활하지만 높은 비트레이트와 HEVC(x265)는 끊길 수 있습니다. tonywei92 제작(MIT), 스토어 업데이트 지원."},
        {"dodakvarter", "슈팅 / 로그라이크", "밤의 스웨덴 교외를 배경으로 하는 두 화면용 좀비 로그라이크.", "Call of Duty Zombies처럼 여러 라운드를 생존하세요. 크로나를 모아 바리케이드를 열고 새 지역으로 이동하며 전력을 찾습니다. Julmust와 Snabbkaffe를 마시고 Lådan을 사용하고(Dalahäst 주의), Smedjan에서 강화할 수 있습니다. 매번 새로운 마을과 더 좋은 전리품을 만나며 스웨덴 민담의 보스 8종이 등장합니다.\n위 화면은 게임, 아래 화면은 인벤토리, 체력, 탄약, 지도입니다. BananaOS 기본 제공 앱입니다. 제거하면 메뉴 타일만 사라지며 apps/dodakvarter의 저장 데이터는 유지됩니다. 다시 설치하면 타일이 복원됩니다."},
        {"bank", "도구", "PKHeX.Core 기반의 포켓몬 보관함, 저장 편집, 적법성 검사 및 교환 앱.", "이전 이름은 Bank & Trade입니다. 1~5세대 게임의 저장 데이터를 읽어 자체 보관함에 포켓몬을 보관하고, 게임·박스·파티 사이에서 이동할 수 있습니다. 세대를 올려 이동할 때만 Pal Park 및 Poké Transfer 방식으로 형식을 변환합니다. PKHeX처럼 포켓몬 생성·편집·복제, 트레이너·가방·도감 편집, 적법성 검사를 지원하며 Wi-Fi로 다른 기기와 로비 또는 비공개 방에서 교환합니다.\n사용하기 전에 게임을 종료하세요. 보관함, 설정, 저장 백업은 apps/bank에 남으며 앱을 삭제해도 유지됩니다. 0.5.3 이전에는 기본 제공되었으며 0.5.3부터 스토어에서 앱 목록으로 설치합니다."},
        {"bshare", "도구", "LocalSend를 이용해 Wi-Fi로 휴대전화나 컴퓨터와 파일을 주고받습니다.", "같은 Wi-Fi의 LocalSend 앱(Tien Do Nam과 기여자 제작, localsend.org)과 파일을 주고받습니다. 수신을 직접 켠 후 각 전송을 승인합니다. 게임은 해당 시스템 폴더에, 나머지는 banana/received 또는 지정한 위치에 저장합니다. 보내려면 카드의 파일 또는 폴더를 선택하고 상대 기기를 선택하세요.\nBshare는 LocalSend의 공개 프로토콜을 기반으로 만든 BananaOS의 파일 전송 기능입니다. 기본 제공되며 제거하면 메뉴 타일만 사라지고 다시 설치하면 복원됩니다."},
        {"portmaster", "도구", "PC 및 홈브류 게임 포트를 다운로드하고 포트 게임 목록에서 실행합니다.", "휴대용 게임기에서 실행할 수 있도록 이식된 PC 및 홈브류 게임을 portmaster.games에서 내려받습니다. 많은 게임이 무료이며 일부는 정품 게임 파일이 필요합니다. 포트 게임 목록에서 실행하세요.\nPortMaster와 설치한 게임은 카드의 roms/ports 폴더에 저장됩니다. 자체 업데이트를 지원합니다. 앱을 제거해도 설치한 포트와 실행 환경(PortMaster/libs)은 남지만 게임 실행에는 PortMaster 폴더가 필요하므로 다시 설치해야 합니다. PortMaster 팀 제작(MIT). BananaOS 0.5.3 이전에는 기본 제공되었습니다."},
    };
    for (size_t i=0;i<sizeof rows/sizeof rows[0];i++) if (!strcmp(a->id,rows[i].id)) {
        snprintf(a->genre,sizeof a->genre,"%s",rows[i].genre);
        snprintf(a->summary,sizeof a->summary,"%s",rows[i].summary);
        snprintf(a->desc,sizeof a->desc,"%s",rows[i].desc);
        return;
    }
}
