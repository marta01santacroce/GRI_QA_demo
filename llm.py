from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from phoenix.otel import register
from openinference.instrumentation.openai import OpenAIInstrumentor
import shutil

# setup tracing
tracer_provider = register(
    project_name="prova_marta",
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
    metadata_path = os.path.join(folder_path, "metadata.json")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

   

    updated_metadata = {}
    csv_decisions = {}  # mappa csv_filename -> YES/NO

    # --- loop GRI ---
    for gri_code, refs in metadata.items():
        gri_desc = gri_code_list.get(gri_code, "Descrizione non trovata")

        #print(f"\n=== Analizzo GRI {gri_code}: {gri_desc} ===")

        kept_refs = []
        for page, num in refs:
            csv_filename = f"{page}_{num}.csv"
            csv_path = os.path.join(folder_path, csv_filename)

            if not os.path.exists(csv_path):
                #print(f"   ⚠️ CSV {csv_filename} non trovato")
                continue
           
            # leggi contenuto CSV (limita righe per non esplodere token)
            with open(csv_path, "r", encoding="utf-8") as f:
                csv_content = f.read()

            csv_preview = "\n".join(csv_content.splitlines()[:30])  # max 30 righe
            #print(f"   📄 Controllo {csv_filename} (prime 30 righe):")
            #print(csv_preview)

            # --- prompt per l'LLM ---
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
            except Exception as e:
                #print(f"   ❌ Errore chiamando LLM per {csv_filename}: {e}")
                decision = "YES"  # fallback: tienilo

            csv_decisions[csv_filename] = decision
            #print(f"   🔎 LLM decision for {csv_filename}: {decision}")

            # mantieni il riferimento solo se YES
            if decision == "YES":
                kept_refs.append([page, num])

        if kept_refs:
            updated_metadata[gri_code] = kept_refs



        #salvo updated_metadata in un file json metadata_after_llm.json
        new_metadata_path = os.path.join(folder_path, "metadata_after_llm.json")
        with open(new_metadata_path, "w", encoding="utf-8") as f:
            json.dump(updated_metadata, f, indent=2, ensure_ascii=False)

    #print(f"\n💾 Salvato nuovo metadata.json. Backup creato in {backup_path}")

    # --- elimina CSV non più referenziati ---
    all_kept_files = {f"{page}_{num}.csv" for refs in updated_metadata.values() for page, num in refs}
    all_checked_files = set(csv_decisions.keys())
    to_delete = all_checked_files - all_kept_files

    for csv_filename in to_delete:
        try:
            os.remove(os.path.join(folder_path, csv_filename))
            #print(f"   🗑️ Eliminato {csv_filename}")
        except Exception as e:
            pass
            #print(f"   ⚠️ Impossibile eliminare {csv_filename}: {e}")


    #print(f"\n✅ Analisi completata per il file {pdf_basename}. File {new_metadata_path} aggiornato e CSV ripuliti nella cartella {folder_path}.")
    return new_metadata_path

#chiamata di prova
if __name__ == "__main__":
    folder_path = r"C:\Users\marta\Desktop\work_proj\GRI-QA\table_dataset"
    gri_code_list_path = r".\json_config\en_queries.json"
    pdf_basename = "prova"
    new_metadata_path = check(folder_path, gri_code_list_path, pdf_basename)

    
