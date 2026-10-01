# Daybook

Tarayıcıda çalışan günlük uygulaması. Ana uygulama `index.html` dosyasıdır; bir Python sunucusuna veya Python paketlerine ihtiyaç duymaz.

## Durum

Korunan ana günlük deposu. Eski `diary` deposuyla aynı günlük JavaScript kodunu içerir; bu depoda ek kullanım açıklaması vardır. 1 Ekim 2026 düzenlemesinde günlük uygulamasının HTML/JavaScript dosyası değiştirilmemiştir.

## Başlatma

`index.html` dosyasını modern bir tarayıcıda açabilirsiniz. Yerel sunucu kullanmak isterseniz depo klasöründe:

```bash
python3 -m http.server 8000 --bind 127.0.0.1
```

Ardından `http://127.0.0.1:8000` adresini açın. Python burada yalnızca isteğe bağlı bir dosya sunucusudur.

## Kullanım

1. İlk açılışta kullanıcı adı ve en az altı karakterlik parola oluşturun.
2. **New Entry** ile başlık ve günlük metni ekleyip kaydedin.
3. Arama, tarih, ruh hâli ve etiket filtrelerini kullanın; istediğiniz kaydı sabitleyin.
4. **Export** ile JSON yedeği alın. **Import** ile yedeği geri yükleyin.

İçe aktarma, onay verdiğinizde açık kullanıcının mevcut kayıtlarının yerini alır. Önce dışa aktararak yedek alın.

## Kayıtlar ve gizlilik

Günlükler aynı tarayıcı profili ve adres için `localStorage` içinde saklanır. Başka tarayıcıya, porta veya adrese geçmek farklı bir kayıt alanı açar. Tarayıcı verilerini temizlemek kayıtları kaldırabilir; düzenli JSON yedeği alın.

Parola kontrolü tarayıcı içinde yapılır. Parola doğrulama bilgisi PBKDF2 ile türetilir, ancak günlük metinleri şifrelenmeden saklanır. Kilit ekranı şifreli bir kasa sağlamaz. JSON yedekleri de günlük metinlerini içerir.

## Dosyalar

- `index.html`: günlük uygulaması.
- `tools/least-used-cleanup/`: ayrı bir eski Linux dosya temizleme aracı; [kendi kurulumu](tools/least-used-cleanup/README.md) vardır.
- `src/least_used_cleanup_server.py`: eski temizleme aracı başlatma yolunu koruyan yönlendirici.

Disk Avcısı'nın tekrar eden kodları ana [disk-avcisi deposunda](https://github.com/bulutax-max/disk-avcisi) korunur. Sanal ortamlar ve önbellekler kaynak koddan çıkarılmıştır; geçmiş commit'ler korunur.

## Tamamlama kontrolü

Kullanıcı oluşturma, kayıt ekleme/düzenleme, yeniden giriş, arama ve JSON dışa/içe aktarma kontrol edilmelidir. Uygulamanın kendi parola ekranı ve veri saklama sınırları yukarıda açıklanmıştır.

1 Ekim 2026: JavaScript ve Python sözdizimi kontrol edildi. Günlük HTML dosyası ile taşınan temizleme sunucusu ve şablonunun özgün Git dosya kimlikleri korundu. Bu ortamda tarayıcı motoru ve Flask kurulamadığından günlük etkileşimleri ve Flask sunucusu çalıştırılarak doğrulanmadı.
