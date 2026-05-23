@echo off
chcp 65001 > nul
title 지침서 RAG 자동 동기화 도구

echo ======================================================
echo          지침서 RAG 자동 동기화 도구 (Zero-Touch)
echo ======================================================
echo.

echo 🔍 [1/2] 모든 지침서 폴더의 변경 사항을 스캔합니다...
python build_cache.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ [에러] 벡터 DB 빌드 중 오류가 발생했습니다.
    goto end
)

:: 깃허브에 반영할 변경사항이 있는지 확인
set changes=no
for /f "tokens=*" %%i in ('git status --porcelain') do set changes=yes

echo.
echo ------------------------------------------------------
if "%changes%"=="yes" (
    echo 🚀 [2/2] 변경 파일이 감지되어 깃허브 업로드를 진행합니다...
    echo ------------------------------------------------------
    git add .
    git commit -m "docs: 변경된 지침서 문서 및 벡터 데이터베이스 캐시 자동 업데이트"
    git push origin main
    
    if %errorlevel% neq 0 (
        echo.
        echo ❌ [에러] 깃허브 업로드(Push) 중 오류가 발생했습니다.
    ) else (
        echo.
        echo ======================================================
        echo 🎉 모든 변경 사항이 성공적으로 클라우드에 업로드되었습니다!
        echo 약 1분 후 웹 클라우드 서버에 자동 적용됩니다.
        echo ======================================================
    )
) else (
    echo 🏠 [2/2] 변경된 파일이 없습니다. 깃허브 업로드를 건너뜁니다.
    echo ------------------------------------------------------
    echo ✅ 모든 문서와 데이터베이스가 이미 최신 상태입니다.
)

:end
echo.
echo 아무 키나 누르면 창이 닫힙니다.
pause > nul
