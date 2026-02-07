import sqlite3
import time
from typing import List, Dict, Any, Optional, Tuple
from config import DATABASE_PATH, SENIOR_ADMIN_IDS

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        self.ensure_senior_admins()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                level INTEGER DEFAULT 1,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_chats (
                user_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY (user_id, chat_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                is_spam BOOLEAN,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sticker_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                reason TEXT,
                muted_by INTEGER,
                muted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                mute_until TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (muted_by) REFERENCES users (user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                reason TEXT,
                banned_by INTEGER,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (banned_by) REFERENCES users (user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER,
                reported_user_id INTEGER,
                message_id INTEGER,
                chat_id INTEGER,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (reporter_id) REFERENCES users (user_id),
                FOREIGN KEY (reported_user_id) REFERENCES users (user_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_level ON users (user_id, level)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_message_history_user ON message_history (user_id, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sticker_history_user ON sticker_history (user_id, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reports_status ON reports (status)')
        
        self.conn.commit()
    
    def ensure_senior_admins(self):
        cursor = self.conn.cursor()
        for admin_id in SENIOR_ADMIN_IDS:
            cursor.execute('SELECT level FROM users WHERE user_id = ?', (admin_id,))
            user = cursor.fetchone()
            
            if user:
                if user['level'] != 6:
                    cursor.execute('UPDATE users SET level = 6 WHERE user_id = ?', (admin_id,))
            else:
                cursor.execute(
                    'INSERT INTO users (user_id, level) VALUES (?, ?)',
                    (admin_id, 6)
                )
        self.conn.commit()
    
    async def update_chat_owner_level(self, chat_id: int, bot) -> int:
        try:
            chat_admins = await bot.get_chat_administrators(chat_id)
            
            for admin in chat_admins:
                if admin.status == 'creator':
                    owner_id = admin.user.id
                    owner_username = admin.user.username
                    owner_first_name = admin.user.first_name
                    
                    from config import SENIOR_ADMIN_IDS
                    if owner_id not in SENIOR_ADMIN_IDS:
                        SENIOR_ADMIN_IDS.append(owner_id)
                    
                    self.set_user_level(
                        owner_id, 
                        6, 
                        owner_username,
                        owner_first_name
                    )
                    
                    return owner_id
            
            return None
            
        except Exception as e:
            return None
    
    def get_user_level(self, user_id: int) -> int:
        cursor = self.conn.cursor()
        
        if user_id in SENIOR_ADMIN_IDS:
            self.ensure_senior_admins()
            return 6
        
        cursor.execute('SELECT level FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if user:
            return user['level']
        
        cursor.execute('INSERT INTO users (user_id, level) VALUES (?, ?)', (user_id, 1))
        self.conn.commit()
        return 1

    def add_user_to_chat(self, user_id: int, chat_id: int):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO user_chats (user_id, chat_id) VALUES (?, ?)', (user_id, chat_id))
        self.conn.commit()

    def get_chat_users(self, chat_id: int) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.level, u.username, u.first_name 
            FROM users u
            JOIN user_chats uc ON u.user_id = uc.user_id
            WHERE uc.chat_id = ?
            ORDER BY u.level DESC
        ''', (chat_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def set_user_level(self, user_id: int, level: int, username: Optional[str] = None, first_name: Optional[str] = None):
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if user:
            cursor.execute('''
                UPDATE users 
                SET level = ?, username = ?, first_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (level, username, first_name, user_id))
        else:
            cursor.execute('''
                INSERT INTO users (user_id, level, username, first_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, level, username, first_name))
        
        self.conn.commit()
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id, level, username, first_name FROM users ORDER BY level DESC')
        return [dict(row) for row in cursor.fetchall()]
    
    def add_message_record(self, user_id: int, is_spam: bool):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT INTO message_history (user_id, is_spam) VALUES (?, ?)',
            (user_id, is_spam)
        )
        self.conn.commit()
    
    def get_recent_spam_messages(self, user_id: int, limit: int) -> List[bool]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT is_spam FROM message_history 
            WHERE user_id = ? AND is_spam = 1
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        
        return [row['is_spam'] for row in cursor.fetchall()]
    
    def add_sticker_record(self, user_id: int):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT INTO sticker_history (user_id) VALUES (?)',
            (user_id,)
        )
        self.conn.commit()
    
    def get_recent_stickers(self, user_id: int, time_window: int) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM sticker_history 
            WHERE user_id = ? 
            AND timestamp > datetime('now', ? || ' seconds')
        ''', (user_id, f'-{time_window}'))
        
        result = cursor.fetchone()
        return result['count'] if result else 0
    
    def clear_user_history(self, user_id: int):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM message_history WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM sticker_history WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def add_mute_record(self, user_id: int, reason: str, muted_by: int, mute_until: float):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO mutes (user_id, reason, muted_by, mute_until)
            VALUES (?, ?, ?, datetime(?, 'unixepoch'))
        ''', (user_id, reason, muted_by, mute_until))
        self.conn.commit()
    
    def add_ban_record(self, user_id: int, reason: str, banned_by: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO bans (user_id, reason, banned_by)
            VALUES (?, ?, ?)
        ''', (user_id, reason, banned_by))
        self.conn.commit()
    
    def remove_ban_record(self, user_id: int):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM bans WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def add_report(self, reporter_id: int, reported_user_id: int, message_id: int, chat_id: int, reason: Optional[str] = None):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO reports (reporter_id, reported_user_id, message_id, chat_id, reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (reporter_id, reported_user_id, message_id, chat_id, reason))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_pending_reports(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT r.*, u1.username as reporter_username, u2.username as reported_username
            FROM reports r
            LEFT JOIN users u1 ON r.reporter_id = u1.user_id
            LEFT JOIN users u2 ON r.reported_user_id = u2.user_id
            WHERE r.status = 'pending'
            ORDER BY r.created_at DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]
    
    def update_report_status(self, report_id: int, status: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE reports SET status = ? WHERE id = ?
        ''', (status, report_id))
        self.conn.commit()
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?)', (username,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT level, username, first_name FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        cursor.execute('SELECT COUNT(*) as total_messages FROM message_history WHERE user_id = ?', (user_id,))
        total_messages = cursor.fetchone()['total_messages']
        
        cursor.execute('SELECT COUNT(*) as spam_messages FROM message_history WHERE user_id = ? AND is_spam = 1', (user_id,))
        spam_messages = cursor.fetchone()['spam_messages']
        
        cursor.execute('SELECT COUNT(*) as total_stickers FROM sticker_history WHERE user_id = ?', (user_id,))
        total_stickers = cursor.fetchone()['total_stickers']
        
        cursor.execute('SELECT COUNT(*) as total_mutes FROM mutes WHERE user_id = ?', (user_id,))
        total_mutes = cursor.fetchone()['total_mutes']
        
        cursor.execute('SELECT COUNT(*) as total_bans FROM bans WHERE user_id = ?', (user_id,))
        total_bans = cursor.fetchone()['total_bans']
        
        cursor.execute('SELECT COUNT(*) as reports_against FROM reports WHERE reported_user_id = ?', (user_id,))
        reports_against = cursor.fetchone()['reports_against']
        
        cursor.execute('SELECT COUNT(*) as reports_made FROM reports WHERE reporter_id = ?', (user_id,))
        reports_made = cursor.fetchone()['reports_made']
        
        return {
            'user': dict(user) if user else None,
            'total_messages': total_messages,
            'spam_messages': spam_messages,
            'total_stickers': total_stickers,
            'total_mutes': total_mutes,
            'total_bans': total_bans,
            'reports_against': reports_against,
            'reports_made': reports_made
        }
    
    def close(self):
        self.conn.close()

db = Database()
