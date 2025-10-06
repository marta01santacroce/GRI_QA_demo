import gradio as gr  # version 5.45
import os
import json
import subprocess
from itertools import islice
from urllib.parse import quote
import sys
import llm
import pandas as pd
import shutil
import gradio_actions
import markdown2
import build_summary_company
from gradio_toggle import Toggle

server_host = "155.185.48.176"  # se lavoro sul server unimore, sennò server_host = 'localhost'

messages = [
    {"role": "system",
     "content": (
         "You are an experienced assistant in sustainability and GRI standards. "
         "You are helping the user understand the data extracted from PDFs. "
         "Instructions: "
         "- Think step by step through the information before answering (use reasoning internally). "
         "- Answer clearly, concisely and succinctly. "
         "- Use only the data from the tables inside the provided context. "
         "- If you cannot find the answer, say so clearly. "
         "- Report the row and cell you used for the answer (from the CSV format) and indicate the PAGE and NUMBER of the table (from the context). "
         "- Do not explain your reasoning process; just give the final answer and required details."
     )},
    {"role": "user",
     "content": (
         "Here are the name of the file and the relevant context like a table in csv with at the end the page and the number of table:\n---\n{context}\n---\n"
         "Now, answer the following question based strictly on the context.\n\nQuestion: {user_message}"
     )}
]


def clear_all():
    # csv_group.visible = False
    return None


def load_companies_with_summary(companies_name, base_path="./table_dataset"):
    companies_data = {}

    for name in companies_name:
        summary_path = os.path.join(base_path, name, "summary.txt")
        if os.path.exists(summary_path):
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_text = f.read().strip()
        else:
            summary_text = ""
        companies_data[name] = summary_text

    return companies_data


def upload_and_process_files(files):
    """
    Funzione che riceve una lista di file PDF, esegue le chiamate a main.py e restituisce un testo sui valori GRI trovati.
    """
    csv_group.visible = False
    if not files:
        return "⚠️No file uploaded"

    # Percorso del file di query
    json_file_query = os.path.join('json_config', 'en_queries_30X.json')
    with open(json_file_query, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"

    for file in files:

        filename = os.path.basename(file.name)
        pdf_path = os.path.join("reports", filename)  # destinazione sul server
        shutil.copy(file.name, pdf_path)  # copia dal tmp di gradio al server
        pdf_basename = os.path.splitext(filename)[0]
        pdf_name = os.path.abspath(os.path.join("reports", filename))

        try:
            # 1. Denso
            subprocess.run(
                [sys.executable, "main.py", "--pdf", pdf_name, "--embed", "--use_dense"],
                shell=False,
                check=True,
                env=env,
                capture_output=True,
                text=True
            )

            # 2. Sparso
            subprocess.run(
                [sys.executable, "main.py", "--pdf", pdf_name, "--embed", "--use_sparse"],
                shell=False,
                check=True,
                env=env,
                capture_output=True,
                text=True
            )

            # 3. Ensemble con query
            subprocess.run(
                [sys.executable, "main.py", "--pdf", pdf_name, "--load_query_from_file", json_file_query,
                 "--use_ensemble"],
                shell=False,
                check=True,
                env=env,
                capture_output=True,
                text=True
            )

        except subprocess.CalledProcessError as e:

            results.append(
                f"📁 {pdf_basename}: Error while executing main.py  \n"
                f"stdout:\n{e.stdout}\n\nstderr:\n{e.stderr}"
            )
            continue

        """ Uso openAI per scremare le tabelle trovate. Per ogni GRI-tabella_presa_dal_csv gli chiedo se è inerente"""

        new_metadata_path = llm.check(folder_path=os.path.join(".", "table_dataset"),
                                      gri_code_list_path=json_file_query, pdf_basename=pdf_basename)

        if not os.path.exists(new_metadata_path):
            results.append(f"📁{pdf_basename}: {new_metadata_path} non trovato  ")
            continue

        x = os.path.join(".", "table_dataset", pdf_basename, "metadata.json")
        y = os.path.join(".", "table_dataset", pdf_basename, "metadata_before_llm.json")
        os.replace(x, y)

        new_name = os.path.join(".", "table_dataset", pdf_basename, "metadata_after_llm.json")
        os.replace(new_metadata_path, new_name)

        """ !! SPOSTARE llm.formatted prima di llm.check se si vuole formattare prima di valuatre se è pertinente il csv al GRI """
        llm.formatted(folder_path=os.path.join(".", "table_dataset"), pdf_basename=pdf_basename)

        # Leggo il metadata_after_llm.json
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
                        link = f"   [pag.{page}](http://{server_host}:8080/viewer.html?file={quote(pdf_basename)}.pdf#page={page})  "
                        output_lines.append(f"     {link} -> {page - 1}_{other_num}.csv  ")

        results.append("\n".join(output_lines))

        build_summary_company.build_summary(pdf_basename)

    return "\n\n".join(results)


def handle_chat_with_pdf(chat_history, chat_input_data, docs_list, select_pot_value):
    """
    Gestisce una domanda dell'utente con file PDF selezionati.
    """
    user_message = chat_input_data.get("text", "").strip()

    if len(docs_list) == 0:
        response = "⚠️ No documents selected."
        new_chat_history = chat_history + [
            {"role": "assistant", "content": response}
        ]
        save_chat_and_toggle(new_chat_history, select_pot_value)
        return new_chat_history

    if user_message == '':
        response =  "⚠️ No input received from User."
        new_chat_history = chat_history + [
            {"role": "assistant", "content": response}
        ]
        save_chat_and_toggle(new_chat_history, select_pot_value)
        return new_chat_history

    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"

    context = ""

    # Se il toggle è attivo → comportamento alternativo per ora non fa nulla se non stampare a video una frase
    if select_pot_value:
        response = "🧠 PoT attivo"
        new_chat_history = chat_history + [
            {"role": "assistant", "content": response}
        ]
        save_chat_and_toggle(new_chat_history, select_pot_value)
        return new_chat_history


    for file in docs_list:

        pdf_name = os.path.join(os.path.abspath(os.getcwd()), "reports", file + ".pdf")

        try:
            subprocess.run(
                [sys.executable, "main.py", "--pdf", pdf_name, "--query", user_message, "--use_ensemble"],
                shell=False, check=True, env=env, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            return [{"role": "assistant", "content": f"⚠️ Error during PDF processing:\n{e.stderr}"}]

        # Recupero metadata.json
        metadata_path = os.path.join("table_dataset", file, "verbal_questions_metadata.json")
        if not os.path.exists(metadata_path):
            return [{"role": "assistant", "content": f"⚠️ No metadata.json found for {file}"}]

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # Trovo la tabella collegata
        csv_texts = []
        for q, refs in metadata.items():
            if q.strip().lower() == user_message.strip().lower():
                for page, num in refs:
                    csv_file = os.path.join("table_dataset", file, f"{page}_{num}.csv")
                    if os.path.exists(csv_file):
                        try:
                            df = pd.read_csv(csv_file, sep=';')
                        except Exception:
                            print("DEBUG eccezione file: ", csv_file)
                            continue

                        csv_texts.append(f"# Page {page}, Table {num}\n")
                        csv_texts.append(df.to_csv(index=False))
                        print("DEBUG: csv file: ", csv_file)

        if not csv_texts:
            context = f"No table found for your query for file selected {file}"

        # Costruisco messaggi per OpenAI
        tables_str = "\n\n".join(csv_texts)  # unisci tutte le tabelle trovate
        header = f"File name: {file}\n"
        context += f"{header}\n\n{tables_str}\n---\n"

    message = [
        messages[0],  # system invariato
        {
            "role": "user",
            "content": messages[1]["content"].format(
                context=context,
                user_message=user_message
            )
        }
    ]

    response = llm.ask_openai(message)

    # Appendi la nuova risposta alla chat esistente
    new_chat_history = chat_history + [
        {"role": "assistant", "content": response}
    ]

    save_chat_and_toggle(new_chat_history, select_pot_value)
    return new_chat_history


def make_card_html(company_name, summary_text):
    return f"""
    <div style="
        border: 1px solid #6bff93; /* bordo verde chiaro */
        border-radius: 10px;
        display: flex;
        flex-direction: column;
        height: 300px; /* altezza uniforme delle card */
        overflow: hidden; /* impedisce che il contenuto esca */
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    ">
        <!-- Header della card -->
        <div style="
            background-color: #11bd67; /* verde header */
            color: #000000; /* testo nero */
            padding: 10px;
            text-align: center;
            font-weight: bold;
            flex-shrink: 0;
            border-radius: 10px 10px 0 0; /* arrotonda solo angoli superiori */
        ">
            {company_name}
        </div>

        <!-- Contenuto scrollabile -->
        <div style="
            padding: 10px;
            overflow-y: auto;
            flex: 1;
            font-size: 14px;
            text-align: left;
            color: black;
            max-width: 100%;
            overflow-x: hidden;
        ">
            {markdown2.markdown(summary_text)}
        </div>
    </div>
    """


def add_cards(files):
    """Aggiunge le card relative ai file appena caricati e ricarica la vista dalle risorse sul disco/DB."""
    if not files:
        return render_cards()

    # Eventualmente fai qualche operazione sui nuovi file (es: generare summary subito)
    new_names = [os.path.splitext(os.path.basename(f.name))[0] for f in files]
    for name in new_names:
        try:
            # Se vuoi obbligare la creazione del summary subito, decommenta:
            # build_summary_company.build_summary(name)
            pass
        except Exception:
            pass

    # Ricostruisci le cards leggendo lo stato aggiornato dal DB/filesystem
    return render_cards()


def render_cards_from_dict(companies_dict):
    cards_html_content = "".join(make_card_html(name, summary) for name, summary in companies_dict.items())
    return f"""
    <div style="
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
        gap: 15px;
        max-height: 80vh;
        overflow-y: auto;
        padding-right: 10px;
        max-width: 100%;
        overflow-x: hidden;
    ">
        {cards_html_content}
    </div>
    """


def render_cards():
    # Rilegge la lista attuale di documenti dalla sorgente (DB / filesystem)
    companies = gradio_actions.get_docs_from_db()
    companies_dict = load_companies_with_summary(companies)
    return render_cards_from_dict(companies_dict)


def load_chat_and_toggle():
    chat_history = []
    toggle_state = False

    # Carica chat salvata
    if os.path.exists("chat_state.json"):
        try:
            with open("chat_state.json", "r", encoding="utf-8") as f:
                chat_history = json.load(f)
        except Exception as e:
            print("Errore caricando chat salvata:", e)

    # Carica stato toggle
    if os.path.exists("toggle_state.json"):
        try:
            with open("toggle_state.json", "r", encoding="utf-8") as f:
                toggle_state = json.load(f)
        except Exception as e:
            print("Errore caricando toggle:", e)

    return chat_history, toggle_state


def save_chat_and_toggle(chat_history, toggle_state):
    try:
        with open("chat_state.json", "w", encoding="utf-8") as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=2)
        with open("toggle_state.json", "w", encoding="utf-8") as f:
            json.dump(toggle_state, f)
    except Exception as e:
        print("Errore salvando lo stato:", e)


with gr.Blocks(css="max-height: 100%") as chatbot_ui:
    gr.HTML("""
        <style>
        #docs_list .wrap.svelte-1m7w40t {
            max-height: 400px !important;
            overflow-y: auto !important;
            padding: 5px;
        }
        
        </style>
        """)
    gr.Markdown(
        "<h2 style='text-align: center; font-size: 40px;'>GRI-QA Chatbot</h2>"
    )

    with gr.Row():
        # Colonna sinistra → Chat
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                elem_id="chatbot",
                type="messages",
                min_height=500,
                max_height=500,
                avatar_images=(None, "./images/icon_chatbot.png"),
                show_copy_button=True,
                show_copy_all_button=True,
                group_consecutive_messages=False
            )

            chat_input = gr.MultimodalTextbox(
                elem_id='chat_input',
                interactive=True,
                placeholder="Enter question for the selected file...",
                show_label=False,
                sources="microphone",
            )

        # Colonna destra → Lista file interrogabili
        with gr.Column(scale=1):
            with gr.Row():
                docs_list = gr.CheckboxGroup(
                    elem_id="docs_list",
                    choices=[],
                    label="Select documents to query",
                    value=[],
                    interactive=True,

                )
            with gr.Row(elem_id="row_toggle"):
                select_pot = Toggle(
                    elem_id='PoT',
                    label='PoT',
                    show_label=False,
                    info='PoT',
                    value=False,
                    interactive=True,
                    color='#50B596',
                    transition=1
                )


    def clear_textbox():
        return {"text": ""}


    # Disabilita le checkbox quando l'utente invia


    def disable_docs():
        return gr.update(interactive=False)


    # Riabilita le checkbox quando il bot ha finito


    def enable_docs():
        return gr.update(interactive=True)


    # Disabilita il textbox quando l'utente invia


    def disable_textbox():
        return gr.update(interactive=False)


    # Riabilita il textbox quando il bot ha finito


    def enable_textbox():
        return gr.update(interactive=True)


    # Invia messaggio utente
    chat_msg = chat_input.submit(
        llm.add_user_message,
        inputs=[chatbot, chat_input],
        outputs=[chatbot, chat_input, chat_input]
    )

    # Subito dopo l’invio → disabilita docs_list
    chat_msg.then(
        disable_docs,
        outputs=[docs_list]
    )
    # Subito dopo l’invio → disabilita textbox
    chat_msg.then(
        disable_textbox,
        outputs=[chat_input]
    )

    # Bot risponde usando anche la selezione dei documenti
    bot_msg = chat_msg.then(
        handle_chat_with_pdf,
        inputs=[chatbot, chat_input, docs_list, select_pot],
        outputs=[chatbot]
    )

    # Riabilita le checkbox quando il bot ha finito
    bot_msg.then(
        enable_docs,
        outputs=[docs_list]
    )
    # Riabilita il textbox quando il bot ha finito
    bot_msg.then(
        enable_textbox,
        outputs=[chat_input]
    )

    # Pulizia textbox
    chat_msg.then(
        clear_textbox,
        outputs=[chat_input]
    )

    chatbot.like(gradio_actions.print_like_dislike, None, None, like_user_message=False)

with gr.Blocks(css="max-height: 100%") as company_cards:
    cards_container = gr.HTML()

with gr.Blocks(css="max-height: 100%") as process_file_ui:
    gr.Markdown(
        "<h2 style='text-align: center; font-size: 40px;'>GRI-QA Extraction of GRI Information</h2>"
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
                height=300,
                show_label=True,
                container=True,

            )

        # Colonna destra (2/3)
        with gr.Column(scale=2):
            with gr.Group(visible=True) as csv_group:
                # Dropdown inizialmente vuoti
                pdf_dropdown = gr.Dropdown(choices=[], value=None, label="🗂️ Seleziona cartella")
                csv_dropdown = gr.Dropdown(choices=[], value=None, label="📄 Seleziona file CSV")

                dataframe = gr.Dataframe(visible=False, interactive=True, value=pd.DataFrame(), max_height=380,
                                         wrap=True, show_copy_button=True, show_search='search', label="Contenuto CSV")
                log_output = gr.Textbox(label="Output", interactive=False, autoscroll=False)

            with gr.Row():
                gr.HTML("")  # spazio vuoto a sinistra
                save_button = gr.Button(value="Salva modifiche", variant='primary')
                gr.HTML("")  # spazio vuoto a destra

            # Aggiornamento dinamico delle scelte
            pdf_dropdown.change(gradio_actions.list_csv_files, inputs=pdf_dropdown, outputs=csv_dropdown)
            csv_dropdown.change(gradio_actions.load_csv, inputs=[pdf_dropdown, csv_dropdown], outputs=dataframe)
            save_button.click(gradio_actions.save_csv, inputs=[pdf_dropdown, csv_dropdown, dataframe],
                              outputs=log_output)

    # Eventi
    upload_button.click(
        fn=upload_and_process_files,
        inputs=pdf_input,
        outputs=output_box
    ).then(
        fn=gradio_actions.refresh_pdf_folders,
        inputs=[],
        outputs=pdf_dropdown
    ).then(
        fn=gradio_actions.update_docs_list,
        inputs=[],
        outputs=docs_list
    ).then(
        fn=add_cards,
        inputs=[pdf_input],
        outputs=[cards_container]
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

    with gr.Blocks(
            theme='lone17/kotaemon',
            title="GRI-QA demo"

    ) as demo:
        gr.HTML("""
           <style>
           /* === Scrollbar globale per tutta la pagina === */

           /* Tutti gli elementi scrollabili */
           *::-webkit-scrollbar {
                width: 8px;
            }
            *::-webkit-scrollbar-thumb {
                background-color: rgba(100, 100, 100, 0.4);
                border-radius: 4px;
            }
            *::-webkit-scrollbar-thumb:hover {
                background-color: rgba(100, 100, 100, 0.6);
            }
           
           </style>
           """)
        gr.TabbedInterface(
            [chatbot_ui, process_file_ui, company_cards],
            ["Chatbot", "Process File", "Company Card"],
        )
        # Rigenera cards al caricamento
        demo.load(concurrency_limit=None, fn=render_cards, inputs=[], outputs=[cards_container])
        # Rigenera dropdown PDF al caricamento
        demo.load(concurrency_limit=None, fn=gradio_actions.refresh_pdf_folders, inputs=[], outputs=[pdf_dropdown])
        # Rigenera la checkbox nel chatbot
        demo.load(concurrency_limit=None, fn=gradio_actions.refresh_docs_list, inputs=[], outputs=[docs_list])
        # Ricarica chat e toggle salvati al caricamento della pagina
        demo.load(concurrency_limit=None, fn=load_chat_and_toggle, inputs=[], outputs=[chatbot, select_pot])

    demo.launch()
