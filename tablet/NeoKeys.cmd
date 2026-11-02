@echo off
rem Double-click to start NeoKeys with the FP10 Lights bridge; close this window to stop it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve.ps1" %*
