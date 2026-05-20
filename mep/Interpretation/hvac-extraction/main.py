from flask import Flask, request, jsonify, render_template

from config import client
from services.extraction_service import ExtractionService
from utils.image_utils import ImageUtils
from utils.pdf_utils import PDFUtils
from services.mysql_service import MySQLService


class App:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.json.sort_keys = False

        # services
        self.extraction_service = ExtractionService(client)
        self.mysql_service = MySQLService()

        self._register_routes()

    def _register_routes(self):
        @self.app.route("/")
        def home():
            return render_template("index.html")

        @self.app.route("/extract-ducts", methods=["POST"])
        def extract_ducts():
            if "file" not in request.files:
                return jsonify({"error": "No file"}), 400

            file = request.files["file"]

            if file.filename == "":
                return jsonify({"error": "Empty filename"}), 400

            try:
                # PDF handling
                if ImageUtils.is_pdf(file.filename):
                    base64_images = PDFUtils.pdf_to_base64_images(file.stream)

                # Image handling
                else:
                    base64_images = [ImageUtils.encode_image(file.stream)]

                result = self.extraction_service.extract(base64_images)
                extraction_id = self.mysql_service.insert_extraction(
                    filename=file.filename,
                    result=result
                )

                return jsonify({
                    "id":extraction_id,
                    "result":result
                    
                    })

            except Exception as e:
                return jsonify({"error": str(e)}), 500

    def run(self):
        self.app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    App().run()
