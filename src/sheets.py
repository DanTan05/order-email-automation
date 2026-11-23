import gspread
import pandas as pd

def write_tab(sheet_id: str, tab_name: str, df: pd.DataFrame) -> None:
    gc = gspread.service_account(filename="credentials/service_account.json")
    spreadsheet = gc.open_by_key(sheet_id)

    try:
        worksheet = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=30)

    worksheet.clear()
    safe = df.astype(object).where(df.notna(), "")
    rows = [safe.columns.tolist()] + safe.values.tolist()
    worksheet.update(range_name="A1", values=rows)