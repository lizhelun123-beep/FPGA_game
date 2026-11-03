#include "beam_uart_log.h"
#include <stdio.h>
int beam_uart_log_vprintf(BeamUartLog *log,const char *format,va_list args)
{
    int n;
    if (!log || !format || log->offset || log->used>=sizeof log->data) return -1;
    n=vsnprintf(log->data+log->used,sizeof log->data-log->used,format,args);
    if (n<0 || (size_t)n>=sizeof log->data-log->used) return -1;
    log->used+=(size_t)n;
    return n;
}
int beam_uart_log_poll(BeamUartLog *log,int (*put)(unsigned char),unsigned budget)
{
    if (!log || !put || log->offset>log->used || log->used>=sizeof log->data) return -1;
    while (budget-- && log->offset<log->used) {
        int result=put((unsigned char)log->data[log->offset]);
        if (result<0) return -1;
        if (!result) return 1;
        ++log->offset;
    }
    if (log->offset<log->used) return 1;
    log->offset=log->used=0;
    return 0;
}
