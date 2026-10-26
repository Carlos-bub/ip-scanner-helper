@echo off
setlocal
set "SCANNER_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%SCANNER_PYTHON%" (
    echo Ambiente virtual nao encontrado. Siga a instalacao descrita no README.
    pause
    exit /b 1
)
"%SCANNER_PYTHON%" -m ip_scanner_helper %*
exit /b %ERRORLEVEL%
