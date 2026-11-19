@echo off
TITLE Centro Meteorologico OpenWeatherMap Pro - JPV
COLOR 0B
echo ============================================================
echo   CENTRO METEOROLOGICO OPENWEATHERMAP PRO (EDICION ENTERPRISE)
echo   Arquitectura: Ing. Juancito Pena Vizcaino
echo ============================================================
echo.
cd /d "%~dp0"

IF NOT EXIST ".venv\Scripts\activate.bat" (
    echo [ERROR] No se encontro el entorno virtual en .venv\Scripts\activate.bat
    echo Ejecuta: python -m venv .venv e instala las dependencias.
    pause
    exit /b 1
)

echo [1/2] Activando entorno virtual seguro de Python...
call .venv\Scripts\activate.bat

echo [2/2] Iniciando aplicacion Streamlit...
echo La aplicacion abrira en tu navegador (http://localhost:8501)
echo Presiona Ctrl+C en esta consola para detener el servidor.
echo.
streamlit run app.py

pause
