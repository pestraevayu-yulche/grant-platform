$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\модуль_автоматизации'; python app.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\модуль_поиска'; python app.py"

Write-Host "Запущены два окна: модуль автоматизации (8000) и модуль поиска (5000)."
Write-Host "Сначала дождитесь строки Running on http://127.0.0.1:8000 и Running on http://127.0.0.1:5000."
