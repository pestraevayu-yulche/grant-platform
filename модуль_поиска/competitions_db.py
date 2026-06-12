# competitions_db.py
import json
import os
from datetime import datetime

class CompetitionsDB:
    def __init__(self, filepath='data/competitions.json'):
        self.filepath = filepath
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        if not os.path.exists(self.filepath):
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
    
    def get_all(self):
        with open(self.filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save(self, competition):
        competitions = self.get_all()
        competition['id'] = datetime.now().strftime('%Y%m%d%H%M%S')
        competition['created_at'] = datetime.now().isoformat()
        competitions.append(competition)
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(competitions, f, ensure_ascii=False, indent=2)
        return competition['id']
    
    def get_by_id(self, competition_id):
        competitions = self.get_all()
        for c in competitions:
            if c.get('id') == competition_id:
                return c
        return None

competitions_db = CompetitionsDB()