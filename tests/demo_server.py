"""Offline UI fixture. Never used by app.py and never calls Gemini."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from config import Settings


class DemoTutor:
    def reply(self, message, history, detail):
        time.sleep(0.35)
        if 'uji html' in message.lower():
            return '<script>window.xss=1</script><img src=x onerror="window.xss=2">\n\n[tautan](javascript:alert(1))\n\n**Teks aman**'
        if 'latihan' in message.lower():
            return '### Coba satu latihan\n\nKamu punya list `nilai = [70, 85, 90]`.\n\n**Bagaimana cara menghitung rata-ratanya?** Tulis kode versimu, nanti kita bahas bersama.'
        if history:
            return 'Betul, kita masih membahas **list dan dictionary**.\n\nGunakan list untuk urutan nilai; dictionary untuk pasangan kunci dan nilai.\n\n```python\nsiswa = {"nama": "Rani", "nilai": [80, 90]}\nprint(siswa["nilai"][0])  # 80\n```\n\nKode ini contoh penjelasan, belum dieksekusi oleh aplikasi.'
        return '''### Dua cara menyimpan data

**List** menyimpan nilai secara berurutan. Kamu mengambil isinya memakai posisi (indeks), dimulai dari `0`.

```python
nilai = [80, 90, 75]
print(nilai[0])  # 80
```

**Dictionary** menyimpan pasangan kunci dan nilai. Kamu mengambil isinya memakai nama kuncinya.

```python
mahasiswa = {"nama": "Rani", "nilai": 90}
print(mahasiswa["nama"])  # Rani
```

Pakai **list** untuk kumpulan nilai. Pakai **dictionary** saat setiap nilai punya label.

Kalau ingin menyimpan nama dan umur satu orang, menurutmu lebih cocok yang mana?'''


if __name__ == '__main__':
    create_app(settings=Settings(api_key='offline-demo-not-a-key'), service=DemoTutor(), demo=True).run(
        host='127.0.0.1', port=5051, debug=False)
