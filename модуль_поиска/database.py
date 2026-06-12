# database.py

import sqlite3
import json


class ProjectsDB:

    def __init__(
        self,
        db_path="data/projects.db"
    ):

        self.conn = sqlite3.connect(db_path)

        self.create_tables()

    def create_tables(self):

        cursor = self.conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            title TEXT,
            abstract TEXT,
            source TEXT,
            url TEXT,
            authors TEXT,
            contacts TEXT,
            relevance_score REAL
        )
        """)

        self.conn.commit()

    def insert_project(
        self,
        project
    ):

        cursor = self.conn.cursor()

        cursor.execute("""
        INSERT OR REPLACE INTO projects (
            id,
            title,
            abstract,
            source,
            url,
            authors,
            contacts,
            relevance_score
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project.get("id"),
            project.get("title"),
            project.get("abstract"),
            project.get("source"),
            project.get("url"),
            json.dumps(project.get("authors", [])),
            json.dumps(project.get("contacts", [])),
            project.get("relevance_score", 0)
        ))

        self.conn.commit()

    def insert_many(
        self,
        projects
    ):

        for project in projects:
            self.insert_project(project)

    def get_all_projects(self):

        cursor = self.conn.cursor()

        cursor.execute("SELECT * FROM projects")

        rows = cursor.fetchall()

        return rows