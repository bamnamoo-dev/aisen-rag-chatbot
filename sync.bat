@echo off
title RAG Auto Sync Tool

echo ======================================================
echo          RAG Auto Sync Tool (Zero-Touch)
echo ======================================================
echo.

echo [+] [1/2] Scanning PDF folder changes...
"C:\Users\PC\AppData\Local\Python\bin\python.exe" build_cache.py

if %errorlevel% neq 0 (
    echo.
    echo [-] [Error] Failed to build vector DB cache.
    goto end
)

:: Check if there are changes to push to GitHub
set changes=no
for /f "tokens=*" %%i in ('git status --porcelain') do set changes=yes

echo.
echo ------------------------------------------------------
if "%changes%"=="yes" (
    echo [+] [2/2] Changes detected. Uploading to GitHub...
    echo ------------------------------------------------------
    git add .
    git commit -m "docs: auto-update pdf documents and vector db cache"
    git push origin main
    
    if %errorlevel% neq 0 (
        echo.
        echo [-] [Error] GitHub push failed.
    ) else (
        echo.
        echo ======================================================
        echo [+] All changes successfully uploaded to GitHub main!
        echo It will be deployed to Streamlit Cloud in about 1 min.
        echo ======================================================
    )
) else (
    echo [+] [2/2] No changes detected. Skipping GitHub upload.
    echo ------------------------------------------------------
    echo [+] All documents and caches are already up-to-date.
)

:end
echo.
echo Press any key to exit.
pause > nul

