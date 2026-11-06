# Buxoro Qorako‘l xususiy maktabi — Professional Telegram CRM

## Tizim tarkibi
- Ota-onalar uchun Telegram bot
- Ota-ona roziligi bilan murojaat yig'ish
- Telefon raqamini Telegram contact tugmasi orqali olish
- Farzandning ism-familiyasi, yoshi, sinfi va hozirgi maktabi
- Murojaat turini tanlash
- SQLite ma'lumotlar bazasiga saqlash
- Administratorning shaxsiy Telegramiga yangi murojaat bildirishnomasi
- Admin panel: yangi/barcha murojaatlar, qidiruv, statistika, CSV eksport
- Murojaat statuslarini o'zgartirish va izoh yozish
- Ota-onaga /privacy va /delete_my_data buyruqlari

## 1. Talablar
- Windows 10/11
- Python 3.13
- Telegram akkaunt

## 2. Papkani ochish
ZIP arxivni oching. PowerShell'da loyiha papkasiga o'ting:
```powershell
cd C:\Bukhara_Qorakol_Professional_CRM
```

## 3. Virtual muhit va kutubxonalar
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```
Agar PowerShell aktivlashtirish skriptini bloklasa:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 4. Bot tokeni va admin ID
1. Telegram'da @BotFather orqali bot yarating va token oling.
2. Administrator o'z Telegram akkauntining raqamli ID raqamini aniqlasin.
3. `.env.example` faylidan nusxa oling va nusxani `.env` deb nomlang.
4. `.env` ichiga haqiqiy BOT_TOKEN va ADMIN_ID ni yozing.
5. SCHOOL_PHONE va SCHOOL_ADDRESS qiymatlarini maktabning tasdiqlangan ma'lumotlari bilan almashtiring.

**Token maxfiy:** uni hech kimga yubormang, skrinshotda ko'rsatmang va internetga joylamang.

## 5. Administrator botni ishga tushirishi shart
Administrator botga shaxsiy akkauntidan kirib, avval `/start` yuborsin. Telegram bot foydalanuvchi bilan suhbatni foydalanuvchi boshlamaguncha o'zi boshlay olmaydi.

## 6. Ishga tushirish
```powershell
python main.py
```
Terminal ochiq turgan va kompyuter internetga ulangan paytda bot ishlaydi. 24/7 xizmat uchun keyinchalik serverga joylashtirish mumkin.

## 7. Admin buyruqlari
- `/admin` — admin bosh menyusi
- `/new` — yangi murojaatlar
- `/leads` — oxirgi murojaatlar
- `/stats` — statistika
- `/search` — ota-ona/farzand/telefon bo'yicha qidirish
- `/lead 12` — 12-raqamli murojaat kartochkasi
- `/export` — barcha murojaatlarni CSV formatida yuklab olish
- `/cancel` — joriy amalni bekor qilish

Admin faqat `.env` dagi ADMIN_ID bilan belgilanadi. Boshqa foydalanuvchilar admin buyruqlaridan foydalana olmaydi.

## 8. Ota-ona buyruqlari
- `/start` — murojaatni boshlash
- `/cancel` — jarayonni bekor qilish
- `/privacy` — ma'lumotlardan foydalanish haqida
- `/delete_my_data` — shu Telegram ID ga tegishli murojaat yozuvlarini o'chirish

## 9. Ma'lumotlar bazasi
Birinchi versiya SQLite ishlatadi. Bot birinchi ishga tushganda `school_crm.db` fayli avtomatik yaratiladi. PostgreSQL serverini hozircha o'rnatish shart emas. Bazani muntazam zaxiralab boring.

## 10. Muhim sozlashlar
- Qabul sinflari `.env` dagi `GRADES` orqali boshqariladi.
- Maktab manzili va telefonini `.env` da to'ldiring.
- Kontrakt summasi yoki aniq dars jadvali kabi tasdiqlanmagan ma'lumotlar botda uydirib ko'rsatilmaydi; ota-ona murojaat qoldiradi, administrator aniqlashtiradi.
- Ma'lumotlarni faqat murojaatni ko'rib chiqish uchun ishlating. Saqlash muddati, kirish huquqi va o'chirish tartibini maktab rahbariyati bilan kelishib oling.
- Bu versiya bitta administratorga mo'ljallangan.
- Admin status tugmalari murojaat kartochkasini yangilaydi. Statuslar: Yangi, Bog'lanildi, Tashrif belgilandi, Hujjat topshirdi, Qabul qilindi, Qabul qilinmadi, Qayta bog'lanish kerak.

## 11. Birinchi sinov
1. Administrator botga `/start` yuboradi.
2. Botni boshqa Telegram akkauntdan ochib, `/start` yuboring.
3. Rozilik bering va savollarga javob bering.
4. Admin akkauntiga yangi murojaat xabari kelishini tekshiring.
5. Admin xabaridagi status tugmasini bosing.
6. `/stats` va `/export` buyruqlarini tekshiring.
