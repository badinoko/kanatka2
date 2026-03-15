@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ========================================
echo   Симулятор камеры
echo ========================================
echo.
echo Этот скрипт копирует фото из указанной
echo папки в workdir\incoming порциями,
echo имитируя работу камеры.
echo.

:: --- Параметры ---
:: Папка с тестовыми фото (первый аргумент или спросим)
set "SOURCE=%~1"
if "%SOURCE%"=="" (
    echo Перетащите папку с фото на этот файл,
    echo или укажите путь:
    echo.
    set /p "SOURCE=Путь к папке с фото: "
)

if not exist "%SOURCE%" (
    echo.
    echo ОШИБКА: папка не найдена: %SOURCE%
    pause
    exit /b 1
)

set "DEST=%~dp0workdir\incoming"
if not exist "%DEST%" mkdir "%DEST%"

:: Считаем файлы
set COUNT=0
for %%f in ("%SOURCE%\*.jpg" "%SOURCE%\*.jpeg" "%SOURCE%\*.png") do set /a COUNT+=1

if %COUNT%==0 (
    echo.
    echo ОШИБКА: в папке нет фото ^(jpg/jpeg/png^)
    pause
    exit /b 1
)

echo Найдено фото: %COUNT%
echo Источник:     %SOURCE%
echo Назначение:   %DEST%
echo.
echo Фото будут копироваться порциями по 5-8 штук
echo с паузой 10 секунд между порциями.
echo Это имитирует проезд кресел канатки.
echo.
echo Нажмите любую клавишу для старта...
pause >nul

set BATCH=0
set INBATCH=0
set BATCHSIZE=6
set TOTAL=0

for %%f in ("%SOURCE%\*.jpg" "%SOURCE%\*.jpeg" "%SOURCE%\*.png") do (
    copy "%%f" "%DEST%\" >nul
    set /a TOTAL+=1
    set /a INBATCH+=1

    echo   [!TOTAL!/%COUNT%] %%~nxf

    if !INBATCH! geq %BATCHSIZE% (
        set /a BATCH+=1
        echo.
        echo --- Серия !BATCH! отправлена ^(!INBATCH! фото^) ---
        echo     Пауза 10 сек...
        echo.
        set INBATCH=0

        :: Случайный размер следующей порции (5-8)
        set /a BATCHSIZE=5 + !RANDOM! %% 4

        timeout /t 10 /nobreak >nul
    )
)

if !INBATCH! gtr 0 (
    set /a BATCH+=1
    echo.
    echo --- Серия !BATCH! отправлена ^(!INBATCH! фото^) ---
)

echo.
echo ========================================
echo   Готово! Отправлено %COUNT% фото
echo   в %BATCH% сериях.
echo ========================================
echo.
echo Откройте PhotoSelector и посмотрите результат.
pause
