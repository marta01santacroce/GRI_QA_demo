import gradio as gr  # version 5.44.1
from dotenv import load_dotenv
from gradio_pdf import PDF
from pdf2image import convert_from_path
from transformers import pipeline


load_dotenv()


p = pipeline(
    "document-question-answering",
    model="impira/layoutlm-document-qa",
)

def qa(question: str, doc: str) -> str:
    img = convert_from_path(doc)[0]
    output = p(img, question)
    return sorted(output, key=lambda x: x["score"], reverse=True)[0]['answer']


if __name__ == "__main__":

    theme = gr.themes.Soft(
        primary_hue="lime",
        radius_size="xxl",
    ).set(
        body_background_fill_dark='*background_fill_secondary',
        body_background_fill='*background_fill_primary',
        body_text_color='*neutral_900',
        body_text_color_dark='*primary_50', 
        embed_radius='*radius_md'
    )

    with gr.Blocks(
        theme=theme,
        fill_width=True,
        title="GRI-QA demo"
    ) as demo:

        gr.Markdown(
            "<h2 style='text-align: center; font-size: 40px;'>GRI-QA demo</h2>"
        )

        with gr.Row(height=500, equal_height=True): # Colonna sinistra: caricamento e anteprima PDF 
            with gr.Column(scale=1): qa, [ PDF(label="Document", height=500)]
            
            with gr.Column(scale=2):
                placeholder = gr.Textbox(
                    value="fare qualcosa..",
                    label="Analisi GRI",
                    
                    show_copy_button=True
                )

    demo.launch()
