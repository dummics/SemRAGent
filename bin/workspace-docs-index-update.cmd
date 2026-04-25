@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0workspace-docs-index-update.ps1" %*
