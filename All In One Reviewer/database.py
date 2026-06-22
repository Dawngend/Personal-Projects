import sqlite3
import json
import os

# Save the db inside the Database subfolder you created
DB_PATH = os.path.join("Database", "reviewer.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            modules_included TEXT NOT NULL,
            subject TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id INTEGER,
            type TEXT NOT NULL,
            question TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            options TEXT,
            times_missed INTEGER DEFAULT 0,
            FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

def create_deck(name, modules_included, subject):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO decks (name, modules_included, subject) VALUES (?, ?, ?)", 
                   (name, modules_included, subject))
    deck_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return deck_id

def add_card(deck_id, card_type, question, correct_answer, options=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    options_json = json.dumps(options) if options else None
    cursor.execute("""
        INSERT INTO cards (deck_id, type, question, correct_answer, options)
        VALUES (?, ?, ?, ?, ?)
    """, (deck_id, card_type, question, correct_answer, options_json))
    conn.commit()
    conn.close()

def get_decks():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM decks")
    decks = cursor.fetchall()
    conn.close()
    return decks

def get_cards_for_deck(deck_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cards WHERE deck_id = ?", (deck_id,))
    cards = cursor.fetchall()
    conn.close()
    return cards

def update_card_miss_count(card_id, increment=1):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE cards SET times_missed = times_missed + ? WHERE id = ?", (increment, card_id))
    conn.commit()
    conn.close()

init_db()
