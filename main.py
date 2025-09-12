from dotenv import load_dotenv
from utils import init_args
from runnable import Runnable
from table_extraction import UnstructuredTableExtractor
from tqdm import tqdm
import os
import csv
import json
from itertools import islice
from bs4 import BeautifulSoup


load_dotenv()

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
        gri_code_to_page = {}
        tables_as_html = set()

        for gri_code, description in islice(data.items(),0,3):
          if gri_code not in gri_code_to_page.keys():
            gri_code_to_page[gri_code] = []

          args["query"] = description
          r.set_args(args)
          s = r.run()

          ute = UnstructuredTableExtractor("yolox", "hi_res")

          for doc in tqdm(s[:args["k"]]): #keeps only the top k pages with the highest score, where k is specified in the Python command (default = 20) 

            #print("\n\nDEB doc: "+ str(doc))

            tables = ute.extract_table_unstructured([doc]) #extract tables

            #print("\n\nDEB tables: "+ str(tables))

            for i,table in enumerate(tables):
              #print("\n\nDEB table: "+ str(table))

              #for i in range(len(table)):
              #print("\n\nDEB table[0]: "+ str(table[0]))
              
              tables_as_html.add((table[0].metadata.text_as_html, doc.page_content, doc.metadata["page"], i))
              gri_code_to_page[gri_code].append((doc.metadata["page"], i))

          #print("DEB: " + str(tables_as_html))  


        for table_html in tables_as_html:
          #print("DEBUG table_html: " + str(table_html))

          # table_html[0] contiene il testo della tabella estratta (HTML)
          raw_table_text = table_html[0]

          #print("[DEBUG-raw_table_text]: " + str(raw_table_text))

          soup = BeautifulSoup(raw_table_text, "html.parser")

          # Trova tutte le righe della tabella
          rows = []
          for tr in soup.find_all("tr"):
              # Ogni riga può avere sia <td> che <th>
              cells = [cell.get_text(strip=True) for cell in tr.find_all(["td", "th"])]
              rows.append(cells)

          # Assicurati che la cartella esista
          if not os.path.exists(f"table_dataset/{dir_name}"):
              os.makedirs(f"table_dataset/{dir_name}", exist_ok=True)

          # Salva in CSV
          with open(f'table_dataset/{dir_name}/{str(table_html[-2])}_{str(table_html[-1])}.csv',
                    mode='w', newline='', encoding='utf-8') as file:
              writer = csv.writer(file)
              writer.writerows(rows)


        with open(f'table_dataset/{dir_name}/metadata.json', 'w') as json_file:
          json.dump(gri_code_to_page, json_file, indent=4)
          
    else:
      s = r.run()
