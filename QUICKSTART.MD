# Quick Start

```bash
python3 -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py seed_full
python manage.py seed_portal
python manage.py createsuperuser
python manage.py runserver
```

- Site: http://127.0.0.1:8000/  · Sign Up: /accounts/signup/  · Login: /accounts/login/
- Admin: http://127.0.0.1:8000/admin/

**Note upload:** Admin → Resources → Add → Class → Faculty → Subject → (Chapter) → file/link.
Tyo class/faculty ma gayepachi note subject-wise dekhincha.

Details: `README.md`
