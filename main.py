from utils import init_args
from runnable import Runnable
from table_extraction import UnstructuredTableExtractor
from tqdm import tqdm
import os
import csv
import json
from itertools import islice
from bs4 import BeautifulSoup
import re

if __name__ == "__main__":

    args = init_args()
    r = Runnable(args)

    if len(args["load_query_from_file"]) > 0:

        with open(args["load_query_from_file"], 'r') as file:
            data = json.load(file)

        if os.path.isdir(args["pdf"]):
            file_names = os.listdir(args["pdf"])
        elif os.path.isfile(args["pdf"]):
            file_names = [args["pdf"]]
        else:
            raise ValueError(f"wrong file name")

        for file_name in file_names:
            splitted_file_name = file_name.split(".")
            if splitted_file_name[-1] != "pdf":
                continue

            file_path = args["pdf"]
            base_name = os.path.basename(file_path)
            dir_name = os.path.splitext(base_name)[0]

            args["pdf"] = file_name

            metadata_path = os.path.join("table_dataset", dir_name)

            gri_code_to_page = {}
            tables_as_html = set()

            for gri_code, description in islice(data.items(), 3, 8):  # dal 4 all'8 GRI

                if gri_code not in gri_code_to_page.keys():
                    gri_code_to_page[gri_code] = []

                args["query"] = description
                r.set_args(args)
                s = r.run()

                ute = UnstructuredTableExtractor("yolox", "hi_res")

                for doc in tqdm(s[:args["k"]]):  # keeps only the top k pages with the highest score, where k is specified in the Python command (default = 5)

                    tables = ute.extract_table_unstructured([doc])  # extract tables

                    for i, table in enumerate(tables):
                        tables_as_html.add((table[0].metadata.text_as_html, doc.page_content, doc.metadata["page"], i))
                        gri_code_to_page[gri_code].append((doc.metadata["page"], i))

            for table_html in tables_as_html:

                # table_html[0] contiene il testo della tabella estratta (HTML)
                raw_table_text = table_html[0]

                soup = BeautifulSoup(raw_table_text, "html.parser")

                # Trova tutte le righe della tabella
                rows = []
                for tr in soup.find_all("tr"):
                    # Ogni riga può avere sia <td> che <th>
                    cells = [cell.get_text(strip=True) for cell in tr.find_all(["td", "th"])]
                    rows.append(cells)

                # Assicurati che la cartella esista
                if not os.path.exists(metadata_path):
                    os.makedirs(metadata_path, exist_ok=True)

                # Salva in CSV
                with open(os.path.join(metadata_path, f"{str(table_html[-2])}_{str(table_html[-1])}.csv"), mode='w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    writer.writerows(rows)

            with open(os.path.join(metadata_path, "metadata.json"), 'w',encoding='utf-8') as json_file:
                json.dump(gri_code_to_page, json_file, indent=4)

    elif len(args["query"]) > 0:

        if os.path.isdir(args["pdf"]):
            file_names = os.listdir(args["pdf"])
        elif os.path.isfile(args["pdf"]):
            file_names = [args["pdf"]]
        else:
            raise ValueError(f"wrong file name")

        for file_name in file_names:
            splitted_file_name = file_name.split(".")
            if splitted_file_name[-1] != "pdf":
                continue

            file_path = args["pdf"]
            base_name = os.path.basename(file_path)
            dir_name = os.path.splitext(base_name)[0]
            args["pdf"] = file_name

            question_to_page = {}
            tables_as_html = set()

            question_to_page[args["query"]] = []
            csvs = [f for f in os.listdir(os.path.join("table_dataset", dir_name)) if f.endswith(".csv")]

            matched_csvs = []

            s = r.run()

            for doc in tqdm(s[:args["k"]]):  # keeps only the top k pages with the highest score, where k is specified in the Python command (default = 5)
                page_str = str(doc.metadata["page"])
                for csv_file in csvs:
                    p = int(re.search(r"(\d+)_\d+\.csv$", csv_file).group(1))
                    if page_str == str(p):
                        matched_csvs.append(os.path.join(os.path.join("table_dataset", dir_name), csv_file))
                        i = int(re.search(r"_(\d+)\.csv$", csv_file).group(1))
                        question_to_page[args["query"]].append((p, i))

            metadata_path = f'table_dataset/{dir_name}/verbal_questions_metadata.json'

            # Assicura che la cartella padre esista
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)

            # Assicura che il file esista
            if not os.path.exists(metadata_path):
                with open(metadata_path, "w", encoding="utf-8") as f:
                    f.write("{}")  # inizializza ad esempio con un JSON vuoto
                    existing_data = {}

            else:
                with open(metadata_path, 'r') as json_file:
                    try:
                        existing_data = json.load(json_file)
                    except json.JSONDecodeError:
                        existing_data = {}  # file vuoto o corrotto → inizializza dict vuoto

            # Aggiorna con i nuovi dati
            existing_data.update(question_to_page)  # se vuoi unione di dict

            # Riscrivi tutto
            with open(metadata_path, "w", encoding='utf-8') as json_file:
                json.dump(existing_data, json_file, indent=4)

    else:
        s = r.run()
