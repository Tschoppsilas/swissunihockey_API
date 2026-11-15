@echo off
cd /d "%~dp0"
set "LABEL="
set /p LABEL=Titel-Zusatz (z.B. Winterpause oder Schlusstabelle, leer = keiner):
if defined LABEL (
    "C:\Program Files\Git\bin\bash.exe" generate_tables.sh --label "%LABEL%"
) else (
    "C:\Program Files\Git\bin\bash.exe" generate_tables.sh
)
pause
