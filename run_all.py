import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def start(name, folder, port):
    path = ROOT / folder
    print(f"Запуск: {name} — {path} на порту {port}")
    env = os.environ.copy()
    env['PORT'] = str(port)
    return subprocess.Popen([sys.executable, "app.py"], cwd=str(path), env=env)
# Запускаем оба модуля на разных портах
processes = [
    start("модуль автоматизации", "модуль_автоматизации", 8000),
    start("модуль поиска", "модуль_поиска", 5000),
]

print("Оба модуля запущены. Для остановки нажмите Ctrl+C.")
try:
    for p in processes:
        p.wait()
except KeyboardInterrupt:
    print("Остановка модулей...")
    for p in processes:
        p.terminate()
