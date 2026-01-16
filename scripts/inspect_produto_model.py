"""Inspect SQLAlchemy mapping for Produto model.

Run from backend folder:
    py -3 scripts\inspect_produto_model.py

This prints the table name and mapped column names and actual DB column names
as SQLAlchemy sees them. Useful to debug mismatches between model and DB.
"""
import os
import sys

# ensure package import works
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.models.product import Produto


def main():
    t = Produto.__table__
    print(f"Table: {t.name}")
    for col in t.columns:
        print(f"- key={col.key} | name={col.name} | type={col.type}")


if __name__ == '__main__':
    main()
