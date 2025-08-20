# InviteManager Bot

Modern Discord davet sistemi ile sunucunuzu buyutun! Bu bot, kullanıcıların davet kodları olusturmasına ve davet istatistiklerini takip etmesine olanak sağlar.

## Ozellikler

- Button Arayuzu: Modern Discord button sistemi
- Detaylı İstatistikler: Sunucu ve kullanıcı bilgileri
- Davet Sıralaması: Kim daha cok davet ettiğini görün ve yarışın!
- Güvenlik: Kendini davet etme ve tekrar davet olma engellendi
- Veritabanı: SQLite ile güvenli veri saklama
- Profesyonel Arayuz: Discord'un resmi renkleri ile modern embed'lar
- Kolay Kullanım: Tek komut ile tüm özelliklere erişim

## Kurulum

### 1. Gereksinimler
- Python 3.8 veya üzeri
- Discord Developer Portal'da bot hesabı

### 2. Paketleri Yükleyin
```bash
pip install -r requirements.txt
```

### 3. Bot Token'ını Ayarlayın
1. `env_example.txt` dosyasını `.env` olarak kopyalayın
2. Discord Developer Portal'dan bot token'ınızı alın
3. `.env` dosyasında `DISCORD_TOKEN` değerini güncelleyin

### 4. Botu Çalıştırın
```bash
python bot.py
```

## Komutlar

| Komut | Açıklama |
|-------|----------|
| `/invite` | Sunucu için davet linki oluşturur |
| `/stats` | Oluşturduğun davet istatistiklerini gösterir |
| `/leaderboard` | Davet sıralamasını gösterir |
| `/adminstats` | Sunucudaki tüm davet istatistikleri (Sadece Yönetici) |
| `/suspicious` | Şüpheli davet aktivitelerini gösterir (Sadece Yönetici) |
| `/reset` | Tüm davet verilerini sıfırlar (Sadece Yönetici) |
| `/help` | Yardım menüsünü gösterir |

## Bot Ayarları

Bot'u Discord Developer Portal'da kurarken şu izinleri verin:
- **Message Content Intent**: ✅ Açık
- **Server Members Intent**: ✅ Açık
- **Bot Permissions**: 
  - Send Messages
  - Embed Links
  - Read Message History
  - Manage Server (Davet takibi için)

## Veritabanı Yapısı

### invite_codes Tablosu
- `code`: Davet kodu (PRIMARY KEY)
- `user_id`: Kod sahibinin Discord ID'si (UNIQUE - her kullanıcı sadece 1 link)
- `created_at`: Kod oluşturulma tarihi
- `uses`: Kodun kullanım sayısı

### invited_users Tablosu
- `id`: Otomatik artan ID
- `inviter_id`: Davet eden kullanıcının ID'si
- `invited_user_id`: Davet edilen kullanıcının ID'si (UNIQUE)
- `invited_at`: Davet tarihi
- `invite_code`: Kullanılan davet kodu

### suspicious_invites Tablosu
- `id`: Otomatik artan ID
- `inviter_id`: Şüpheli davet yapan kullanıcının ID'si
- `invite_count`: Şüpheli aktivite sayısı
- `first_invite_at`: İlk şüpheli aktivite tarihi
- `last_invite_at`: Son şüpheli aktivite tarihi

### bot_protection Tablosu
- `id`: Otomatik artan ID
- `user_id`: Bot olarak tespit edilen kullanıcının ID'si
- `is_bot`: Bot olup olmadığı (BOOLEAN)
- `detected_at`: Tespit tarihi

## Güvenlik Özellikleri

### Fake Davet Koruması
- **Tek Davet Linki**: Her kullanıcı sadece 1 adet sınırsız davet linki oluşturabilir
- Bot Koruması: Botlar davet edildiğinde sayılmaz ve tespit edilir
- Tekrar Davet Koruması: Aynı kullanıcı birden fazla kez davet edilemez
- Anti-Spam Koruması: Kısa sürede çok fazla davet yapılması engellenir
- Şüpheli Aktivite Tespiti: Anormal davet aktiviteleri otomatik tespit edilir

### Güvenlik Ayarları
- Saatte Maksimum Davet: 20 kişi
- Günde Maksimum Davet: 100 kişi
- Bot Koruması: Aktif
- Şüpheli Aktivite Loglaması: Aktif

### Şüpheli Aktivite Uyarıları
- Çok hızlı davet yapan kullanıcılar uyarılır
- Şüpheli aktiviteler otomatik loglanır
- Admin'ler `/suspicious` komutu ile takip edebilir

## Kullanım Senaryoları

1. Davet Linki Oluşturma: `/invite` komutu ile sunucu için davet linki oluştur
2. İstatistik Takibi: `/stats` komutu ile kendi davet istatistiklerini gör
3. Sıralama: `/leaderboard` komutu ile en çok davet edenleri gör
4. Admin Kontrolü: `/adminstats` ve `/suspicious` komutları ile sunucu güvenliğini takip et
5. Güvenlik: Bot otomatik olarak fake davetleri engeller ve şüpheli aktiviteleri tespit eder

## Tasarım Özellikleri

- Discord Resmi Renkleri: Mavi (#5865F2), Yeşil (#57F287), Kırmızı (#ED4245)
- Profesyonel Embed'lar: Timestamp, footer ve author bilgileri
- Modern İkonlar: Her komut için uygun emoji'ler
- Responsive Tasarım: Mobil ve masaüstü uyumlu

## Sorun Giderme

### Bot çalışmıyor
- Discord token'ının doğru olduğundan emin olun
- Bot'un sunucuda olduğundan emin olun
- Gerekli izinlerin verildiğinden emin olun

### Komutlar çalışmıyor
- Bot'un mesaj okuma izninin olduğundan emin olun
- Button'ların düzgün yüklendiğinden emin olun
- Bot'un gerekli izinlere sahip olduğundan emin olun

## Lisans

Bu proje MIT lisansı altında lisanslanmıştır.

## Geliştirici

**Mustafa** tarafından geliştirilmiştir.

## Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/AmazingFeature`)
3. Commit yapın (`git commit -m 'Add some AmazingFeature'`)
4. Push yapın (`git push origin feature/AmazingFeature`)
5. Pull Request oluşturun

## Destek

Herhangi bir sorun yaşarsanız, GitHub Issues bölümünde bildirin.
