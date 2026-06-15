@echo off
title RAG Git Push Tool
echo ======================================================
echo          RAG Quick Git Push Tool
echo ======================================================
echo.

:: Check for git changes
git status --short
echo.

set changes=no
for /f "tokens=*" %%i in ('git status --porcelain') do set changes=yes

if "%changes%"=="yes" (
    echo [+] Changes detected. Committing and pushing...
    git add .
    git commit -m "fix: remove append_usage_log calls and sync workspace"
    git push origin main
    if %errorlevel% neq 0 (
        echo.
        echo [-] [Error] Push failed.
    ) else (
        echo.
        echo ======================================================
        echo [+] Successfully pushed to GitHub main branch!
        echo Streamlit Cloud will deploy changes shortly.
        echo ======================================================
    )
) else (
    echo [i] No changes detected.
)

echo.
pause
