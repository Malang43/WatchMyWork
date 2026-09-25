"""Generate fake demo data only; never reads user spreadsheets or .env."""
import csv
from pathlib import Path
from openpyxl import Workbook

root = Path(__file__).resolve().parents[1] / 'sample-data'
root.mkdir(exist_ok=True)
ids = ['PK100001', 'PK100002', 'PK100003', 'PK100004', 'PK100005', 'PK100006', 'PK100007', 'PK100008', 'PK100001', 'PK100002', '', 'INVALID-ID', 'PK100009', 'PK100010', 'PK100003', 'pk100004', ' PK100001 ', 'PK999999', 'PK100011', 'PK100005']
rows = [['Tracking ID', 'Status', 'Reference']] + [[value, '', f'DEMO-{i:03}'] for i, value in enumerate(ids, 1)]
book = Workbook()
sheet = book.active
sheet.title = 'Tracking demo'
for row in rows:
    sheet.append(row)
sheet.freeze_panes = 'A2'
for column in ['A', 'B', 'C']:
    sheet.column_dimensions[column].width = 22
book.save(root / 'tracking-demo.xlsx')
with (root / 'tracking-demo.csv').open('w', encoding='utf-8-sig', newline='') as out:
    csv.writer(out).writerows(rows)
print('Created 20 fake records in sample-data/tracking-demo.xlsx and .csv')
