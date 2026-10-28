@echo off
setlocal
rem Run Vivado without vivado.bat's pushd/cd outside the Codex workspace.
if not defined XILINX_VIVADO set "XILINX_VIVADO=D:\Xilinx\Vivado\2023.1"
set "_RDI_NEEDS_PYTHON=True"
set "_RDI_CWD=%cd%"
set "_RDI_BINROOT=%XILINX_VIVADO%\bin"
set "RDI_BINROOT=%_RDI_BINROOT%"
set "RDI_PROG=vivado"
call "%_RDI_BINROOT%\setupEnv.bat"
set "RDI_SETUP_ENV_FUNCTION=DIRNAME"
call "%RDI_BINROOT%\setupEnv.bat" "%RDI_BINROOT%" XILINX_VIVADO
set "RDI_DEPENDENCY=XILINX_VIVADO_HLS;XILINX_HLS"
set "RDI_USE_JDK17=True"
call "%RDI_BINROOT%\loader.bat" -exec %RDI_PROG% %*
exit /b %errorlevel%
