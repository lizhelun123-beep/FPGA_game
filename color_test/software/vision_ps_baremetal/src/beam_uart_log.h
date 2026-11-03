#ifndef BEAM_UART_LOG_H
#define BEAM_UART_LOG_H
#include <stddef.h>
#include <stdarg.h>
typedef struct { char data[2048]; size_t used,offset; } BeamUartLog;
int beam_uart_log_vprintf(BeamUartLog *log,const char *format,va_list args);
/* One UART owner, nonblocking sink.0=drained,1=pending,-1=error. */
int beam_uart_log_poll(BeamUartLog *log,int (*put)(unsigned char),unsigned budget);
#endif
