import discord
from discord.ext import commands
import sqlite3
from datetime import datetime
from config import Config
import logging
import os
import json
import asyncio

# Ticket System Classes
class TicketCategorySelect(discord.ui.Select):
    def __init__(self, categories):
        self.categories = categories
        options = []
        
        for category in categories:
            options.append(discord.SelectOption(
                label=category["name"],
                description=category["description"],
                emoji=category["emoji"],
                value=category["id"]
            ))
        
        super().__init__(
            placeholder="Bir kategori seçin...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select"
        )
        
        logger.info(f"TicketCategorySelect oluşturuldu: {len(categories)} kategori")
    
    async def callback(self, interaction: discord.Interaction):
        try:
            logger.info(f"TicketCategorySelect callback başlatıldı: user={interaction.user.display_name}")
            logger.info(f"Seçilen değer: {self.values[0]}")
            logger.info(f"Mevcut kategoriler: {[cat['id'] for cat in self.categories]}")
            
            selected_category = None
            for category in self.categories:
                if category["id"] == self.values[0]:
                    selected_category = category
                    logger.info(f"Kategori bulundu: {category['name']}")
                    break
            
            if selected_category:
                logger.info(f"Kategori seçildi: {selected_category['name']}, ticket oluşturuluyor...")
                await interaction.response.send_message(
                    f"✅ **{selected_category['emoji']} {selected_category['name']}** kategorisi seçildi!\n\nTicket oluşturuluyor...",
                    ephemeral=True
                )
                # Ticket oluştur (dropdown menüyü kaldırma)
                logger.info("create_ticket_with_category çağrılıyor...")
                await create_ticket_with_category(interaction, selected_category)
                logger.info("create_ticket_with_category tamamlandı")
            else:
                logger.warning(f"Kategori bulunamadı: {self.values[0]}")
                await interaction.response.send_message("❌ Kategori bulunamadı!", ephemeral=True)
        except Exception as e:
            # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
            if not any(error_type in str(e) for error_type in [
                'Interaction has already been acknowledged',
                'Unknown Channel',
                '404 Not Found',
                'error code: 40060',
                'error code: 10003',
                'error code: 10062',
                'Unknown interaction'
            ]):
                logger.error(f"Ticket category select callback hatası: {e}")
                logger.error(f"Exception type: {type(e)}")
                logger.error(f"Exception args: {e.args}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Bir hata oluştu. Lütfen tekrar deneyin.", ephemeral=True)
            except Exception as e2:
                # Sessizce geç, log spam yapma
                pass

class TicketCategoryView(discord.ui.View):
    def __init__(self, categories):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect(categories))
        logger.info(f"TicketCategoryView oluşturuldu: {len(categories)} kategori")
    
    async def on_timeout(self):
        # Timeout olursa view'ı yeniden oluştur
        logger.info("Ticket view timeout oldu")
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        # Hata durumunda view'ı yeniden oluştur
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(error) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f"Ticket view hatası: {error}")
            logger.error(f"Error item: {item}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Bir hata oluştu. Lütfen tekrar deneyin.", ephemeral=True)
        except Exception as e:
            # Sessizce geç, log spam yapma
            pass



# Log sistemi kurulumu
def setup_logging():
    """Log dosyası ve konsol log sistemini kurar"""
    # logs klasörü oluştur
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Log formatı
    log_format = '%(asctime)s | %(levelname)s | %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Root logger'ı yapılandır
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            # Dosyaya yazma
            logging.FileHandler(
                f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log',
                encoding='utf-8'
            ),
            # Konsola yazma
            logging.StreamHandler()
        ]
    )
    
    # Discord.py loglarını azalt
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)

# Log sistemini başlat
setup_logging()
logger = logging.getLogger(__name__)

# Bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Bot instance
bot = commands.Bot(command_prefix=Config.BOT_PREFIX, intents=intents)

# Veritabanı başlatma
def init_db():
    """Veritabanını ve tabloları oluşturur"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    # Davet kodları tablosu - UNIQUE(user_id) kısıtlaması kaldırıldı
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            uses INTEGER DEFAULT 0
        )
    ''')
    
    # Davet edilen kullanıcılar tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invited_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER NOT NULL,
            invited_user_id INTEGER NOT NULL,
            invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            invite_code TEXT,
            UNIQUE(invited_user_id)
        )
    ''')
    
    # Şüpheli davet tespiti için tablo
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suspicious_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER NOT NULL,
            invite_count INTEGER DEFAULT 1,
            first_invite_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_invite_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Bot koruması için tablo
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_protection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            is_bot BOOLEAN DEFAULT FALSE,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Ticket sistemi tabloları
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ticket_config (
            guild_id INTEGER PRIMARY KEY,
            category_id INTEGER,
            support_role_id INTEGER,
            ticket_counter INTEGER DEFAULT 1,
            daily_limit INTEGER DEFAULT 3,
            log_channel_id INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            ticket_number INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            category_id TEXT NOT NULL,
            category_name TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            closed_by INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_daily_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            UNIQUE(guild_id, user_id, date)
        )
    ''')
    
    conn.commit()
    conn.close()

# Veritabanını başlat
init_db()

# Fake davet koruması fonksiyonları
def is_user_already_invited(user_id):
    """Kullanıcının daha önce davet edilip edilmediğini kontrol eder"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM invited_users WHERE invited_user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    return result is not None

def is_suspicious_inviter(inviter_id):
    """Davet eden kullanıcının şüpheli olup olmadığını kontrol eder"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    # Son 1 saatteki davet sayısını kontrol et
    cursor.execute('''
        SELECT COUNT(*) FROM invited_users 
        WHERE inviter_id = ? AND invited_at >= datetime('now', '-1 hour')
    ''', (inviter_id,))
    
    recent_invites = cursor.fetchone()[0]
    
    # Son 24 saatteki toplam davet sayısını kontrol et
    cursor.execute('''
        SELECT COUNT(*) FROM invited_users 
        WHERE inviter_id = ? AND invited_at >= datetime('now', '-24 hours')
    ''', (inviter_id,))
    
    daily_invites = cursor.fetchone()[0]
    
    conn.close()
    
    # Şüpheli kriterler (config'den alınır):
    # - 1 saatte Config.SECURITY['MAX_INVITES_PER_HOUR']'dan fazla davet
    # - 24 saatte Config.SECURITY['MAX_INVITES_PER_DAY']'dan fazla davet
    return (recent_invites > Config.SECURITY['MAX_INVITES_PER_HOUR'] or 
            daily_invites > Config.SECURITY['MAX_INVITES_PER_DAY'])

def log_suspicious_activity(inviter_id):
    """Şüpheli davet aktivitesini loglar"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO suspicious_invites 
        (inviter_id, invite_count, first_invite_at, last_invite_at)
        VALUES (?, 
                COALESCE((SELECT invite_count + 1 FROM suspicious_invites WHERE inviter_id = ?), 1),
                COALESCE((SELECT first_invite_at FROM suspicious_invites WHERE inviter_id = ?), datetime('now')),
                datetime('now'))
    ''', (inviter_id, inviter_id, inviter_id))
    
    conn.commit()
    conn.close()

def is_bot_user(user_id):
    """Kullanıcının bot olup olmadığını kontrol eder"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT is_bot FROM bot_protection WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    return result[0] if result else False

def mark_user_as_bot(user_id):
    """Kullanıcıyı bot olarak işaretler"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO bot_protection (user_id, is_bot, detected_at)
        VALUES (?, TRUE, datetime('now'))
    ''', (user_id,))
    
    conn.commit()
    conn.close()

def can_user_invite(inviter_id, invited_user_id):
    """Kullanıcının davet yapıp yapamayacağını kontrol eder"""
    # Bot koruması (config'den kontrol et)
    if Config.SECURITY['BOT_PROTECTION'] and is_bot_user(invited_user_id):
        return False, "Bu kullanıcı bir bot ve davet edilemez!"
    
    # Zaten davet edilmiş mi kontrol et (config'den kontrol et)
    if Config.SECURITY['DUPLICATE_INVITE_PROTECTION'] and is_user_already_invited(invited_user_id):
        return False, "Bu kullanıcı zaten davet edilmiş!"
    
    # Şüpheli davet eden kontrol et (config'den kontrol et)
    if Config.SECURITY['SUSPICIOUS_ACTIVITY_LOGGING'] and is_suspicious_inviter(inviter_id):
        log_suspicious_activity(inviter_id)
        return False, f"Çok fazla davet yapıyorsun! Saatte maksimum {Config.SECURITY['MAX_INVITES_PER_HOUR']}, günde maksimum {Config.SECURITY['MAX_INVITES_PER_DAY']} davet yapabilirsin."
    
    return True, "Davet yapılabilir"

def user_has_invite_link(user_id):
    """Kullanıcının zaten davet linki olup olmadığını kontrol eder"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT code FROM invite_codes WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    return result is not None

def get_user_invite_link(user_id):
    """Kullanıcının mevcut davet linkini getirir"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT code, uses FROM invite_codes WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    return result

# Ticket Sistemi Fonksiyonları
def get_ticket_config(guild_id):
    """Sunucunun ticket konfigürasyonunu getirir"""
    try:
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM ticket_config WHERE guild_id = ?', (guild_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            logger.debug(f"Ticket config bulundu: guild_id={guild_id}")
            return {
                'guild_id': result[0],
                'category_id': result[1],
                'support_role_id': result[2],
                'ticket_counter': result[3],
                'daily_limit': result[4],
                'log_channel_id': result[5]
            }
        else:
            logger.debug(f"Ticket config bulunamadı: guild_id={guild_id}")
        return None
    except Exception as e:
        logger.error(f"get_ticket_config hatası: {e}")
        return None

def save_ticket_config(guild_id, category_id, support_role_id, daily_limit=3, log_channel_id=None):
    """Ticket konfigürasyonunu kaydeder"""
    try:
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO ticket_config 
            (guild_id, category_id, support_role_id, daily_limit, log_channel_id) 
            VALUES (?, ?, ?, ?, ?)
        ''', (guild_id, category_id, support_role_id, daily_limit, log_channel_id))
        
        conn.commit()
        conn.close()
        logger.info(f"Ticket config kaydedildi: guild_id={guild_id}, category_id={category_id}, support_role_id={support_role_id}")
    except Exception as e:
        logger.error(f"save_ticket_config hatası: {e}")
        logger.error(f"Config detayları: guild_id={guild_id}, category_id={category_id}, support_role_id={support_role_id}")

def get_user_daily_tickets(guild_id, user_id):
    """Kullanıcının günlük ticket sayısını getirir"""
    try:
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT count FROM user_daily_tickets 
            WHERE guild_id = ? AND user_id = ? AND date = ?
        ''', (guild_id, user_id, today))
        
        result = cursor.fetchone()
        conn.close()
        
        count = result[0] if result else 0
        logger.debug(f"Günlük ticket sayısı: guild_id={guild_id}, user_id={user_id}, count={count}")
        return count
    except Exception as e:
        logger.error(f"get_user_daily_tickets hatası: {e}")
        return 0

def increment_user_daily_tickets(guild_id, user_id):
    """Kullanıcının günlük ticket sayısını artırır"""
    try:
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            INSERT OR REPLACE INTO user_daily_tickets 
            (guild_id, user_id, date, count) 
            VALUES (?, ?, ?, COALESCE((SELECT count + 1 FROM user_daily_tickets WHERE guild_id = ? AND user_id = ? AND date = ?), 1))
        ''', (guild_id, user_id, today, guild_id, user_id, today))
        
        conn.commit()
        conn.close()
        logger.info(f"Günlük ticket sayısı artırıldı: guild_id={guild_id}, user_id={user_id}, date={today}")
    except Exception as e:
        logger.error(f"increment_user_daily_tickets hatası: {e}")
        logger.error(f"Detaylar: guild_id={guild_id}, user_id={user_id}, date={today}")

def create_ticket_record(guild_id, ticket_number, user_id, channel_id, category_id, category_name):
    """Yeni ticket kaydı oluşturur"""
    try:
        logger.info(f"create_ticket_record başlatıldı: ticket_number={ticket_number}, user_id={user_id}, channel_id={channel_id}")
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tickets 
            (guild_id, ticket_number, user_id, channel_id, category_id, category_name) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (guild_id, ticket_number, user_id, channel_id, category_id, category_name))
        
        conn.commit()
        conn.close()
        logger.info(f"Ticket kaydı veritabanına eklendi: ticket_number={ticket_number}")
    except Exception as e:
        logger.error(f"create_ticket_record hatası: {e}")
        logger.error(f"Detaylar: guild_id={guild_id}, ticket_number={ticket_number}, user_id={user_id}, channel_id={channel_id}")
        raise

def get_user_active_ticket(guild_id, user_id):
    """Kullanıcının aktif ticket'ını getirir"""
    try:
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM tickets 
            WHERE guild_id = ? AND user_id = ? AND status = 'open'
            ORDER BY created_at DESC LIMIT 1
        ''', (guild_id, user_id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            logger.debug(f"Aktif ticket bulundu: guild_id={guild_id}, user_id={user_id}, ticket_id={result[0]}")
            return {
                'id': result[0],
                'guild_id': result[1],
                'ticket_number': result[2],
                'user_id': result[3],
                'channel_id': result[4],
                'category_id': result[5],
                'category_name': result[6],
                'status': result[7],
                'created_at': result[8]
            }
        else:
            logger.debug(f"Aktif ticket bulunamadı: guild_id={guild_id}, user_id={user_id}")
        return None
    except Exception as e:
        logger.error(f"get_user_active_ticket hatası: {e}")
        return None

def close_ticket(ticket_id, closed_by):
    """Ticket'ı kapatır"""
    try:
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE tickets 
            SET status = 'closed', closed_at = ?, closed_by = ? 
            WHERE id = ?
        ''', (datetime.now(), closed_by, ticket_id))
        
        conn.commit()
        conn.close()
        logger.info(f"Ticket {ticket_id} veritabanında kapatıldı, kapatan: {closed_by}")
    except Exception as e:
        logger.error(f"close_ticket hatası: {e}")
        logger.error(f"Ticket ID: {ticket_id}, Kapatan: {closed_by}")

def get_next_ticket_number(guild_id):
    """Sonraki ticket numarasını getirir"""
    try:
        logger.info(f"get_next_ticket_number başlatıldı: guild_id={guild_id}")
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('SELECT ticket_counter FROM ticket_config WHERE guild_id = ?', (guild_id,))
        result = cursor.fetchone()
        
        if result:
            ticket_number = result[0]
            logger.info(f"Mevcut ticket sayacı: {ticket_number}")
            # Sayaçı artır
            cursor.execute('UPDATE ticket_config SET ticket_counter = ? WHERE guild_id = ?', (ticket_number + 1, guild_id))
            conn.commit()
            conn.close()
            logger.info(f"Ticket sayacı artırıldı: {ticket_number} -> {ticket_number + 1}")
            return ticket_number
        else:
            logger.warning(f"Ticket sayacı bulunamadı, varsayılan 1 döndürülüyor")
        
        conn.close()
        return 1
    except Exception as e:
        logger.error(f"get_next_ticket_number hatası: {e}")
        logger.error(f"Detaylar: guild_id={guild_id}")
        return 1

# Ticket kategorileri
TICKET_CATEGORIES = [
    {
        "id": "player_complaint",
        "name": "Oyuncu Şikayet",
        "emoji": "⚖️",
        "description": "Oyuncular hakkında şikayet bildirmek için"
    },
    {
        "id": "penalty_appeal",
        "name": "Ceza İtiraz",
        "emoji": "📝",
        "description": "Ceza itirazı yapmak için"
    },
    {
        "id": "admin_complaint",
        "name": "Yönetici Şikayet",
        "emoji": "👤",
        "description": "Yöneticiler hakkında şikayet bildirmek için"
    },
    {
        "id": "other_requests",
        "name": "Diğer Talepler",
        "emoji": "❓",
        "description": "Diğer talepler için"
    }
]

# Ticket oluşturma fonksiyonu
async def create_ticket_with_category(interaction, selected_category):
    """Kategori ile yeni ticket oluşturur"""
    logger.info(f"create_ticket_with_category başlatıldı: user={interaction.user.display_name}, category={selected_category['name']}")
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    logger.info(f"Guild ID: {guild_id}, User ID: {user_id}")
    
    # Ticket konfigürasyonunu kontrol et
    logger.info("Ticket konfigürasyonu kontrol ediliyor...")
    config = get_ticket_config(guild_id)
    if not config:
        logger.warning(f"Ticket konfigürasyonu bulunamadı: guild_id={guild_id}")
        await interaction.followup.send("❌ Ticket sistemi kurulmamış! Lütfen admin ile iletişime geçin.", ephemeral=True)
        return
    logger.info(f"Ticket konfigürasyonu bulundu: category_id={config['category_id']}, support_role_id={config['support_role_id']}")
    
    # Günlük limit kontrolü
    logger.info("Günlük limit kontrol ediliyor...")
    daily_count = get_user_daily_tickets(guild_id, user_id)
    logger.info(f"Günlük ticket sayısı: {daily_count}/{config['daily_limit']}")
    if daily_count >= config['daily_limit']:
        logger.warning(f"Günlük limit doldu: {daily_count}/{config['daily_limit']}")
        await interaction.followup.send(f"❌ Günlük ticket limitiniz doldu! ({config['daily_limit']}/gün)", ephemeral=True)
        return
    
    # Kullanıcının zaten açık ticket'ı var mı?
    logger.info("Aktif ticket kontrol ediliyor...")
    active_ticket = get_user_active_ticket(guild_id, user_id)
    if active_ticket:
        logger.warning(f"Aktif ticket bulundu: #{active_ticket['ticket_number']}")
        await interaction.followup.send("❌ Zaten açık bir ticket'ınız var!", ephemeral=True)
        return
    logger.info("Aktif ticket bulunamadı, devam ediliyor...")
    
    # Ticket kanalı oluştur
    logger.info("Ticket kanalı oluşturuluyor...")
    category = interaction.guild.get_channel(config['category_id'])
    support_role = interaction.guild.get_role(config['support_role_id'])
    
    logger.info(f"Kategori bulundu: {category.name if category else 'Bulunamadı'}")
    logger.info(f"Destek rolü bulundu: {support_role.name if support_role else 'Bulunamadı'}")
    
    if not category:
        logger.error(f"Ticket kategorisi bulunamadı: category_id={config['category_id']}")
        await interaction.followup.send("❌ Ticket kategorisi bulunamadı!", ephemeral=True)
        return
    
    ticket_number = get_next_ticket_number(guild_id)
    channel_name = f"ticket-{ticket_number}"
    logger.info(f"Ticket numarası: {ticket_number}, Kanal adı: {channel_name}")
    
    try:
        # Kanal oluştur
        logger.info("Discord kanalı oluşturuluyor...")
        channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                support_role: discord.PermissionOverwrite(read_messages=True, send_messages=True) if support_role else None,
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
        )
        
        # Ticket kaydını oluştur
        logger.info("Ticket kaydı veritabanında oluşturuluyor...")
        create_ticket_record(guild_id, ticket_number, user_id, channel.id, selected_category["id"], selected_category["name"])
        logger.info(f"Ticket kaydı oluşturuldu: ticket_number={ticket_number}, channel_id={channel.id}")
        
        # Günlük sayacı artır
        logger.info("Günlük ticket sayacı artırılıyor...")
        increment_user_daily_tickets(guild_id, user_id)
        logger.info("Günlük ticket sayacı artırıldı")
        
        # Hoş geldin mesajı
        logger.info("Hoş geldin embed'i oluşturuluyor...")
        embed = discord.Embed(
            title=f"🎉 {selected_category['emoji']} {selected_category['name']} Ticket'ı Oluşturuldu!",
            description=f"Merhaba {interaction.user.mention}!\n\n**Kategori:** {selected_category['emoji']} {selected_category['name']}\n**Açıklama:** {selected_category['description']}\n\nDestek ekibimiz en kısa sürede size yardımcı olacaktır.",
            color=0x57F287  # Yeşil
        )
        embed.add_field(
            name="📊 Ticket Bilgileri",
            value=f"**Numara:** #{ticket_number}\n**Oluşturulma:** {datetime.now().strftime('%d/%m/%Y %H:%M')}\n**Günlük Kalan:** {config['daily_limit'] - daily_count - 1}",
            inline=False
        )
        embed.add_field(name="📝 Bilgi", value="Lütfen sorununuzu detaylı bir şekilde açıklayın.", inline=False)

        
        # Ticket mesajını gönder (kapatma butonu olmadan)
        logger.info("Ticket mesajı gönderiliyor...")
        await channel.send(embed=embed)
        logger.info("Hoş geldin mesajı kanala gönderildi")
        
        # Kullanıcıya bilgi ver
        logger.info("Kullanıcıya followup mesajı gönderiliyor...")
        try:
            await interaction.followup.send(f"✅ **{selected_category['emoji']} {selected_category['name']}** ticket'ı oluşturuldu! {channel.mention}", ephemeral=True)
            logger.info("Kullanıcıya followup mesajı gönderildi")
        except Exception as e:
            logger.error(f"Followup mesaj hatası: {e}")
        
        # Destek ekibine bildirim
        if support_role:
            logger.info("Destek ekibine bildirim gönderiliyor...")
            try:
                notification_embed = discord.Embed(
                    title="🆕 Yeni Ticket",
                    description=f"**Kategori:** {selected_category['emoji']} {selected_category['name']}\n**Kullanıcı:** {interaction.user.mention}\n**Kanal:** {channel.mention}\n**Numara:** #{ticket_number}",
                    color=0x5865F2  # Mavi
                )
                await channel.send(f"{support_role.mention}", embed=notification_embed)
                logger.info("Destek ekibine bildirim gönderildi")
            except Exception as e:
                logger.error(f"Destek ekibine bildirim hatası: {e}")
        else:
            logger.warning("Destek rolü bulunamadı, bildirim gönderilmedi")
        
        # Ticket oluşturma logunu gönder
        logger.info("Ticket aktivite logu gönderiliyor...")
        try:
            await log_ticket_activity(guild_id, "Oluşturuldu", ticket_number, user_id, channel.id, f"Kategori: {selected_category['name']}")
            logger.info("Ticket aktivite logu gönderildi")
        except Exception as e:
            logger.error(f"Ticket log hatası: {e}")
        
        logger.info(f"Ticket #{ticket_number} başarıyla oluşturuldu ve tüm işlemler tamamlandı")
        
    except discord.Forbidden:
        logger.error("Discord Forbidden hatası: Yetki yetersiz")
        try:
            await interaction.followup.send("❌ Ticket oluşturulamıyor! Yetki hatası.", ephemeral=True)
        except Exception as e:
            logger.error(f"Forbidden followup hatası: {e}")
    except Exception as e:
        logger.error(f"Ticket oluşturma genel hatası: {e}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Exception args: {e.args}")
        try:
            await interaction.followup.send(f"❌ Ticket oluşturulurken hata oluştu: {str(e)}", ephemeral=True)
        except Exception as e2:
            logger.error(f"Exception followup hatası: {e2}")
            logger.error(f"Original error: {e}")

@bot.event
async def on_ready():
    logger.info(f'✅ {bot.user} olarak giriş yapıldı!')
    logger.info(f'📊 {len(bot.guilds)} sunucuda aktif')
    logger.info(f'🎯 {Config.BOT_NAME} hazır!')
    
    # Slash komutları senkronize et
    try:
        synced = await bot.tree.sync()
        logger.info(f'✅ {len(synced)} slash komut senkronize edildi! (invite, stats, leaderboard, adminstats, suspicious, reset, help)')
    except Exception as e:
        logger.error(f'❌ Slash komut senkronizasyon hatası: {e}')
    
    # Mevcut davetleri yükle
    await load_invites()
    
    # Persistent view'ları kaydet
    logger.info("Persistent view'lar kaydediliyor...")
    bot.add_view(TicketCategoryView(TICKET_CATEGORIES))
    logger.info("Persistent view'lar kaydedildi")

# Davet takip sistemi
async def load_invites():
    """Sunucudaki mevcut davetleri yükler ve veritabanına kaydeder"""
    logger.info("🔄 load_invites() fonksiyonu başlatıldı")
    
    for guild in bot.guilds:
        try:
            logger.info(f"🔍 {guild.name} sunucusu kontrol ediliyor...")
            
            # Bot'un davet izni var mı kontrol et
            if not guild.me.guild_permissions.manage_guild:
                logger.warning(f'⚠️ {guild.name} sunucusunda davet izni yok, atlanıyor...')
                continue
                
            logger.info(f"✅ {guild.name} sunucusunda davet izni var, davetler alınıyor...")
            invites = await guild.invites()
            logger.info(f'📊 {guild.name} sunucusunda {len(invites)} davet bulundu')
            
            # Mevcut davetleri veritabanına yükle
            logger.info(f"💾 {len(invites)} davet veritabanına yükleniyor...")
            conn = sqlite3.connect(Config.DATABASE_NAME)
            cursor = conn.cursor()
            
            invite_details = []
            for i, invite in enumerate(invites, 1):
                logger.info(f"📝 Davet {i}/{len(invites)} işleniyor: {invite.code}")
                
                # Davet oluşturan kişiyi doğru şekilde al
                inviter_id = invite.inviter.id if invite.inviter else 0
                
                # Eğer bot tarafından oluşturulduysa, veritabanından bul
                if inviter_id == bot.user.id:
                    # Veritabanından bu daveti bul
                    cursor.execute('SELECT user_id FROM invite_codes WHERE code = ?', (invite.code,))
                    result = cursor.fetchone()
                    if result:
                        inviter_id = result[0]
                
                # Önce bu davet kodu zaten var mı kontrol et
                cursor.execute('SELECT id FROM invite_codes WHERE code = ?', (invite.code,))
                existing_invite = cursor.fetchone()
                
                if existing_invite:
                    # Mevcut daveti güncelle
                    cursor.execute('''
                        UPDATE invite_codes 
                        SET user_id = ?, uses = ?, created_at = ?
                        WHERE code = ?
                    ''', (inviter_id, invite.uses, invite.created_at, invite.code))
                    logger.info(f"🔄 Davet {invite.code} güncellendi")
                else:
                    # Yeni davet ekle
                    cursor.execute('''
                        INSERT INTO invite_codes (code, user_id, created_at, uses)
                        VALUES (?, ?, ?, ?)
                    ''', (invite.code, inviter_id, invite.created_at, invite.uses))
                    logger.info(f"➕ Yeni davet {invite.code} eklendi")
                
                # Davet detaylarını hazırla
                try:
                    inviter_user = await bot.fetch_user(inviter_id)
                    inviter_name = inviter_user.display_name if inviter_user else f"ID: {inviter_id}"
                except:
                    inviter_name = f"ID: {inviter_id}"
                    
                invite_details.append(f"{inviter_name} (ID: {inviter_id}): {invite.code}")
            
            conn.commit()
            conn.close()
            logger.info(f"💾 Veritabanı işlemleri tamamlandı")
            
            # Davet detaylarını göster
            logger.info(f'📊 {guild.name} sunucusunda {len(invites)} davet yüklendi:')
            for detail in invite_details:
                logger.info(f'   • {detail}')
            
        except discord.Forbidden:
            logger.warning(f'⚠️ {guild.name} sunucusunda davet izni yok, atlanıyor...')
        except Exception as e:
            logger.error(f'❌ {guild.name} sunucusunda davet yüklenirken hata: {e}')
            logger.error(f'❌ Hata detayı: {type(e).__name__}: {str(e)}')
    
    logger.info("✅ load_invites() fonksiyonu tamamlandı")

@bot.event
async def on_invite_create(invite):
    """Yeni davet oluşturulduğunda"""
    try:
        # Bot'un davet izni var mı kontrol et
        if not invite.guild.me.guild_permissions.manage_guild:
            logger.warning(f'⚠️ {invite.guild.name} sunucusunda davet izni yok, davet takibi yapılamıyor')
            return
            
        # Davet oluşturan kişiyi doğru şekilde al
        inviter_id = invite.inviter.id if invite.inviter else 0
        
        # Eğer bot tarafından oluşturulduysa, son kullanıcıyı bul
        if inviter_id == bot.user.id:
            # Veritabanından en son davet oluşturan kullanıcıyı bul
            conn = sqlite3.connect(Config.DATABASE_NAME)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_id FROM invite_codes 
                WHERE code = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', (invite.code,))
            
            result = cursor.fetchone()
            if result:
                inviter_id = result[0]
            
            conn.close()
        
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        # Önce bu davet kodu zaten var mı kontrol et
        cursor.execute('SELECT id FROM invite_codes WHERE code = ?', (invite.code,))
        existing_invite = cursor.fetchone()
        
        if existing_invite:
            # Mevcut daveti güncelle
            cursor.execute('''
                UPDATE invite_codes 
                SET user_id = ?, uses = ?, created_at = ?
                WHERE code = ?
            ''', (inviter_id, invite.uses, invite.created_at, invite.code))
        else:
            # Yeni davet ekle
            cursor.execute('''
                INSERT INTO invite_codes (code, user_id, created_at, uses)
                VALUES (?, ?, ?, ?)
            ''', (invite.code, inviter_id, invite.created_at, invite.uses))
        
        conn.commit()
        conn.close()
        
        # Davet eden kullanıcı adını al
        try:
            inviter_user = await bot.fetch_user(inviter_id)
            inviter_name = inviter_user.display_name if inviter_user else f"ID: {inviter_id}"
        except:
            inviter_name = f"ID: {inviter_id}"
        
        # Toplam davet sayısını al ve logla
        try:
            all_invites = await invite.guild.invites()
            logger.info(f'🔗 Yeni davet oluşturuldu: {invite.code} (Kullanıcı: {inviter_name})')
            logger.info(f'📊 Sunucuda toplam {len(all_invites)} davet bulundu')
        except:
            logger.info(f'🔗 Yeni davet oluşturuldu: {invite.code} (Kullanıcı: {inviter_name})')
            
    except Exception as e:
        logger.error(f'❌ Davet kaydedilirken hata: {e}')

@bot.event
async def on_member_join(member):
    """Yeni üye katıldığında davet takibi"""
    try:
        # Bot'un davet izni var mı kontrol et
        if not member.guild.me.guild_permissions.manage_guild:
            logger.warning(f'⚠️ {member.guild.name} sunucusunda davet izni yok, üye takibi yapılamıyor')
            return
        
        # Bot koruması - Eğer katılan üye bir bot ise (config'den kontrol et)
        if Config.SECURITY['BOT_PROTECTION'] and member.bot:
            mark_user_as_bot(member.id)
            logger.info(f'🤖 Bot tespit edildi: {member.display_name} (ID: {member.id})')
            return
        
        # Sunucudaki tüm davetleri al
        invites = await member.guild.invites()
        
        # Hangi davet kullanıldığını bul
        for invite in invites:
            if invite.uses > 0:  # Davet kullanılmış
                # Veritabanında bu daveti bul
                conn = sqlite3.connect(Config.DATABASE_NAME)
                cursor = conn.cursor()
                
                cursor.execute('SELECT uses FROM invite_codes WHERE code = ?', (invite.code,))
                result = cursor.fetchone()
                
                if result and result[0] < invite.uses:
                    # Davet oluşturan kişiyi doğru şekilde al
                    inviter_id = invite.inviter.id if invite.inviter else 0
                    
                    # Eğer bot tarafından oluşturulduysa, veritabanından bul
                    if inviter_id == bot.user.id:
                        cursor.execute('SELECT user_id FROM invite_codes WHERE code = ?', (invite.code,))
                        inviter_result = cursor.fetchone()
                        if inviter_result:
                            inviter_id = inviter_result[0]
                    
                    # Fake davet koruması kontrol et
                    can_invite, reason = can_user_invite(inviter_id, member.id)
                    
                    if not can_invite:
                        logger.warning(f'🚫 Fake davet engellendi: {member.display_name} - {reason}')
                        
                        # Davet eden kullanıcıya uyarı gönder
                        try:
                            inviter_user = await bot.fetch_user(inviter_id)
                            if inviter_user:
                                embed = discord.Embed(
                                    title="🚫 Davet Engellendi!",
                                    description=f"**{member.display_name}** kullanıcısı davet edilemedi!\n\n**Sebep:** {reason}",
                                    color=0xED4245,
                                    timestamp=datetime.now()
                                )
                                await inviter_user.send(embed=embed)
                        except:
                            pass
                        
                        conn.close()
                        continue
                    
                    # Davet eden kullanıcıya DM gönder
                    if inviter_id != bot.user.id:
                        try:
                            cursor.execute('''
                                INSERT INTO invited_users (inviter_id, invited_user_id, invited_at, invite_code)
                                VALUES (?, ?, ?, ?)
                            ''', (inviter_id, member.id, datetime.now(), invite.code))
                            
                            # Davet kullanım sayısını güncelle
                            cursor.execute('UPDATE invite_codes SET uses = ? WHERE code = ?', (invite.uses, invite.code))
                            
                            conn.commit()
                            conn.close()
                            
                            # Davet eden kullanıcı adını al
                            try:
                                inviter_user = await bot.fetch_user(inviter_id)
                                inviter_name = inviter_user.display_name if inviter_user else f"ID: {inviter_id}"
                            except:
                                inviter_name = f"ID: {inviter_id}"
                                
                            logger.info(f'🎉 Yeni üye {member.display_name} {inviter_name} tarafından davet edildi!')
                            
                            # Davet eden kullanıcıya DM gönder
                            try:
                                embed = discord.Embed(
                                    title="🎉 Yeni Davet!",
                                    description=f"**{member.display_name}** senin davet linkinle sunucuya katıldı!",
                                    color=0x57F287,
                                    timestamp=datetime.now()
                                )
                                embed.add_field(
                                    name="🛡️ Güvenlik",
                                    value="Bu davet güvenlik kontrollerinden geçti ve sayıldı.",
                                    inline=False
                                )
                                await inviter_user.send(embed=embed)
                            except:
                                pass  # DM gönderilemezse sessizce geç
                            
                            break
                        except sqlite3.IntegrityError:
                            # Kullanıcı zaten davet edilmiş
                            logger.warning(f'🚫 Kullanıcı zaten davet edilmiş: {member.display_name}')
                            conn.close()
                            continue
                    
                    conn.close()
    except Exception as e:
        logger.error(f'❌ Üye katılım takibinde hata: {e}')

# Slash Komutlar
@bot.tree.command(name="invite", description="Sunucu için davet linki oluşturur veya mevcut linkini gösterir")
async def invite_command(interaction: discord.Interaction):
    try:
        # Kullanıcının zaten davet linki var mı kontrol et
        if user_has_invite_link(interaction.user.id):
            # Mevcut davet linkini getir
            invite_data = get_user_invite_link(interaction.user.id)
            if invite_data:
                code, uses = invite_data
                invite_url = f"https://discord.gg/{code}"
                
                embed = discord.Embed(
                    title="🔗 Mevcut Davet Linkin",
                    description=f"**Link:** {invite_url}\n\n**Kullanım Sayısı:** {uses} kişi\n\nBu linki arkadaşlarınızla paylaşarak sunucunuza davet edebilirsiniz!",
                    color=0x5865F2,  # Discord mavi
                    timestamp=datetime.now()
                )
                embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
                embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        
        # Yeni davet linki oluştur
        invite_link = await interaction.channel.create_invite(
            max_age=0,  # Süresiz
            max_uses=0,  # Sınırsız kullanım
            reason=f"{interaction.user.display_name} tarafından davet linki oluşturuldu"
        )
        
        embed = discord.Embed(
            title="🔗 Yeni Davet Linki Oluşturuldu!",
            description=f"**Link:** {invite_link.url}\n\n**Önemli:** Her kullanıcı sadece 1 adet davet linki oluşturabilir!\n\nBu linki arkadaşlarınızla paylaşarak sunucunuza davet edebilirsiniz!",
            color=0x57F287,  # Discord yeşil
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
        
        # Önce response gönder, sonra veritabanı işlemlerini yap
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Davet kodunu veritabanına kaydet (response gönderildikten sonra)
        try:
            conn = sqlite3.connect(Config.DATABASE_NAME)
            cursor = conn.cursor()
            
            # Önce bu davet kodu zaten var mı kontrol et
            cursor.execute('SELECT id FROM invite_codes WHERE code = ?', (invite_link.code,))
            existing_invite = cursor.fetchone()
            
            if existing_invite:
                # Mevcut daveti güncelle
                cursor.execute('''
                    UPDATE invite_codes 
                    SET user_id = ?, created_at = ?
                    WHERE code = ?
                ''', (interaction.user.id, datetime.now(), invite_link.code))
            else:
                # Yeni davet ekle
                cursor.execute('''
                    INSERT INTO invite_codes (code, user_id, created_at, uses)
                    VALUES (?, ?, ?, ?)
                ''', (invite_link.code, interaction.user.id, datetime.now(), 0))
            
            conn.commit()
            conn.close()
            logger.info(f'🔗 Yeni davet linki veritabanına kaydedildi: {invite_link.code} (Kullanıcı: {interaction.user.display_name})')
        except Exception as e:
            logger.error(f'❌ Davet veritabanına kaydedilirken hata: {e}')
            # Veritabanı hatası olsa bile kullanıcıya tekrar mesaj gönderme
        
    except discord.Forbidden:
        embed = discord.Embed(
            title="❌ Yetki Hatası",
            description="Bu kanal için davet linki oluşturamıyorum!\n\n**Gerekli yetkiler:**\n• Davet Oluştur",
            color=0xED4245,  # Discord kırmızı
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        embed = discord.Embed(
            title="❌ Hata",
            description="Davet linki oluşturulurken bir hata oluştu!",
            color=0xED4245,  # Discord kırmızı
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)



@bot.tree.command(name="leaderboard", description="Davet sıralamasını gösterir")
async def leaderboard_command(interaction: discord.Interaction):
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    # Davet sıralamasını getir (en çok davet edenler)
    cursor.execute('''
        SELECT inviter_id, COUNT(*) as invite_count
        FROM invited_users 
        GROUP BY inviter_id 
        ORDER BY invite_count DESC 
        LIMIT 10
    ''')
    
    leaderboard_data = cursor.fetchall()
    
    if not leaderboard_data:
        embed = discord.Embed(
            title="🏆 Davet Sıralaması",
            description="Henüz kimse davet etmemiş!\n\n🔗 **/invite** komutunu kullanarak davet linki oluşturun!",
            color=0x5865F2,  # Discord mavi
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
    else:
        # Sıralama listesini oluştur
        leaderboard_list = []
        for i, (inviter_id, invite_count) in enumerate(leaderboard_data, 1):
            try:
                user = await bot.fetch_user(inviter_id)
                # Emoji ile sıralama
                if i == 1:
                    medal = "🥇"
                elif i == 2:
                    medal = "🥈"
                elif i == 3:
                    medal = "🥉"
                else:
                    medal = f"**{i}.**"
                
                leaderboard_list.append(f"{medal} **{user.name}** - `{invite_count}` davet")
            except:
                leaderboard_list.append(f"**{i}.** **Bilinmeyen Kullanıcı** - `{invite_count}` davet")
        
        embed = discord.Embed(
            title="🏆 Davet Sıralaması",
            description="**En Çok Davet Eden Kullanıcılar:**\n\n" + "\n".join(leaderboard_list),
            color=0xFFD700,  # Altın rengi
            timestamp=datetime.now()
        )
        
        # Kullanıcının kendi sıralamasını da göster
        user_id = interaction.user.id
        cursor.execute('SELECT COUNT(*) FROM invited_users WHERE inviter_id = ?', (user_id,))
        user_invites = cursor.fetchone()[0]
        
        embed.add_field(
            name="📈 Senin İstatistiğin",
            value=f"**Davet Ettiğin Kişi Sayısı:** `{user_invites}`",
            inline=False
        )
        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
    
    conn.close()
    
    await interaction.response.send_message(embed=embed, ephemeral=True)



@bot.tree.command(name="stats", description="Oluşturduğun davet linkinin istatistiklerini gösterir")
async def stats_command(interaction: discord.Interaction):
    try:
        # Interaction'ı defer et (timeout'u önle)
        await interaction.response.defer(ephemeral=True)
        
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        # Kullanıcının davet linkini getir
        cursor.execute('''
            SELECT code, uses, created_at FROM invite_codes 
            WHERE user_id = ?
        ''', (interaction.user.id,))
        
        user_invite = cursor.fetchone()
        
        if not user_invite:
            embed = discord.Embed(
                title="📊 Davet İstatistiklerin",
                description="❌ Henüz hiç davet linki oluşturmamışsın!\n\n`/invite` komutuyla davet linki oluşturabilirsin.",
                color=0xE74C3C,  # Kırmızı
                timestamp=datetime.now()
            )
        else:
            code, uses, created_at = user_invite
            invite_url = f"https://discord.gg/{code}"
            
            try:
                # Tarih formatını dönüştür
                if isinstance(created_at, str):
                    created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00')).strftime("%d/%m/%Y %H:%M")
                else:
                    created_date = created_at.strftime("%d/%m/%Y %H:%M")
            except:
                created_date = "Bilinmiyor"
            
            embed = discord.Embed(
                title="📊 Davet İstatistiklerin",
                description=f"🔗 **Davet Linkin:** {invite_url}\n\n🎯 **Toplam Davet Edilen:** {uses} kişi\n📅 **Oluşturulma Tarihi:** {created_date}\n\n**Not:** Her kullanıcı sadece 1 adet davet linki oluşturabilir!",
                color=0x57F287,  # Yeşil
                timestamp=datetime.now()
            )
        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
        
        conn.close()
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f'❌ Stats komutu hatası: {e}')
        embed = discord.Embed(
            title="❌ Hata",
            description="İstatistikler alınırken bir hata oluştu!",
            color=0xE74C3C
        )
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            try:
                # Eğer followup da çalışmazsa, yeni mesaj gönder
                await interaction.channel.send(embed=embed, delete_after=10.0)
            except:
                pass  # Sessizce geç, log spam yapma

@bot.tree.command(name="adminstats", description="Sunucudaki tüm davet istatistiklerini gösterir (Sadece Yönetici)")
async def adminstats_command(interaction: discord.Interaction):
    # Sadece Yönetici (Administrator) yetkisi kontrol et
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Yetki Hatası",
            description="Bu komutu kullanmak için **Yönetici (Administrator)** yetkisine sahip olmalısın!",
            color=0xED4245,  # Kırmızı
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        # Interaction'ı defer et (timeout'u önle)
        await interaction.response.defer(ephemeral=True)
        
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        # Tüm davetleri getir (en çok kullanılanlar üstte)
        cursor.execute('''
            SELECT code, user_id, uses, created_at FROM invite_codes 
            ORDER BY uses DESC, created_at DESC
        ''')
        
        all_invites = cursor.fetchall()
        
        if not all_invites:
            embed = discord.Embed(
                title="📊 Sunucu Davet İstatistikleri",
                description="❌ Henüz hiç davet linki oluşturulmamış!",
                color=0xE74C3C,  # Kırmızı
                timestamp=datetime.now()
            )
        else:
            # Toplam istatistikler
            total_invites = len(all_invites)
            total_uses = sum(invite[2] for invite in all_invites)
            
            # Davet detaylarını hazırla
            invite_details = []
            for i, (code, user_id, uses, created_at) in enumerate(all_invites[:15], 1):  # En çok 15 davet göster
                try:
                    user = await bot.fetch_user(user_id)
                    user_name = user.display_name if user else f"ID: {user_id}"
                except:
                    user_name = f"ID: {user_id}"
                
                try:
                    # Tarih formatını dönüştür
                    if isinstance(created_at, str):
                        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00')).strftime("%d/%m/%Y")
                    else:
                        created_date = created_at.strftime("%d/%m/%Y")
                except:
                    created_date = "Bilinmiyor"
                
                # Emoji ile sıralama
                if i == 1:
                    medal = "🥇"
                elif i == 2:
                    medal = "🥈"
                elif i == 3:
                    medal = "🥉"
                else:
                    medal = f"**{i}.**"
                
                invite_details.append(f"{medal} **{user_name}** - `{code}` - **{uses} kullanım** _(Oluşturulma: {created_date})_")
            
            # Eğer daha fazla davet varsa
            if len(all_invites) > 15:
                invite_details.append(f"_... ve {len(all_invites) - 15} davet daha_")
            
            embed = discord.Embed(
                title="📊 Sunucu Davet İstatistikleri",
                description=f"🎯 **Toplam Davet Edilen:** {total_uses} kişi\n📝 **Oluşturulan Davet:** {total_invites} adet\n\n**En Çok Kullanılan Davetler:**\n" + "\n".join(invite_details),
                color=0x9B59B6,  # Mor
                timestamp=datetime.now()
            )
        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
        
        conn.close()
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f'❌ AdminStats komutu hatası: {e}')
        embed = discord.Embed(
            title="❌ Hata",
            description="İstatistikler alınırken bir hata oluştu!",
            color=0xE74C3C
        )
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            try:
                # Eğer followup da çalışmazsa, yeni mesaj gönder
                await interaction.channel.send(embed=embed, delete_after=10.0)
            except:
                pass  # Sessizce geç, log spam yapma

@bot.tree.command(name="help", description="Bot komutları hakkında bilgi verir")
async def help_command(interaction: discord.Interaction):
    """Bot komutları hakkında bilgi verir"""
    try:
        embed = discord.Embed(
            title=f"🤖 {Config.BOT_NAME} Komut Listesi",
            description="Aşağıda kullanabileceğiniz tüm komutlar listelenmiştir:",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        # Davet Sistemi Komutları (Herkese açık)
        embed.add_field(
            name="🎯 **Davet Sistemi**",
            value="• `/invite` - Davet linki oluşturur\n• `/stats` - Davet istatistiklerinizi gösterir\n• `/leaderboard` - Davet sıralamasını gösterir",
            inline=False
        )
        
        # Ticket Sistemi Komutları (Herkese açık)
        if interaction.user.guild_permissions.administrator:
            # Admin kullanıcılar için tüm ticket komutları
            embed.add_field(
                name="🎫 **Ticket Sistemi**",
                value="• `/close` - Bu kanalın ticket'ını kapatır (Sadece Yönetici)\n• `/ticket-stats` - Ticket istatistiklerini gösterir\n• `/ticket-setup` - Ticket sistemi kurulumu (kategori, destek rolü, log kanalı)\n• `/ticket-panel` - Ticket paneli oluşturur\n• `/ticket-list` - Aktif ticket'ları listeler",
                inline=False
            )
        else:
            # Normal kullanıcılar için sadece başlık ve bilgi
            embed.add_field(
                name="🎫 **Ticket Sistemi**",
                value="Ticket açmak için ticket kanalını kullanabilirsiniz.",
                inline=False
            )
        
        # Admin Komutları (Sadece admin yetkisi olanlara)
        if interaction.user.guild_permissions.administrator:
            embed.add_field(
                name="⚙️ **Admin Komutları**",
                value="• `/adminstats` - Admin davet istatistiklerini gösterir\n• `/suspicious` - Şüpheli davet aktivitelerini gösterir\n• `/reset` - Tüm davet verilerini sıfırlar",
                inline=False
            )
        
        # Genel Bilgiler
        embed.add_field(
            name="ℹ️ **Genel Bilgiler**",
            value=f"• **Bot Adı:** {Config.BOT_NAME}\n• **Prefix:** `/` (Slash Commands)\n• **Davet Limit:** Günlük 5 ticket\n• **Destek:** Admin ile iletişime geçin",
            inline=False
        )
        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f'❌ Help komut hatası: {e}')
        try:
            embed = discord.Embed(
                title="❌ Hata",
                description="Komut listesi gösterilirken bir hata oluştu!",
                color=0xED4245,
                timestamp=datetime.now()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            try:
                # Eğer followup da çalışmazsa, yeni mesaj gönder
                await interaction.channel.send(embed=embed, delete_after=10.0)
            except:
                pass  # Sessizce geç, log spam yapma

@bot.tree.command(name="suspicious", description="Şüpheli davet aktivitelerini gösterir (Sadece Yönetici)")
async def suspicious_command(interaction: discord.Interaction):
    # Sadece Yönetici (Administrator) yetkisi kontrol et
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Yetki Hatası",
            description="Bu komutu kullanmak için **Yönetici (Administrator)** yetkisine sahip olmalısın!",
            color=0xED4245,  # Kırmızı
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        # Interaction'ı defer et (timeout'u önle)
        await interaction.response.defer(ephemeral=True)
        
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        # Şüpheli davet aktivitelerini getir
        cursor.execute('''
            SELECT inviter_id, invite_count, first_invite_at, last_invite_at
            FROM suspicious_invites 
            ORDER BY invite_count DESC, last_invite_at DESC
        ''')
        
        suspicious_data = cursor.fetchall()
        
        if not suspicious_data:
            embed = discord.Embed(
                title="🚨 Şüpheli Davet Aktivitesi",
                description="✅ Henüz şüpheli davet aktivitesi tespit edilmedi!",
                color=0x57F287,  # Yeşil
                timestamp=datetime.now()
            )
        else:
            # Şüpheli aktivite detaylarını hazırla
            suspicious_list = []
            for i, (inviter_id, invite_count, first_invite_at, last_invite_at) in enumerate(suspicious_data[:10], 1):
                try:
                    user = await bot.fetch_user(inviter_id)
                    user_name = user.display_name if user else f"ID: {inviter_id}"
                except:
                    user_name = f"ID: {inviter_id}"
                
                try:
                    # Tarih formatını dönüştür
                    if isinstance(first_invite_at, str):
                        first_date = datetime.fromisoformat(first_invite_at.replace('Z', '+00:00')).strftime("%d/%m/%Y %H:%M")
                    else:
                        first_date = first_invite_at.strftime("%d/%m/%Y %H:%M")
                    
                    if isinstance(last_invite_at, str):
                        last_date = datetime.fromisoformat(last_invite_at.replace('Z', '+00:00')).strftime("%d/%m/%Y %H:%M")
                    else:
                        last_date = last_invite_at.strftime("%d/%m/%Y %H:%M")
                except:
                    first_date = "Bilinmiyor"
                    last_date = "Bilinmiyor"
                
                suspicious_list.append(f"**{i}.** **{user_name}** - `{invite_count}` şüpheli aktivite\n   📅 İlk: {first_date} | Son: {last_date}")
            
            # Eğer daha fazla şüpheli aktivite varsa
            if len(suspicious_data) > 10:
                suspicious_list.append(f"_... ve {len(suspicious_data) - 10} şüpheli aktivite daha_")
            
            embed = discord.Embed(
                title="🚨 Şüpheli Davet Aktivitesi",
                description=f"⚠️ **Toplam Şüpheli Aktivite:** {len(suspicious_data)} adet\n\n**En Çok Şüpheli Aktivite:**\n" + "\n".join(suspicious_list),
                color=0xFF6B6B,  # Kırmızımsı
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="🛡️ Güvenlik Bilgisi",
                value="Şüpheli aktivite tespit edildiğinde otomatik olarak loglanır ve davetler engellenir.",
                inline=False
            )
        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and bot.user.avatar.url else None)
        
        conn.close()
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f'❌ Suspicious komutu hatası: {e}')
        embed = discord.Embed(
            title="❌ Hata",
            description="Şüpheli aktivite bilgileri alınırken bir hata oluştu!",
            color=0xE74C3C
        )
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            try:
                # Eğer followup da çalışmazsa, yeni mesaj gönder
                await interaction.channel.send(embed=embed, delete_after=10.0)
            except:
                pass  # Sessizce geç, log spam yapma

@bot.tree.command(name="reset", description="Tüm davet verilerini sıfırlar (Sadece Yönetici)")
async def reset_command(interaction: discord.Interaction):
    # Sadece Yönetici (Administrator) yetkisi kontrol et
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Yetki Hatası",
            description="Bu komutu kullanmak için **Yönetici (Administrator)** yetkisine sahip olmalısın!\n\n**Not:** Bu komut tüm davet verilerini kalıcı olarak siler!",
            color=0xED4245,  # Kırmızı
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        # Onay embed'i gönder
        embed = discord.Embed(
            title="⚠️ DİKKAT: Veri Sıfırlama",
            description="**Bu komut tüm davet verilerini kalıcı olarak silecek!**\n\n**Silinecek veriler:**\n• Tüm davet kodları\n• Tüm davet edilen kullanıcılar\n• Şüpheli aktivite kayıtları\n• Bot koruma kayıtları\n• Ticket sistemi kurulumu (kategori, destek rolü, log kanalı)\n• Tüm ticket'lar\n• Ticket günlük sayıları\n• Log dosyaları\n\n**Bu işlem geri alınamaz!**\n\nDevam etmek için **'EVET'** yazın.",
            color=0xFF6B6B,  # Uyarı rengi
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Kullanıcıdan onay bekle
        def check(message):
            return message.author == interaction.user and message.channel == interaction.channel and message.content.upper() == "EVET"
        
        try:
            await bot.wait_for('message', timeout=30.0, check=check)
            
            # Onay alındı, verileri sıfırla
            
            # Önce Discord sunucusundaki tüm davetleri sil
            try:
                logger.info('🗑️ Discord sunucusundaki davetler siliniyor...')
                for guild in bot.guilds:
                    if guild.me.guild_permissions.manage_guild:
                        invites = await guild.invites()
                        for invite in invites:
                            try:
                                await invite.delete(reason=f"Reset komutu ile {interaction.user.display_name} tarafından silindi")
                                logger.info(f'🗑️ Discord daveti silindi: {invite.code}')
                            except Exception as e:
                                logger.error(f'❌ Discord daveti silinirken hata: {e}')
                        logger.info(f'✅ {guild.name} sunucusundaki {len(invites)} davet silindi')
            except Exception as e:
                logger.error(f'❌ Discord davetleri silinirken hata: {e}')
            
            # Sonra veritabanını temizle
            conn = sqlite3.connect(Config.DATABASE_NAME)
            cursor = conn.cursor()
            
            # Tüm tabloları temizle
            cursor.execute('DELETE FROM invite_codes')
            cursor.execute('DELETE FROM invited_users')
            cursor.execute('DELETE FROM suspicious_invites')
            cursor.execute('DELETE FROM bot_protection')
            cursor.execute('DELETE FROM ticket_config')
            cursor.execute('DELETE FROM tickets')
            cursor.execute('DELETE FROM user_daily_tickets')
            
            conn.commit()
            conn.close()
            
            # Log dosyalarını da temizle
            try:
                import glob
                import os
                
                # logs klasöründeki tüm .log dosyalarını bul ve sil
                log_files = glob.glob('logs/*.log')
                for log_file in log_files:
                    try:
                        os.remove(log_file)
                        logger.info(f'🗑️ Log dosyası silindi: {log_file}')
                    except Exception as e:
                        logger.error(f'❌ Log dosyası silinirken hata: {e}')
                
                # Yeni temiz log dosyası oluştur
                logger.info('🆕 Yeni log dosyası oluşturuldu')
                
            except Exception as e:
                logger.error(f'❌ Log dosyaları temizlenirken hata: {e}')
            
            # Başarı mesajı
            success_embed = discord.Embed(
                title="✅ Veriler Başarıyla Sıfırlandı!",
                description="**Tüm davet verileri, Discord davetleri ve loglar kalıcı olarak silindi:**\n\n• 🗑️ Discord sunucusundaki davetler silindi\n• 🗑️ Veritabanı temizlendi\n• 🗑️ Davet kodları temizlendi\n• 🗑️ Davet edilen kullanıcılar silindi\n• 🗑️ Şüpheli aktivite kayıtları silindi\n• 🗑️ Bot koruma kayıtları silindi\n• 🗑️ Ticket sistemi kurulumu (kategori, destek rolü, log kanalı) silindi\n• 🗑️ Tüm ticket'lar silindi\n• 🗑️ Ticket günlük sayıları silindi\n• 🗑️ Log dosyaları temizlendi\n\n**Sunucu artık tamamen temiz bir başlangıç yapabilir!**",
                color=0x57F287,  # Yeşil
                timestamp=datetime.now()
            )
            success_embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
            success_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)
            
        except asyncio.TimeoutError:
            # Timeout olursa
            timeout_embed = discord.Embed(
                title="⏰ Zaman Aşımı",
                description="30 saniye içinde onay verilmediği için işlem iptal edildi.",
                color=0xFF6B6B,
                timestamp=datetime.now()
            )
            timeout_embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
            await interaction.followup.send(embed=timeout_embed, ephemeral=True)
            
    except Exception as e:
        logger.error(f'❌ Reset komutu hatası: {e}')
        error_embed = discord.Embed(
            title="❌ Hata",
            description="Veriler sıfırlanırken bir hata oluştu!",
            color=0xED4245,
            timestamp=datetime.now()
        )
        error_embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        try:
            await interaction.followup.send(embed=error_embed, ephemeral=True)
        except:
            await interaction.channel.send(embed=error_embed, delete_after=10.0)

@bot.tree.command(name="ticket-setup", description="Ticket sistemi kurulumu yapar (Sadece Yönetici)")
async def ticket_setup_command(interaction: discord.Interaction, category: discord.CategoryChannel, support_role: discord.Role, log_channel: discord.TextChannel):
    """Ticket sistemi kurulumu"""
    # Sadece Yönetici (Administrator) yetkisi kontrol et
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Yetki Hatası",
            description="Bu komutu kullanmak için **Yönetici (Administrator)** yetkisine sahip olmalısın!",
            color=0xED4245,
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        # Ticket konfigürasyonunu kaydet (log kanalı ile)
        save_ticket_config(interaction.guild.id, category.id, support_role.id, 5, log_channel.id)
        
        embed = discord.Embed(
            title="✅ Ticket Sistemi Kuruldu",
            description=f"**Kategori:** {category.mention}\n**Destek Rolü:** {support_role.mention}\n**Log Kanalı:** {log_channel.mention}\n**Günlük Limit:** 5 ticket\n\nArtık `/ticket-panel` komutu ile ticket paneli oluşturabilirsiniz!",
            color=0x57F287,
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and bot.user.avatar.url else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f'❌ Ticket setup hatası: {e}')
        embed = discord.Embed(
            title="❌ Hata",
            description="Ticket sistemi kurulurken bir hata oluştu!",
            color=0xED4245,
            timestamp=datetime.now()
        )
        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except:
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass  # Sessizce geç, log spam yapma

@bot.tree.command(name="ticket-panel", description="Ticket paneli oluşturur (Sadece Yönetici)")
async def ticket_panel_command(interaction: discord.Interaction):
    """Ticket paneli oluşturur"""
    # Sadece Yönetici (Administrator) yetkisi kontrol et
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Yetki Hatası",
            description="Bu komutu kullanmak için **Yönetici (Administrator)** yetkisine sahip olmalısın!",
            color=0xED4245,
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        # Ticket konfigürasyonunu kontrol et
        config = get_ticket_config(interaction.guild.id)
        if not config:
            embed = discord.Embed(
                title="❌ Hata",
                description="Önce `/ticket-setup` komutunu kullanın!",
                color=0xED4245,
                timestamp=datetime.now()
            )
            embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎫 Destek Sistemi",
            description="Aşağıdaki kategorilerden birini seçerek ticket açabilirsiniz.",
            color=0xFFD700,  # Altın rengi
            timestamp=datetime.now()
        )
        
        # Ana resim (büyük resim ortada)
        embed.set_image(url="https://cdn.discordapp.com/attachments/1405597411606270142/1406059134549233695/Untitled_design_1.png?ex=68a5b35c&is=68a461dc&hm=8d635c79cf83614e89533cadfae4d9a594b993a3b407325d738c6236452f4727&")
        
        # Küçük resim (sağ üst köşede)
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1405597411606270142/1406059008372113409/nexusrp_1.png?ex=68a5b33e&is=68a461be&hm=e04a649e91ce85bc5d0c30ed3d4d1f0081d477db3a1e8a967d705016b11f4d9a&")
        
        # Kurallar
        embed.add_field(
            name="📋 Kurallar",
            value="Ticket açmadan önce sunucu kurallarını okuduğunuzdan emin olun.",
            inline=True
        )
        
        embed.add_field(
            name="⏰ Günlük Limit",
            value="Günde maksimum 5 ticket açabilirsiniz.",
            inline=True
        )
        
        embed.add_field(
            name="ℹ️ Bilgi",
            value="Ticket açtıktan sonra destek ekibimiz size yardımcı olacaktır.",
            inline=True
        )
        

        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        
        # Kategorili select menü (kapatma butonu yok, sadece ticket açma)
        try:
            view = TicketCategoryView(TICKET_CATEGORIES)
            logger.info("Ticket panel view oluşturuldu")
            
            # Ana mesajı gönder (persistent view ile)
            await interaction.response.send_message(embed=embed, view=view)
            logger.info("Ticket panel view mesajı gönderildi")
            
            # View'ı persistent yap
            try:
                await view.wait()
                logger.info("Ticket panel view tamamlandı")
            except Exception as e:
                logger.error(f"Ticket panel view wait hatası: {e}")
        except Exception as e:
            logger.error(f"Ticket panel view oluşturma hatası: {e}")
            # Hata durumunda view olmadan gönder
            await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f'❌ Ticket panel hatası: {e}')
        # Hata durumunda followup kullan
        try:
            error_embed = discord.Embed(
                title="❌ Hata",
                description="Ticket paneli oluşturulurken bir hata oluştu!",
                color=0xED4245,
                timestamp=datetime.now()
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
        except:
            # Eğer followup da çalışmazsa, yeni mesaj gönder
            error_embed = discord.Embed(
                title="❌ Hata",
                description="Ticket paneli oluşturulamadı! Lütfen tekrar deneyin.",
                color=0xED4245,
                timestamp=datetime.now()
            )
            await interaction.channel.send(embed=error_embed, delete_after=10.0)

@bot.tree.command(name="close", description="Bu kanalın ticket'ını kapatır (Sadece Yönetici)")
async def close_ticket_command(interaction: discord.Interaction):
    """Bu kanalın ticket'ını kapatır - Sadece yöneticiler kullanabilir"""
    # Yetki kontrolü: Yönetici (Administrator) yetkisi VEYA belirli rollere sahip kullanıcılar
    allowed_role_ids = [
        1407456265713745930, 1407456264325435442, 1407456263360614571, 
        1407456262362501240, 1407456261003411529, 1407456260214882505, 
        1407456259241676850, 1407456258210005113, 1407456257073352774, 
        1407456256003670137, 1407456254280073217, 1407456252690432082, 
        1407456250953732319
    ]
    
    # Kullanıcının rollerini kontrol et
    user_has_allowed_role = any(role.id in allowed_role_ids for role in interaction.user.roles)
    
    if not (interaction.user.guild_permissions.administrator or user_has_allowed_role):
        embed = discord.Embed(
            title="❌ Yetki Hatası",
            description="Bu komutu kullanmak için **Yönetici (Administrator)** yetkisine sahip olmalısın!",
            color=0xED4245,
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        
        # Bu kanalın ticket olup olmadığını kontrol et
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM tickets 
            WHERE guild_id = ? AND channel_id = ? AND status = 'open'
        ''', (guild_id, channel_id))
        
        ticket_data = cursor.fetchone()
        conn.close()
        
        if not ticket_data:
            embed = discord.Embed(
                title="❌ Hata",
                description="Bu kanal bir ticket kanalı değil veya ticket zaten kapatılmış!",
                color=0xED4245,
                timestamp=datetime.now()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Ticket bilgilerini al
        active_ticket = {
            'id': ticket_data[0],
            'guild_id': ticket_data[1],
            'ticket_number': ticket_data[2],
            'user_id': ticket_data[3],
            'channel_id': ticket_data[4],
            'category_id': ticket_data[5],
            'category_name': ticket_data[6],
            'status': ticket_data[7],
            'created_at': ticket_data[8]
        }
        
        # Ticket'ı kapat
        close_ticket(active_ticket['id'], interaction.user.id)
        
        # Kanalı sil
        channel = interaction.guild.get_channel(active_ticket['channel_id'])
        if channel:
            try:
                await channel.delete()
            except discord.Forbidden:
                pass
        
        # Ticket panelini yenile (eğer ticket kanalında ise)
        try:
            # Ticket panel mesajını bul ve yenile
            async for message in interaction.channel.history(limit=50):
                if message.author == bot.user and message.embeds:
                    for embed in message.embeds:
                        if "🎫 Destek Sistemi" in embed.title:
                            # Panel mesajını yenile
                            new_embed = discord.Embed(
                                title="🎫 Destek Sistemi",
                                description="Aşağıdaki kategorilerden birini seçerek ticket açabilirsiniz.",
                                color=0xFFD700,
                                timestamp=datetime.now()
                            )
                            
                            # Ana resim ve thumbnail
                            new_embed.set_image(url="https://cdn.discordapp.com/attachments/1405597411606270142/1406059134549233695/Untitled_design_1.png?ex=68a5b35c&is=68a461dc&hm=8d635c79cf83614e89533cadfae4d9a594b993a3b407325d738c6236452f4727&")
                            new_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1405597411606270142/1406059008372113409/nexusrp_1.png?ex=68a5b33e&is=68a461be&hm=e04a649e91ce85bc5d0c30ed3d4d1f0081d477db3a1e8a967d705016b11f4d9a&")
                            
                            # Kurallar
                            new_embed.add_field(
                                name="📋 Kurallar",
                                value="Ticket açmadan önce sunucu kurallarını okuduğunuzdan emin olun.",
                                inline=True
                            )
                            
                            # Günlük limit (güncellenmiş)
                            new_embed.add_field(
                                name="⏰ Günlük Limit",
                                value="Günde maksimum 5 ticket açabilirsiniz.",
                                inline=True
                            )
                            
                            # Bilgi
                            new_embed.add_field(
                                name="ℹ️ Bilgi",
                                value="Ticket açtıktan sonra destek ekibimiz size yardımcı olacaktır.",
                                inline=True
                            )
                            
                            
                            
                            new_embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
                            
                            # View'ı yeniden oluştur
                            view = TicketCategoryView(TICKET_CATEGORIES)
                            
                            # Mesajı güncelle
                            await message.edit(embed=new_embed, view=view)
                            logger.info(f'🔄 Ticket panel yenilendi: {interaction.channel.name}')
                            break
        except Exception as e:
            # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
            if not any(error_type in str(e) for error_type in [
                'Interaction has already been acknowledged',
                'Unknown Channel',
                '404 Not Found',
                'error code: 40060',
                'error code: 10003',
                'error code: 10062',
                'Unknown interaction'
            ]):
                logger.error(f'❌ Panel yenileme hatası: {e}')
        
        # Ticket kapatma logunu gönder
        await log_ticket_activity(guild_id, "Kapatıldı", active_ticket['ticket_number'], active_ticket['user_id'], active_ticket['channel_id'], f"Kapatıldı: {interaction.user.display_name}")
        
        embed = discord.Embed(
            title="🔒 Ticket Kapatıldı",
            description=f"Ticket #{active_ticket['ticket_number']} yönetici tarafından kapatıldı.\n\n**Oluşturulma:** {active_ticket['created_at'][:10]}\n**Kapatılma:** {datetime.now().strftime('%d/%m/%Y %H:%M')}\n**Kapatan:** {interaction.user.display_name}",
            color=0xFFA500,  # Turuncu
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f'❌ Ticket kapatma hatası: {e}')
        
        # Hata mesajını sessizce gönder, log spam yapma
        try:
            embed = discord.Embed(
                title="❌ Hata",
                description="Ticket kapatılırken bir hata oluştu!",
                color=0xED4245,
                timestamp=datetime.now()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            try:
                await interaction.channel.send(embed=embed, delete_after=10.0)
            except:
                pass  # Sessizce geç, log spam yapma

@bot.tree.command(name="ticket-stats", description="Ticket istatistiklerini gösterir")
async def ticket_stats_command(interaction: discord.Interaction):
    """Ticket istatistiklerini gösterir"""
    try:
        guild_id = interaction.guild.id
        
        # Ticket konfigürasyonunu kontrol et
        config = get_ticket_config(guild_id)
        if not config:
            embed = discord.Embed(
                title="❌ Hata",
                description="Ticket sistemi kurulmamış!",
                color=0xED4245,
                timestamp=datetime.now()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Veritabanından istatistikleri al
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        # Aktif ticket sayısı
        cursor.execute('SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = "open"', (guild_id,))
        active_count = cursor.fetchone()[0]
        
        # Toplam ticket sayısı
        cursor.execute('SELECT COUNT(*) FROM tickets WHERE guild_id = ?', (guild_id,))
        total_count = cursor.fetchone()[0]
        
        conn.close()
        
        embed = discord.Embed(
            title="📊 Ticket İstatistikleri",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        embed.add_field(name="🎫 Aktif Ticket", value=active_count, inline=True)
        embed.add_field(name="📈 Toplam Oluşturulan", value=total_count, inline=True)
        embed.add_field(name="🔒 Kapatılan", value=total_count - active_count, inline=True)
        embed.add_field(name="⏰ Günlük Limit", value=f"{config['daily_limit']} ticket", inline=True)
        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f'❌ Ticket stats hatası: {e}')
        embed = discord.Embed(
            title="❌ Hata",
            description="Ticket istatistikleri alınırken bir hata oluştu!",
            color=0xED4245,
            timestamp=datetime.now()
        )
        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except:
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass  # Sessizce geç, log spam yapma

@bot.event
async def on_interaction(interaction):
    """Button interaction'ları yakalar"""
    if interaction.type == discord.InteractionType.component:
        try:
            logger.info(f"Component interaction detected: type={interaction.type}")
            logger.info(f"Interaction data type: {type(interaction.data)}")
            logger.info(f"Interaction data: {interaction.data}")
            
            # Discord.py versiyonuna göre custom_id'yi al
            custom_id = None
            if hasattr(interaction, 'custom_id'):
                custom_id = interaction.custom_id
                logger.info(f"Direct custom_id: {custom_id}")
            elif hasattr(interaction, 'data') and hasattr(interaction.data, 'custom_id'):
                custom_id = interaction.data.custom_id
                logger.info(f"Data.custom_id: {custom_id}")
            elif hasattr(interaction, 'data') and isinstance(interaction.data, dict) and 'custom_id' in interaction.data:
                custom_id = interaction.data['custom_id']
                logger.info(f"Data dict custom_id: {custom_id}")
            
            logger.info(f"Final custom_id: {custom_id}")
            
            if custom_id == "ticket_category_select":
                logger.info("Ticket category select detected, this should be handled by the view")
                # Bu zaten TicketCategorySelect.callback() tarafından handle ediliyor
                # Global handler'da işlemiyoruz, view'a bırakıyoruz
                return
            else:
                logger.info(f"Unknown custom_id: {custom_id}")
        except Exception as e:
            # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
            if not any(error_type in str(e) for error_type in [
                'Interaction has already been acknowledged',
                'Unknown Channel',
                '404 Not Found',
                'error code: 40060',
                'error code: 10003',
                'error code: 10062',
                'Unknown interaction'
            ]):
                logger.error(f"Button interaction hatası: {e}")
                logger.error(f"Interaction type: {interaction.type}")
                logger.error(f"Interaction data: {getattr(interaction, 'data', 'No data')}")
                logger.error(f"Interaction attributes: {dir(interaction)}")
                logger.error(f"Exception type: {type(e)}")
                logger.error(f"Exception args: {e.args}")

@bot.event
async def on_message(message):
    """Ticket mesajlarını loglar"""
    # Bot mesajlarını loglama
    if message.author.bot:
        return
    
    # Ticket kanalında mı kontrol et
    try:
        # Veritabanından ticket bilgisini al
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT guild_id, ticket_number, user_id 
            FROM tickets 
            WHERE channel_id = ? AND status = 'open'
        ''', (message.channel.id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            guild_id, ticket_number, user_id = result
            
            # Ticket mesajını logla
            try:
                await log_ticket_message(guild_id, ticket_number, user_id, message.channel.id, message.content)
            except Exception as e:
                # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
                if not any(error_type in str(e) for error_type in [
                    'Interaction has already been acknowledged',
                    'Unknown Channel',
                    '404 Not Found',
                    'error code: 40060',
                    'error code: 10003',
                    'error code: 10062',
                    'Unknown interaction'
                ]):
                    logger.error(f"Ticket mesaj log hatası: {e}")
            
    except Exception as e:
        # Log hatası olursa sessizce devam et
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f"Ticket mesaj kontrol hatası: {e}")
    
    # Bot komutlarını işle
    try:
        await bot.process_commands(message)
    except Exception as e:
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f"Bot komut işleme hatası: {e}")





@bot.tree.command(name="ticket-list", description="Aktif ticket'ları listeler (Sadece Yönetici)")
async def ticket_list_command(interaction: discord.Interaction):
    """Aktif ticket'ları listeler"""
    # Sadece Yönetici (Administrator) yetkisi kontrol et
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Yetki Hatası",
            description="Bu komutu kullanmak için **Yönetici (Administrator)** yetkisine sahip olmalısın!",
            color=0xED4245,
            timestamp=datetime.now()
        )
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        guild_id = interaction.guild.id
        
        # Aktif ticket'ları getir
        conn = sqlite3.connect(Config.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.*, u.display_name 
            FROM tickets t 
            LEFT JOIN (
                SELECT DISTINCT user_id, display_name 
                FROM (
                    SELECT user_id, display_name, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) as rn
                    FROM tickets
                ) ranked 
                WHERE rn = 1
            ) u ON t.user_id = u.user_id
            WHERE t.guild_id = ? AND t.status = 'open'
            ORDER BY t.created_at DESC
        ''', (guild_id,))
        
        active_tickets = cursor.fetchall()
        conn.close()
        
        if not active_tickets:
            embed = discord.Embed(
                title="📝 Aktif Ticket'lar",
                description="Aktif ticket bulunamadı.",
                color=0x5865F2,
                timestamp=datetime.now()
            )
            embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📝 Aktif Ticket'lar",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        for ticket in active_tickets:
            user_name = ticket[8] if ticket[8] else "Bilinmeyen Kullanıcı"
            created_at = datetime.fromisoformat(ticket[7]) if ticket[7] else datetime.now()
            
            embed.add_field(
                name=f"🎫 Ticket #{ticket[2]}",
                value=f"**Kullanıcı:** {user_name}\n**Kategori:** {ticket[6]}\n**Oluşturulma:** {created_at.strftime('%d/%m/%Y %H:%M')}\n**Durum:** {ticket[7]}",
                inline=False
            )
        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar and interaction.user.avatar.url else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        # Sadece gerçek hataları logla, Discord interaction hatalarını loglama
        if not any(error_type in str(e) for error_type in [
            'Interaction has already been acknowledged',
            'Unknown Channel',
            '404 Not Found',
            'error code: 40060',
            'error code: 10003',
            'error code: 10062',
            'Unknown interaction'
        ]):
            logger.error(f'❌ Ticket list hatası: {e}')
        embed = discord.Embed(
            title="❌ Hata",
            description="Ticket listesi alınırken bir hata oluştu!",
            color=0xED4245,
            timestamp=datetime.now()
        )
        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except:
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass  # Sessizce geç, log spam yapma



# Ticket Log Sistemi
async def log_ticket_activity(guild_id, action, ticket_number, user_id, channel_id, details=""):
    """Ticket aktivitelerini log kanalına gönderir"""
    try:
        config = get_ticket_config(guild_id)
        if not config or not config.get('log_channel_id'):
            logger.debug(f"Log kanalı bulunamadı: guild_id={guild_id}")
            return
        
        log_channel = bot.get_channel(config['log_channel_id'])
        if not log_channel:
            logger.warning(f"Log kanalı bulunamadı: {config['log_channel_id']}")
            return
        
        # Kullanıcı bilgisini al
        try:
            user = await bot.fetch_user(user_id)
            user_name = user.display_name if user else f"ID: {user_id}"
        except Exception as e:
            logger.error(f"Kullanıcı bilgisi alınamadı: {e}")
            user_name = f"ID: {user_id}"
        
        # Log embed'i oluştur
        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_number} - {action}",
            description=f"**Kullanıcı:** {user_name} ({user_id})\n**Kanal:** <#{channel_id}>\n**Detay:** {details}",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        
        await log_channel.send(embed=embed)
        logger.info(f"Ticket log gönderildi: #{ticket_number} - {action}")
        
    except Exception as e:
        logger.error(f"❌ Ticket log hatası: {e}")
        logger.error(f"Log detayları: guild_id={guild_id}, action={action}, ticket_number={ticket_number}")

async def log_ticket_message(guild_id, ticket_number, user_id, channel_id, message_content):
    """Ticket mesajlarını log kanalına gönderir"""
    try:
        config = get_ticket_config(guild_id)
        if not config or not config.get('log_channel_id'):
            return
        
        log_channel = bot.get_channel(config['log_channel_id'])
        if not log_channel:
            return
        
        # Kullanıcı bilgisini al
        try:
            user = await bot.fetch_user(user_id)
            user_name = user.display_name if user else f"ID: {user_id}"
        except Exception as e:
            logger.error(f"Mesaj log için kullanıcı bilgisi alınamadı: {e}")
            user_name = f"ID: {user_id}"
        
        # Mesaj embed'i oluştur
        embed = discord.Embed(
            title=f"💬 Ticket #{ticket_number} - Yeni Mesaj",
            description=f"**Kullanıcı:** {user_name} ({user_id})\n**Kanal:** <#{channel_id}>\n\n**Mesaj:**\n{message_content[:1000]}{'...' if len(message_content) > 1000 else ''}",
            color=0x57F287,
            timestamp=datetime.now()
        )
        
        embed.set_footer(text=Config.BOT_NAME, icon_url=bot.user.avatar.url if bot.user.avatar and bot.user.avatar.url else None)
        
        await log_channel.send(embed=embed)
        logger.debug(f"Ticket mesaj log gönderildi: #{ticket_number}")
        
    except Exception as e:
        logger.error(f"❌ Ticket mesaj log hatası: {e}")
        logger.error(f"Mesaj log detayları: guild_id={guild_id}, ticket_number={ticket_number}")

# Bot'u çalıştır
if __name__ == '__main__':
    bot.run(Config.DISCORD_TOKEN)