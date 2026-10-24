/* Single native allocator/detector owner. The existing Python VDMA driver
 * programs the capture channel; this process reads only HALTED full stores.
 * Static Linux linking follows the qualified board display executable. */
#define _POSIX_C_SOURCE 200809L
#include "game_linux_capture.h"
#include "scene_protocol.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#if defined(__linux__)
#include <signal.h>
#include <time.h>
static volatile sig_atomic_t stopping;
static void on_signal(int signal_number) { (void)signal_number;stopping=1; }
#endif

static int offline(const char *path)
{
    uint8_t *pixels=malloc(3840U*720U);
    FILE *file=fopen(path,"rb");
    char line[SCENE_PROTOCOL_MAX_LINE+1U];
    int n;
    if (!pixels || !file) { free(pixels);if(file)fclose(file);return 2; }
    n=fread(pixels,1,3840U*720U,file)==3840U*720U && fgetc(file)==EOF && !ferror(file);
    if (fclose(file)) n=0;
    if (!n) {free(pixels);return 2;}
    n=game_capture_detect_bgr(pixels,1,0,line,sizeof line);free(pixels);
    if (n<=0) return 3;
    return fwrite(line,1,(size_t)n,stdout)==(size_t)n?0:3;
}
int main(int argc,char **argv)
{
#ifdef _WIN32
    _setmode(1,_O_BINARY);
#endif
    if (argc==3 && strcmp(argv[1],"--offline-bgr")==0) return offline(argv[2]);
    if (argc!=2 || strcmp(argv[1],"--owner")!=0) return 2;
#if defined(__linux__)
    {
        uint64_t virtual_address,physical_address;
        uint32_t previous=0;
        char command[128],line[SCENE_PROTOCOL_MAX_LINE+1U];
        int status;
        signal(SIGINT,on_signal);signal(SIGTERM,on_signal);
        status=game_capture_owner_prepare(&virtual_address,&physical_address);
        if (status) {
            printf("CAPTURE_OWNER_PREPARE_FAILED status=%d retained=%d\n",status,!game_capture_owner_can_exit());
            fflush(stdout);
        } else {
            printf("CAPTURE_OWNER_READY %llu %u\n",(unsigned long long)physical_address,5760U*720U);
            fflush(stdout);
            while (!stopping && fgets(command,sizeof command,stdin)) {
                unsigned sequence,captured,copy_ms,detect_ms;
                char extra;
                int n;
                if (!strcmp(command,"QUIT\n")) break;
                if (sscanf(command,"DETECT %u %u %c",&sequence,&captured,&extra)!=2 ||
                    !sequence || sequence!=previous+1U) {status=3;break;}
                n=game_capture_detect_owned(sequence,captured,line,sizeof line,&copy_ms,&detect_ms);
                if (n<=0) {status=3;printf("CAPTURE_DETECTION_REJECTED sequence=%u\n",sequence);fflush(stdout);break;}
                fwrite(line,1,(size_t)n,stdout);
                printf("CAPTURE_TIMING sequence=%u copy_ms=%u detect_ms=%u\n",sequence,copy_ms,detect_ms);
                fflush(stdout);previous=sequence;
            }
        }
        if (status==-2 || game_capture_owner_release()) {
            puts("CAPTURE_OWNER_RETAINED no_exit_or_global_reset");fflush(stdout);
            /* Unknown free/HALT outcomes are never retried automatically. */
            for (;;) {struct timespec t={1,0};nanosleep(&t,NULL);}
        }
        puts("CAPTURE_OWNER_RELEASED individually_no_global_reset");fflush(stdout);
        return status?3:0;
    }
#else
    return 3;
#endif
}
