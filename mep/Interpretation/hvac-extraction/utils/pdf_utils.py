# utils/pdf_utils.py

import base64
import fitz  # PyMuPDF
from PIL import Image
import io


class PDFUtils:
    @staticmethod
    def pdf_to_base64_images(file_stream):
        """
        Converts PDF stream → list of base64 PNG images
        """
        pdf_bytes = file_stream.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        images_base64 = []

        for page_num in range(len(doc)):
            page = doc[page_num]

            # 4x zoom = ~300 DPI equivalent
            mat = fitz.Matrix(4, 4)
            pix = page.get_pixmap(matrix=mat)

            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))

            buffered = io.BytesIO()
            img.save(buffered, format="PNG")

            img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            images_base64.append(img_base64)

        return images_base64