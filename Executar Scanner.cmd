@echo off
setlocal
set "SCANNER_EXE=%~dp0dist\portfolio\2.0.1\IP_Scanner_Helper\IP_Scanner_Helper.exe"
if not exist "%SCANNER_EXE%" (
    echo Build nao encontrado. Extraia o pacote Windows completo ou gere o executavel conforme o README.
    pause
    exit /b 1
)
start "" "%SCANNER_EXE%"
