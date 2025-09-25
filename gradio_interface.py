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

server_host = "155.185.48.176"  # se lavoro sul server unimore, sennò server_host = 'localhost'

messages = [{"role": "system",
             "content": "You are an experienced assistant in sustainability and GRI standards. "
                        "You are helping the user understand the data extracted from PDFs. "
                        "Instructions: "
                        "- Answer clearly, concisely and succinctly. "
                        "- Use the data from the tables inside the context. "
                        "- If you cannot find the answer, say so clearly."
                        "- Report the row and cell you used for the answer (from the formatting of the CSV) and the PAGE and NUMBER of the table (extracted from the context)"
             },
            {"role": "user",
             "content":
                 "Here are the name of the file and the relevant context like a table in csv with at the end the page and the number of table:\n---\n{context}\n---\n"
                 "Now, answer the following question based strictly on the context.\n\nQuestion: {user_message}"
             },
            ]


def clear_all():
    # csv_group.visible = False
    return None


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

    return "\n\n".join(results)


def handle_chat_with_pdf(chatbot, chat_input_data, docs_list):
    """
    Gestisce una domanda dell'utente con file PDF selezionati.
    """
    # print("\nDEBUG docs_list:", docs_list)
    user_message = chat_input_data.get("text", "").strip()
    # print("DEBUG user_message:", user_message)

    if chat_input_data is None or user_message == '':
        return [{"role": "assistant", "content": "⚠️ No input received from User."}]

    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"

    if len(docs_list) == 0:
        return [{"role": "assistant", "content": "⚠️ No documents selected."}]

    context = ""

    for file in docs_list:

        pdf_name = os.path.join(os.path.abspath(os.getcwd()), "reports", file + ".pdf")

        # print("DEBUG pdf_name:", pdf_name)

        try:
            subprocess.run(
                [sys.executable, "main.py", "--pdf", pdf_name, "--query", user_message, "--use_ensemble"],
                shell=False, check=True, env=env, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            return [{"role": "assistant", "content": f"⚠️ Error during PDF processing:\n{e.stderr}"}]

        # Recupero metadata.json
        metadata_path = os.path.join("table_dataset", file, "verbal_questions", "metadata.json")
        if not os.path.exists(metadata_path):
            return [{"role": "assistant", "content": f"⚠️ No metadata.json found for {file}"}]

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # Trovo la tabella collegata
        csv_texts = []
        for q, refs in metadata.items():
            if q.strip().lower() == user_message.strip().lower():
                for page, num in refs:
                    csv_file = os.path.join("table_dataset", file, "verbal_questions", f"{page}_{num}.csv")
                    if os.path.exists(csv_file):
                        df = pd.read_csv(csv_file)
                        csv_texts.append(f"# Page {page}, Table {num}\n")
                        csv_texts.append(df.to_csv(index=False))

        if not csv_texts:
            # return [{"role": "assistant", "content": f"❌ No table found for your query for file selected {file}"}]
            csv_texts = f"\nNo table found for your query for file selected {file}\n"

        # Costruisco messaggi per OpenAI
        tables_str = "\n\n".join(csv_texts)  # unisci tutte le tabelle trovate
        header = f"File name: {file}\n"
        context += f"{header}\n\n{tables_str}\n---\n"

        # print("\nDEBUG context:", context)

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

    # print("\nDEBUG message:", message)

    response = llm.ask_openai(message)

    return [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response}
    ]


with gr.Blocks() as chatbot_ui:
    gr.Markdown(
        "<h2 style='text-align: center; font-size: 40px;'>GRI-QA Chatbot</h2>"
    )

    with gr.Row():
        # Colonna sinistra → Chat
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                elem_id="chatbot",
                type="messages",
                min_height=600,
                max_height=600,
                avatar_images=(None, "./images/icon_chatbot.png")
            )

            chat_input = gr.MultimodalTextbox(
                interactive=True,
                placeholder="Enter question for the selected file...",
                show_label=False,
                sources="microphone"
            )

        # Colonna destra → Lista file interrogabili
        with gr.Column(scale=1):
            docs_list = gr.CheckboxGroup(
                choices=gradio_actions.get_docs_from_db(),  # qui li carichi dal DB
                label="Seleziona documenti da interrogare",
                value=[]
            )


    def clear_textbox():
        return {"text": ""}


    # Invia messaggio utente
    chat_msg = chat_input.submit(
        llm.add_user_message,
        inputs=[chatbot, chat_input],
        outputs=[chatbot, chat_input, chat_input]
    )

    # Bot risponde usando anche la selezione dei documenti
    bot_msg = chat_msg.then(
        handle_chat_with_pdf,
        inputs=[chatbot, chat_input, docs_list],
        outputs=[chatbot]
    )

    # Pulizia textbox
    chat_msg.then(
        clear_textbox,
        outputs=[chat_input]
    )

    chatbot.like(gradio_actions.print_like_dislike, None, None, like_user_message=False)

with gr.Blocks() as process_file_ui:
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
                height=450,
                show_label=True,
                container=True,

            )

        # Colonna destra (2/3)
        with gr.Column(scale=2):
            with gr.Group(visible=True) as csv_group:
                # Dropdown inizialmente vuoti
                pdf_dropdown = gr.Dropdown(choices=gradio_actions.list_pdf_folders(), value=None,
                                           label="🗂️ Seleziona cartella")
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
            title="GRI-QA demo",

    ) as demo:
        gr.TabbedInterface(
            [chatbot_ui, process_file_ui],
            ["Chatbot", "Process File"]
        )
        demo.load(concurrency_limit=None)

    demo.launch()
