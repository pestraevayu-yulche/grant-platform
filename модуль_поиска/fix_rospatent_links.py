# fix_rospatent_links.py
import json
import re

def fix_urls():
    input_file = "data/rospatent_projects.json"
    
    with open(input_file, 'r', encoding='utf-8') as f:
        patents = json.load(f)
    
    for patent in patents:
        # Удаляем ссылку для патентов Роспатента
        patent['url'] = None
    
    with open(input_file, 'w', encoding='utf-8') as f:
        json.dump(patents, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Удалены ссылки для {len(patents)} патентов Роспатента.")

if __name__ == "__main__":
    fix_urls()