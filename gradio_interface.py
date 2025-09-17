import gradio as gr  # version 5.45
import os
import json
import subprocess
from itertools import islice
from urllib.parse import quote
import os
import json
import subprocess
from itertools import islice
from urllib.parse import quote
import sys
import llm
import pandas as pd

def refresh_pdf_folders():
    folders = list_pdf_folders()
    return gr.update(choices=folders, value=folders[0] if folders else None)


# funzione che elenca le cartelle disponibili in table_dataset
def list_pdf_folders():
    base = os.path.join(".", "table_dataset")
    if not os.path.exists(base):
        return []
    return [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]

# funzione che elenca i csv in una cartella basename
def list_csv_files(pdf_basename):
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
        return pd.DataFrame()
    path = os.path.join(".", "table_dataset", pdf_basename, csv_filename)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)

# funzione che salva il csv modificato
def save_csv(pdf_basename, csv_filename, df):
    if not pdf_basename or not csv_filename:
        return "⚠️ Seleziona prima una cartella e un file CSV."
    path = os.path.join(".", "table_dataset", pdf_basename, csv_filename)
    df.to_csv(path, index=False)
    return f"✅ File {csv_filename} salvato nella cartella {pdf_basename}."


def upload_and_process_files(files):
    """
    Funzione che riceve una lista di file PDF, esegue le chiamate a main.py e restituisce un testo sui valori GRI trovati.
    """
    csv_group.visible=False
    if not files:
        return "⚠️No file uploaded"

    # Percorso del file di query
    json_file_query = r".\json_config\en_queries_30X.json"
    with open(json_file_query, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"

    for file in files:
        filename = file.name
        pdf_basename = os.path.splitext(os.path.basename(filename))[0]

        try:
            # 1. Denso
            subprocess.run(
                [sys.executable, "main.py", "--pdf", filename, "--embed", "--use_dense"],
                shell=False,
                check=True,
                env=env,
                capture_output=True,
                text=True
            )
            # 2. Sparso
            subprocess.run(
                [sys.executable, "main.py", "--pdf", filename, "--embed", "--use_sparse"],
                shell=False,
                check=True,
                env=env,
                capture_output=True,
                text=True
            )
            # 3. Ensemble con query
            subprocess.run(
                [sys.executable, "main.py", "--pdf", filename,"--load_query_from_file", json_file_query, "--use_ensemble"],
                shell=False,
                check=True,
                env=env,
                capture_output=True,
                text=True
            )

        except subprocess.CalledProcessError as e:
            results.append(
                f"📁 {pdf_basename}: Errore durante l'esecuzione di main.py  \n"
                f"stdout:\n{e.stdout}\n\nstderr:\n{e.stderr}"
            )
            continue



        ''' Uso openAI per scremare le tabelle trovate. Per ogni GRI-tabella_presa_dal_csv gli chiedo se è inerente'''    

        new_metadata_path=llm.check(folder_path=os.path.join(".", "table_dataset"), gri_code_list_path = json_file_query, pdf_basename = pdf_basename) 
        #print("\nDEBUG---NEW_METADATA_PATH: " + str(new_metadata_path))

        x = os.path.join(".", "table_dataset", pdf_basename,"metadata.json")
        y = os.path.join(".", "table_dataset", pdf_basename,"metadata_before_llm.json")
        os.replace(x, y)
        #print(f"\nDEBUG--- x metadata_before_llm= {y}")
    
        new_name = os.path.join(".", "table_dataset", pdf_basename,"metadata_after_llm.json")
        os.replace(new_metadata_path, new_name)
        #print(f"\nDEBUG---new_name of new_metadata_path cioè metadata_after_llm= {new_metadata_path}")
    


        # Leggo il metadata_after_llm.json
       
        if not os.path.exists(new_metadata_path):
            results.append(f"📁{pdf_basename}: {new_metadata_path} non trovato  ")
            continue

        with open(new_metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        output_lines = [f"📁**{pdf_basename}**  "]

        for gri_code, description in islice(data.items(), 3, 8):  # dal 4 all' 8 GRI

            if gri_code in metadata:
                gri_line = f"   🔹**GRI {gri_code}**: {description}  "
                output_lines.append(gri_line)
                pages = []
                for page, other_num in metadata[gri_code]:
                    if page not in pages:
                        pages.append(page)
                        page += 1
                        link = f"   [pag.{page}](http://localhost:8080/viewer.html?file={quote(pdf_basename)}.pdf#page={page})  "
                        output_lines.append(f"     {link}")

        results.append("\n".join(output_lines))
    

    return "\n\n".join(results)


def clear_all(): 
    csv_group.visible=False
    return None

with gr.Blocks() as load_file:
    gr.Markdown(
        "<h2 style='text-align: center; font-size: 40px;'>GRI-QA demo</h2>"
    )

    with gr.Row():
        # Colonna sinistra (1/3)
        with gr.Column(scale=1):
            # Caricamento PDF
            pdf_input = gr.File(
                label="Carica PDF",
                file_types=[".pdf"],
                file_count="multiple"
            )

            with gr.Row():
                clear_button = gr.Button(value="Clear")
                upload_button = gr.Button(value="Submit", variant='primary')

            # Output sotto il caricamento
            output_box = gr.Markdown(
                label="Output",
                height=500,
                show_label=True,
                container=True
            )

        # Colonna destra (2/3)
        with gr.Column(scale=2):
            with gr.Group(visible=True) as csv_group:
                # Dropdown inizialmente vuoti
                pdf_dropdown = gr.Dropdown(choices=list_pdf_folders(), value=None, label="🗂️ Seleziona cartella")
                csv_dropdown = gr.Dropdown(choices=[], value=None, label="📄 Seleziona file CSV")

                dataframe = gr.Dataframe( interactive=True,value=pd.DataFrame(),max_height= 380, wrap=True,show_copy_button=True,show_row_numbers=True,show_search='search', label="Contenuto CSV")
                log_output = gr.Textbox(label="Output", interactive=False, autoscroll=False)

            with gr.Row():
                gr.HTML("")  # spazio vuoto a sinistra
                save_button = gr.Button(value="💾 Salva modifiche", variant='primary')
                gr.HTML("")  # spazio vuoto a destra
                        
            # Aggiornamento dinamico delle scelte
            pdf_dropdown.change(list_csv_files, inputs=pdf_dropdown, outputs=csv_dropdown)
            csv_dropdown.change(load_csv, inputs=[pdf_dropdown, csv_dropdown], outputs=dataframe)
            save_button.click(save_csv, inputs=[pdf_dropdown, csv_dropdown, dataframe], outputs=log_output)
            

    # Eventi
    upload_button.click(
        fn=upload_and_process_files,
        inputs=pdf_input,
        outputs=output_box
    ).then(
        fn=refresh_pdf_folders,
        inputs=[],
        outputs=pdf_dropdown
    )

    clear_button.click(
        fn=clear_all,
        inputs=[],
        outputs=pdf_input
    )


if __name__ == "__main__":

    # Imposta la cartella da servire
    pdf_dir = os.path.join(os.getcwd(), "reports")

    # Avvia un server HTTP in background sulla cartella reports sulla porta 8080
    subprocess.Popen(
        ["python", "-m", "http.server", "8080"],
        cwd=pdf_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    theme = gr.themes.Ocean(
        primary_hue="teal",
        secondary_hue="cyan",
        neutral_hue="slate",
    )

    with gr.Blocks(
        theme=theme,
        title="GRI-QA demo"
    ) as demo:
        
        load_file.render()
        
    demo.launch()
