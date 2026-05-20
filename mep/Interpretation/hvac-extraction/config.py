import os
from dotenv import load_dotenv
from openai import OpenAI


class Config:
    def __init__(self):
        load_dotenv()

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = OpenAI(api_key=api_key)


# singleton-style usage
config = Config()
client = config.client