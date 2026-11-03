#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#include "beam_pynq.h"
#if defined(__linux__)
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

/* One UART owner. Constructor/import does not open any device. */
static int owned_fd=-1;
static struct termios original;
int beam_pynq_clock_ms(void *unused, uint64_t *ms)
{
    struct timespec t;
    (void)unused;
    if (!ms || clock_gettime(CLOCK_MONOTONIC,&t) || t.tv_sec<0) return -1;
    *ms=(uint64_t)t.tv_sec*1000U+(uint64_t)t.tv_nsec/1000000U;
    return 0;
}

int beam_pynq_uart_open(const char *path)
{
    FILE *consoles;
    char line[256], name[128], actual[256];
    struct termios raw;
    int fd;
    if (owned_fd>=0 || !path || strncmp(path,"/dev/",5)) return -1;
    fd=open(path,O_RDWR|O_NOCTTY|O_NONBLOCK|O_CLOEXEC);
    if (fd<0) return -1;
    if (ttyname_r(fd,actual,sizeof actual)) { close(fd); return -1; }
    if (!strcmp(actual,"/dev/console") || !strcmp(actual,"/dev/tty") ||
        !strcmp(actual,"/dev/tty0")) { close(fd); return -1; }
    consoles=fopen("/proc/consoles","r");
    if (!consoles) { close(fd); return -1; }
    while (fgets(line,sizeof line,consoles)) {
        if (sscanf(line,"%127s",name)==1 && !strcmp(actual+5,name)) {
            fclose(consoles); close(fd); return -1;
        }
    }
    if (ferror(consoles)) { fclose(consoles); close(fd); return -1; }
    fclose(consoles);
    if (flock(fd,LOCK_EX|LOCK_NB) || tcgetattr(fd,&original)) { close(fd); return -1; }
    if (ioctl(fd,TIOCEXCL)) { close(fd); return -1; }
    raw=original;
    raw.c_iflag=0; raw.c_oflag=0; raw.c_lflag=0;
    raw.c_cflag=CS8|CLOCAL|CREAD;
    raw.c_cc[VMIN]=0; raw.c_cc[VTIME]=0;
    if (cfsetispeed(&raw,B115200) || cfsetospeed(&raw,B115200) || tcsetattr(fd,TCSANOW,&raw)) {
        (void)tcsetattr(fd,TCSANOW,&original); (void)ioctl(fd,TIOCNXCL); close(fd); return -1;
    }
    owned_fd=fd;
    return fd;
}

int beam_pynq_uart_read(int fd, uint8_t *bytes, size_t capacity)
{
    ssize_t n;
    if (fd<0 || fd!=owned_fd || !bytes || !capacity || capacity>4096U) return -1;
    n=read(fd,bytes,capacity);
    if (n<0 && (errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR)) return 0;
    return n<0 ? -1 : (int)n;
}

int beam_pynq_uart_write(int fd, const uint8_t *packet, size_t length)
{
    size_t offset=0;
    uint64_t begin, now;
    if (fd<0 || fd!=owned_fd || !packet || !length || length>174U ||
        beam_pynq_clock_ms(NULL,&begin)) return -1;
    while (offset<length) {
        ssize_t n;
        if (beam_pynq_clock_ms(NULL,&now) || now<begin || now-begin>=100U) return -1;
        n=write(fd,packet+offset,length-offset);
        if (n>0) offset+=(size_t)n;
        else if (n<0 && errno!=EINTR && errno!=EAGAIN && errno!=EWOULDBLOCK) return -1;
        else {
            struct pollfd p={fd,POLLOUT,0};
            if (poll(&p,1,1)<0 && errno!=EINTR) return -1;
            if (p.revents&(POLLERR|POLLHUP|POLLNVAL)) return -1;
        }
    }
    return 0;
}

int beam_pynq_uart_close(int fd)
{
    int result=0;
    if (fd<0 || fd!=owned_fd) return -1;
    if (tcsetattr(fd,TCSANOW,&original)) result=-1;
    if (ioctl(fd,TIOCNXCL)) result=-1;
    if (close(fd)) result=-1;
    owned_fd=-1;
    return result;
}
#else
int beam_pynq_clock_ms(void *unused, uint64_t *ms)
{ (void)unused; (void)ms; return -1; }
int beam_pynq_uart_open(const char *path) { (void)path; return -1; }
int beam_pynq_uart_read(int fd, uint8_t *b, size_t n) { (void)fd; (void)b; (void)n; return -1; }
int beam_pynq_uart_write(int fd, const uint8_t *b, size_t n) { (void)fd; (void)b; (void)n; return -1; }
int beam_pynq_uart_close(int fd) { (void)fd; return -1; }
#endif
