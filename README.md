MoneyToFlows - Deployra-ready package

Included files:
- app.py (Flask application)
- templates/ (site pages)
- static/ (CSS)
- requirements.txt
- Procfile
- Dockerfile

Quick deploy notes:
- Set env var PORT=3000 in Deployra (or let Deployra set it)
- Set ADMIN_EMAIL, ADMIN_PASSWORD, SUPPORT_EMAIL, SECRET_KEY, ACHAT_LINK if desired
- After deploy, visit /init to initialize DB and create admin user
