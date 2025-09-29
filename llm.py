from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from phoenix.otel import register
from openinference.instrumentation.openai import OpenAIInstrumentor
import gradio as gr

# setup tracing
tracer_provider = register(
    project_name="griqa_demo",
    endpoint="http://localhost:6006/v1/traces",
)
OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

# carico variabili env
load_dotenv(override=True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI()


def check(folder_path, gri_code_list_path, pdf_basename):
    """
    - Legge metadata.json in folder_path/file_name
    - Per ogni GRI e per ogni CSV collegato, chiede all'LLM se il contenuto è pertinente.
    - Alla fine:
         Scrive un nuovo metadata.json solo con riferimenti pertinenti
         Cancella i CSV non più referenziati da nessun GRI
    """

    folder_path = os.path.join(folder_path, pdf_basename)

    # --- carica descrizioni GRI ---
    with open(gri_code_list_path, "r", encoding="utf-8") as f:
        gri_code_list = json.load(f)

    # --- metadata.json ---
    metadata_path = os.path.join(str(folder_path), "metadata.json")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    updated_metadata = {}
    csv_decisions = {}  # mappa csv_filename -> YES/NO

    # --- loop GRI ---
    new_metadata_path = None

    for gri_code, refs in metadata.items():
        gri_desc = gri_code_list.get(gri_code, "Descrizione non trovata")

        kept_refs = []
        for page, num in refs:
            csv_filename = f"{page}_{num}.csv"
            csv_path = os.path.join(str(folder_path), csv_filename)

            if not os.path.exists(csv_path):
                continue

            # leggi contenuto CSV (limita righe per non esplodere token)
            with open(csv_path, "r", encoding="utf-8") as f:
                csv_content = f.read()

            csv_preview = "\n".join(csv_content.splitlines()[:30])  # max 30 righe

            prompt = f"""
            You are an expert in sustainability reporting (GRI Standards).
            I will give you:
            1. A GRI code and its description.
            2. The content of a CSV table extracted from a company report.

            Task: Decide if this CSV table is relevant to the GRI code.

            Answer with ONLY one word: "YES" if the CSV contains information that matches or supports the GRI description, otherwise "NO".

            ---

            GRI code: {gri_code}
            Description: {gri_desc}

            CSV content (partial preview):
            {csv_preview}
            """

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0
                )
                decision = response.choices[0].message.content.strip().upper()
            except Exception:
                decision = "YES"  # fallback: tienilo

            csv_decisions[csv_filename] = decision

            # mantieni il riferimento solo se YES
            if decision == "YES":
                kept_refs.append([page, num])

        if kept_refs:
            updated_metadata[gri_code] = kept_refs

        # salvo updated_metadata in un file json metadata_after_llm.json
        new_metadata_path = os.path.join(str(folder_path), "metadata_after_llm.json")
        with open(new_metadata_path, "w", encoding="utf-8") as f:
            json.dump(updated_metadata, f, indent=2, ensure_ascii=False)

    # --- elimina CSV non più referenziati ---
    all_kept_files = {f"{page}_{num}.csv" for refs in updated_metadata.values() for page, num in refs}
    all_checked_files = set(csv_decisions.keys())
    to_delete = all_checked_files - all_kept_files

    for csv_filename in to_delete:
        try:
            os.remove(os.path.join(str(folder_path), csv_filename))
        except Exception:
            pass

    return new_metadata_path


def formatted(folder_path, pdf_basename, chatbot=False):
    """
    Riformatta i CSV nella cartella folder_path/pdf_basename tramite chiamata a LLM
    """

    if chatbot:
        folder_path = os.path.join(str(folder_path), pdf_basename, "verbal_questions")
        metadata_formatted_path = os.path.join(folder_path, "metadata_formatted.json")

        # Se non esiste metadata_formatted.json, lo creo con lista vuota
        if not os.path.exists(metadata_formatted_path):
            with open(metadata_formatted_path, "w", encoding="utf-8") as f:
                json.dump({"formatted_files": []}, f, indent=2)

        # Carico contenuto esistente
        with open(metadata_formatted_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        formatted_files = set(metadata.get("formatted_files", []))
        print("DEBUG: formatted files:", formatted_files)
    else:
        folder_path = os.path.join(folder_path, pdf_basename)
        metadata_formatted_path = None
        formatted_files = set()

    # Tutti i CSV nella cartella
    csvs = [f for f in os.listdir(folder_path) if f.endswith(".csv")]
    print("DEBUG: csvs in folder:", csvs)

    # Filtra quelli non ancora formattati
    csvs_to_format = [f for f in csvs if f not in formatted_files]
    print("DEBUG: csvs da formattare:", csvs_to_format)

    if not csvs_to_format:
        print("DEBUG: Nessun nuovo CSV da formattare.")
        return

    for csv_file in csvs_to_format:
        csv_path = os.path.join(folder_path, csv_file)

        # Leggi il CSV originale
        with open(csv_path, "r", encoding="utf-8") as f:
            csv_content = f.read()



        prompt = f"""
         
        You are provided with a CSV file automatically extracted from a table. Your task is to reformat it to obtain a rectangular table (all rows have the same number of columns). 
        Instructions 
        - Take the maximum number of fields that a row in the initial CSV has and correct the formatting by bringing all rows to that length.
         -Use ; as the column separator.
         - If a row has missing cells, fill then with NaN.
         - Keep numeric values as they are (including negative percentages).
         - Correct any extraction errors (misplaced values, incorrect indentation, damaged headers). 
        - The output should be clean CSV content only. 
        - Improve readability: standardise headers and align numeric and text values. 
        - Do not remove any rows.
        
        Return only the final CSV content, without any additional explanations.

        Here is the CSV to process:

        {csv_content}

        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        corrected_csv = response.choices[0].message.content

        # Rimuove eventuali backtick iniziali e finali
        corrected_csv = corrected_csv.strip("`").strip()

        # Salva il CSV corretto sovrascrivendo il file originale
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(corrected_csv)

        print(f"DEBUG: CSV {csv_file} formattato e salvato.")

        # Aggiorna metadata_formatted.json
        if metadata_formatted_path:
            formatted_files.add(csv_file)
            with open(metadata_formatted_path, "w", encoding="utf-8") as f:
                json.dump({"formatted_files": sorted(formatted_files)}, f, indent=2)


def add_user_message(chatbot_history, chat_input_data):
    """Aggiunge il messaggio dell'utente alla chat e prepara l'input per il bot."""
    if chat_input_data is None:
        return chatbot_history, {"text": ""}, {"text": ""}

    user_msg = chat_input_data.get("text", "")

    # Aggiunge subito il messaggio dell'utente
    updated_chat = chatbot_history + [{"role": "user", "content": user_msg}]

    # Svuota subito la textbox
    cleared_input = {"text": ""}

    # Output aggiuntivo: il messaggio originale da passare all'handler
    saved_input = {"text": user_msg}

    return updated_chat, cleared_input, saved_input


def format_for_openai(chat_history):
    messages = [{"role": "system",
                 "content": "Sei un assistente esperto di sostenibilità e standard GRI. Questa è la storia passata della chat:"}]
    for entry in chat_history:
        # Se è tupla (user_msg, bot_msg) tipica di Gradio Chatbot
        if isinstance(entry, tuple) or isinstance(entry, list):
            user_text, bot_text = entry
            messages.append({"role": "user", "content": user_text})
            if bot_text:
                messages.append({"role": "assistant", "content": bot_text})
        elif isinstance(entry, dict):
            messages.append(entry)
    return messages


def ask_openai(messages):
    """
    Invia un prompt a OpenAI e restituisce il testo generato.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Errore durante la chiamata a OpenAI: {str(e)}"
