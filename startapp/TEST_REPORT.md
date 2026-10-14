# Rentora test report

## Checks completed in this build environment

- Python source syntax (`ast.parse` / `compileall`): **PASS**
- Main frontend JavaScript syntax (`node --check`): **PASS**
- Location and photo-gallery JavaScript syntax (`node --check`): **PASS**
- Localization JavaScript syntax (`node --check`): **PASS**
- Uzbek/Russian/English translation-helper smoke tests: **PASS**
- Template block balance: **PASS**
- HTML tag-stack audit for templates: **PASS**
- Template `{% url %}` references matched with URL routes: **PASS**
- Language selector includes `UZ`, `RU`, and `EN`: **PASS**
- Translation fields present in listing model, migration, admin, seed data and API serializer: **PASS** (static consistency check)
- Required files and migration files exist: **PASS**
- Django system checks and migration consistency (`manage.py check`, `makemigrations --check --dry-run`): **PASS**
- ZIP archive integrity: checked after packaging.

## Django runtime tests

`python manage.py test core`: **PASS** (112 tests, offline: Telegram/OpenAI keys from `.env` are disabled during tests). Coverage includes the home/car-first listing form and listing editing, Telegram photo upload with text fallback, provider booking rejection, automatic listing translation, localized region/district names, Telegram long polling, guest/access behavior, Telegram OTP registration and webhook checks, unique phone profiles, dependent Uzbekistan region/district filtering, provider onboarding and listing/photo uploads, admin contact messages, gallery rendering and admin image previews, cash booking creation, automatic online checkout without admin approval, OpenAI-backed rental filtering/sorting and server-side price calculations, reservation conflicts, Click callbacks, Payme Merchant API callbacks, and the booking/API flows.

OpenAI, Click, and Payme credentials are not present in this environment, so external AI and live payment provider requests are not exercised. Configure OpenAI and sandbox merchant credentials before attempting provider end-to-end tests. From the project folder run:

```bash
python manage.py migrate
python manage.py seed_demo
python manage.py test core
```
