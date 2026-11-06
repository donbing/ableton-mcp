@echo off
rem Double-click to start Duel (call and response on the FP10 Lights strip); close this window to stop it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve.ps1" -Open duel/ %*
