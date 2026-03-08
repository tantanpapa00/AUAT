@echo off
chcp 65001 > nul
set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
set "ANDROID_HOME=C:\Users\pc\AppData\Local\Android\Sdk"
set "PATH=%JAVA_HOME%\bin;%ANDROID_HOME%\platform-tools;%PATH%"

cd /d "%~dp0android"
echo Building APK...
echo JAVA_HOME=%JAVA_HOME%
echo ANDROID_HOME=%ANDROID_HOME%

call gradlew.bat assembleDebug

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo APK Build Successful!
    echo APK Location: %~dp0android\app\build\outputs\apk\debug\app-debug.apk
    echo ========================================
) else (
    echo.
    echo Build Failed with error code %ERRORLEVEL%
)
