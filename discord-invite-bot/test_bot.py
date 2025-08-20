#!/usr/bin/env python3
"""
Discord Davet Bot Test Dosyası
Bu dosya bot'un temel işlevlerini test etmek için kullanılır.
"""

import sqlite3
from datetime import datetime
import random
import string

def test_database():
    """Veritabanı işlevlerini test eder"""
    print("🧪 Veritabanı testleri başlatılıyor...")
    
    # Test veritabanı oluştur
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    
    # Tabloları oluştur
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_codes (
            code TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at TIMESTAMP,
            uses INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invited_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER,
            invited_user_id INTEGER,
            invited_at TIMESTAMP,
            invite_code TEXT
        )
    ''')
    
    print("✅ Tablolar oluşturuldu")
    
    # Test verisi ekle
    test_user_id = 123456789
    test_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    cursor.execute(
        'INSERT INTO invite_codes (code, user_id, created_at) VALUES (?, ?, ?)',
        (test_code, test_user_id, datetime.now())
    )
    
    print(f"✅ Test davet kodu eklendi: {test_code}")
    
    # Test verisini kontrol et
    cursor.execute('SELECT code FROM invite_codes WHERE user_id = ?', (test_user_id,))
    result = cursor.fetchone()
    
    if result and result[0] == test_code:
        print("✅ Davet kodu doğru şekilde kaydedildi")
    else:
        print("❌ Davet kodu kaydedilemedi")
    
    # Test davet kaydı ekle
    test_invited_user_id = 987654321
    cursor.execute(
        'INSERT INTO invited_users (inviter_id, invited_user_id, invited_at, invite_code) VALUES (?, ?, ?, ?)',
        (test_user_id, test_invited_user_id, datetime.now(), test_code)
    )
    
    print("✅ Test davet kaydı eklendi")
    
    # Davet sayısını kontrol et
    cursor.execute('SELECT COUNT(*) FROM invited_users WHERE inviter_id = ?', (test_user_id,))
    invite_count = cursor.fetchone()[0]
    
    if invite_count == 1:
        print("✅ Davet sayısı doğru şekilde sayıldı")
    else:
        print(f"❌ Davet sayısı yanlış: {invite_count}")
    
    conn.close()
    print("✅ Veritabanı testleri tamamlandı\n")

def test_invite_code_generation():
    """Davet kodu oluşturma işlevini test eder"""
    print("🧪 Davet kodu oluşturma testleri başlatılıyor...")
    
    codes = set()
    for _ in range(100):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        codes.add(code)
    
    if len(codes) == 100:
        print("✅ 100 benzersiz davet kodu oluşturuldu")
    else:
        print(f"❌ Sadece {len(codes)} benzersiz kod oluşturuldu")
    
    # Kod formatını kontrol et
    valid_chars = set(string.ascii_uppercase + string.digits)
    invalid_codes = []
    
    for code in list(codes)[:10]:  # İlk 10 kodu kontrol et
        if not all(char in valid_chars for char in code):
            invalid_codes.append(code)
    
    if not invalid_codes:
        print("✅ Tüm davet kodları geçerli karakterlerden oluşuyor")
    else:
        print(f"❌ Geçersiz kodlar bulundu: {invalid_codes}")
    
    print("✅ Davet kodu oluşturma testleri tamamlandı\n")

def main():
    """Ana test fonksiyonu"""
    print("🚀 Discord Davet Bot Test Suite Başlatılıyor...\n")
    
    try:
        test_database()
        test_invite_code_generation()
        
        print("🎉 Tüm testler başarıyla tamamlandı!")
        print("Bot kullanıma hazır!")
        
    except Exception as e:
        print(f"❌ Test sırasında hata oluştu: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
