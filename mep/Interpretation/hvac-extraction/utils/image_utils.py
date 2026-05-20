import base64


class ImageUtils:
    @staticmethod
    def encode_image(file_stream):
        return base64.b64encode(file_stream.read()).decode("utf-8")
    
    @staticmethod
    def is_pdf(filename):
        return filename.lower().endswith(".pdf")
