# Rentora test report

## Checks completed in this build environment

- Python source syntax (`ast.parse` / `compileall`): **PASS**
- Main frontend JavaScript syntax (`node --check`): **PASS**
- Localization JavaScript syntax (`node --check`): **PASS**
- Uzbek/Russian/English translation-helper smoke tests: **PASS**
- Template block balance: **PASS**
- HTML tag-stack audit for templates: **PASS**
- Template `{% url %}` references matched with URL routes: **PASS**
- Language selector includes `UZ`, `RU`, and `EN`: **PASS**
- Translation fields present in listing model, migration, admin, seed data and API serializer: **PASS** (static consistency check)
- Required files and migration files exist: **PASS**
- ZIP archive integrity: checked after packaging.

## Django runtime tests

`python manage.py test core`: **PASS** (25 tests). Coverage includes guest/access behavior, cash booking creation, automatic online checkout without admin approval, reservation conflicts, Click callbacks, Payme Merchant API callbacks, and the booking/API flows.

Provider credentials are not present in this environment, so live Click and Payme transactions are not exercised. Configure sandbox merchant credentials and callback URLs before attempting provider end-to-end tests. From the project folder run:

```bash
python manage.py migrate
python manage.py seed_demo
python manage.py test core
```
