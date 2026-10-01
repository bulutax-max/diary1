# Least Used Cleanup

Bu klasör, günlük uygulamasından bağımsız eski Flask dosya temizleme aracını korur. Sunucu kodu ve HTML şablonu taşınırken içerikleri değiştirilmemiştir.

## Durum

Korunan deneysel araç. Geniş kapsamlı güvenlik veya dosya silme doğrulaması yapılmamıştır. Dosya yaşına göre sonuç sunar; bir dosyanın gereksiz olduğuna karar vermez.

## Ubuntu'da başlatma

Python 3.10+ ile bu klasörden:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python least_used_cleanup_server.py
```

`http://127.0.0.1:5000` adresini açın. Varsayılan bağlanma adresi yalnızca yerel bilgisayardır; aracı internete açmayın. Silme işlemleri dosyayı çöp kutusuna taşımadan kaldırır.

Depo kökünden eski `python src/least_used_cleanup_server.py` komutu da korunmuştur; aynı Python ortamında Flask kurulu olmalıdır.

## Korunan dosyalar

- `least_used_cleanup_server.py`: tarama ve Flask API.
- `webapp/templates/least_used_cleanup.html`: arayüz.

Taşımayı doğrularken şablon yükleme ve geçici örnek klasörde tarama kontrolü yapın. Gerçek kullanıcı dosyaları üzerinde otomatik silme testi çalıştırmayın.

