import os
import gradio as gr
import pandas as pd
from connectors import PgVectorConnector


def get_docs_from_db():
    connector = PgVectorConnector()
    conn = connector.start_db_connection()

    query = f"SELECT DISTINCT title FROM {os.environ['POSTGRES_SPARSE_TABLE_NAME']} ORDER BY title;"
    with conn.cursor() as cur:
        cur.execute(query)
        result = cur.fetchall()

    connector.close_db_connection(conn)
    return [r[0] for r in result]  # lista di stringhe (es. titoli PDF)

def update_docs_list():
    docs = get_docs_from_db()
    return gr.update(choices=docs, value=[])

def print_like_dislike(x: gr.LikeData):
    print(x.index, x.value, x.liked)


def refresh_pdf_folders():
    folders = list_pdf_folders()
    return gr.update(choices=folders, value=folders[0] if folders else None)


# funzione che elenca le cartelle disponibili in table_dataset
def list_pdf_folders():

    base = os.path.join(".", "table_dataset")
    if not os.path.exists(base):
        return []
    # return [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    # Restituisce tutte le cartelle dentro table_dataset, comprese le sotto-cartelle
    return [
        os.path.relpath(root, base)
        for root, dirs, files in os.walk(base)
        if root != base
    ]


# funzione che elenca i csv in una cartella basename
def list_csv_files(pdf_basename):
    refresh_pdf_folders()
    if not pdf_basename:
        return gr.update(choices=[], value=None)
    folder = os.path.join(".", "table_dataset", pdf_basename)
    if not os.path.exists(folder):
        return gr.update(choices=[], value=None)
    csvs = [f for f in os.listdir(folder) if f.endswith(".csv")]
    return gr.update(choices=csvs, value=csvs[0] if csvs else None)


# funzione che carica il csv come DataFrame
def load_csv(pdf_basename, csv_filename):
    if not pdf_basename or not csv_filename:
        return gr.update(value=pd.DataFrame(), visible=False)

    path = os.path.join(".", "table_dataset", pdf_basename, csv_filename)

    if not os.path.exists(path):
        return gr.update(value=pd.DataFrame(), visible=False)

    return gr.update(value=pd.read_csv(path, sep=';', on_bad_lines='warn', engine='python'), visible=True)


# funzione che salva il csv modificato
def save_csv(pdf_basename, csv_filename, df):
    if not pdf_basename or not csv_filename:
        return "⚠️ Seleziona prima una cartella e un file CSV."
    path = os.path.join(".", "table_dataset", pdf_basename, csv_filename)
    df.to_csv(path, index=False, sep=';')
    return f"✅ File {csv_filename} salvato nella cartella {pdf_basename}."
