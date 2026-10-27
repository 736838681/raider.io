@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
 py -3 raiderio_armor_compare.py --out "结果"
) else (
 python raiderio_armor_compare.py --out "结果"
)
echo.
echo Finished. Check the result folder and error messages above.
pause
