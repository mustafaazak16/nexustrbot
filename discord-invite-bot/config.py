import os
from dotenv import load_dotenv

# Environment variables'ları yükle
load_dotenv()

class Config:
    """Bot konfigürasyon ayarları"""
    
    # Discord Bot Token
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    
    # Bot Prefix
    BOT_PREFIX = os.getenv('BOT_PREFIX', '!')
    
    # Bot Adı
    BOT_NAME = 'NexusTR'
    
    # Veritabanı ayarları
    DATABASE_NAME = 'invites.db'
    
    # Davet kodu uzunluğu
    INVITE_CODE_LENGTH = 8
    
    # Embed renkleri
    COLORS = {
        'SUCCESS': 0x00ff00,  # Yeşil
        'ERROR': 0xff0000,    # Kırmızı
        'INFO': 0x0099ff,     # Mavi
        'WARNING': 0xffaa00,  # Turuncu
        'NEUTRAL': 0x808080   # Gri
    }
    
    # Mesaj ayarları
    MAX_INVITES_DISPLAY = 10  # Davet listesinde gösterilecek maksimum kişi sayısı
    
    # Güvenlik ayarları - Fake davet koruması
    SECURITY = {
        'MAX_INVITES_PER_HOUR': 20,     # Saatte maksimum davet sayısı
        'MAX_INVITES_PER_DAY': 100,     # Günde maksimum davet sayısı
        'BOT_PROTECTION': True,          # Bot koruması aktif mi
        'DUPLICATE_INVITE_PROTECTION': True,  # Tekrar davet koruması aktif mi
        'SUSPICIOUS_ACTIVITY_LOGGING': True   # Şüpheli aktivite loglaması aktif mi
    }
    
    @classmethod
    def validate(cls):
        """Konfigürasyon doğrulaması"""
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN environment variable'ı bulunamadı!")
        return True
