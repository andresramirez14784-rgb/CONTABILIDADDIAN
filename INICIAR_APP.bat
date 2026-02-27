@echo off
title ContaDash - Auditoria Tributaria DIAN
color 1F
echo.
echo  =====================================================
echo   ContaDash - Plataforma de Auditoria Tributaria
echo   Compatible con: SIIGO, ContaSol, Helisa, DIAN
echo  =====================================================
echo.
echo  Iniciando servidor... Por favor espere.
echo  La app se abrira en su navegador automaticamente.
echo  URL: http://localhost:8501
echo.
echo  Para cerrar: presione Ctrl+C en esta ventana
echo.

cd /d "%~dp0"
python -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false --theme.base dark --theme.primaryColor "#2E75B6" --theme.backgroundColor "#0F1C33" --theme.secondaryBackgroundColor "#1A2B4A" --theme.textColor "#E8EFF8"

pause
