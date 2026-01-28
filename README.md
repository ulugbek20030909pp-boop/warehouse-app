# Warehouse Products Web App (CRUD + SQLite)

A small, ready-to-run warehouse web app:
- Add / edit / delete products
- Track stock quantity
- Track sales entries and see **last 30 days sales**
- Data is stored in a local **SQLite** database (`data/app.db`)
- Clean UI (Bootstrap) + search + sorting

## 1) Install
Create and activate a virtual environment (recommended), then:

```bash
pip install -r requirements.txt
```

## 2) Run
```bash
python app.py
```

Open:
- http://127.0.0.1:5000

## 3) Notes
- Database file is created automatically at `data/app.db` on first run.
- If you want to reset the DB, stop the server and delete `data/app.db`.

## Fields
Product:
- name
- sku
- barcode
- quantity
- image_url

Sales:
- product_id
- date
- qty_sold

## API (used by the UI)
- GET    /api/products
- POST   /api/products
- GET    /api/products/<id>
- PUT    /api/products/<id>
- DELETE /api/products/<id>

- POST   /api/products/<id>/sales
- GET    /api/products/<id>/sales?days=30

- GET    /api/summary?days=30   (sales per product for the last N days)
