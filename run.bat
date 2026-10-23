@echo off
cd /d "%~dp0"
py buddy.py
if errorlevel 1 pause