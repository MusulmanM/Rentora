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

The project includes Django/DRF integration tests in `core/tests.py`. They cover the main page, three-language selector, listing filters/details and localized API fields, registration, booking totals, date conflicts, cancellation permissions, and API access. The test runner was invoked, but it **could not start** in this build environment because Django is not installed (`ModuleNotFoundError: No module named 'django'`). Installing dependencies is not possible from this environment due to package-index network restrictions. Therefore the Django integration tests are **not reported as passed**.

On a machine with package-index access, from the project folder run:

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py test core
```
