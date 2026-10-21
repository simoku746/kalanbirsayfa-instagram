# kalanbirsayfa · Instagram paylaşım sırası

`queue/` klasöründeki Reels'ler, `post.json` içindeki tarih ve saatte (Türkiye saati) GitHub Actions ile @kalanbirsayfa hesabına paylaşılır.
Paylaşılan gönderi `posted/` klasörüne taşınır ve videosu depodan kaldırılır.

Gizli ayarlar (Settings → Secrets and variables → Actions): `IG_TOKEN`, `IG_USER_ID`.
