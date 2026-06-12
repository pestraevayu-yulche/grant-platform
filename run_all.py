import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def start(name, folder):
    path = ROOT / folder
    print(f"Запуск: {name} — {path}")
    return subprocess.Popen([sys.executable, "app.py"], cwd=str(path))

processes = [
    start("модуль автоматизации", "модуль_автоматизации"),
    start("модуль поиска", "модуль_поиска"),
]

print("Оба модуля запущены. Для остановки нажмите Ctrl+C.")
try:
    for p in processes:
        p.wait()
except KeyboardInterrupt:
    print("Остановка модулей...")
    for p in processes:
        p.terminate()
