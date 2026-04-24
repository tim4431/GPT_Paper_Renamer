import os
import time
import yaml
import json
import ctypes
import base64
import tempfile
import pdf2image
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pydantic import BaseModel
from openai import OpenAI
from win11toast import notify, update_progress, toast
import atexit

INVALID_CHARS = '<>:"/\\|?*'


class Paper(BaseModel):
    title: str
    author: str


class PDFHandler(FileSystemEventHandler):
    def __init__(self, config):
        self.config = config
        self.api_key = config["api_key"]
        self.client = OpenAI(api_key=self.api_key)
        self.prompt = config["prompt"]
        super().__init__()
        self.processed_files = set()
        self.current_filepath = None

    def on_moved(self, event):
        if (
            not event.is_directory
            and event.src_path.lower().endswith(".pdf.crdownload")
            and event.dest_path.lower().endswith(".pdf")
        ):
            print(f"File Moved: {event}")
            time.sleep(1)
            if os.path.exists(event.dest_path):
                self.process_pdf_with_llm(event.dest_path)

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".pdf"):
            print(f"File Created: {event}")
            time.sleep(1)
            if os.path.exists(event.src_path):
                self.process_pdf_with_llm(event.src_path)

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def process_pdf_with_llm(self, file_path):
        if file_path in self.processed_files:
            print(f"Already processed: {file_path}")
            return
        try:
            self.current_filepath = file_path
            toast(
                "GPT Paper Renamer",
                f"Detecting new download {file_path}. Rename?",
                buttons=["Yes"],
                on_click=self._process_pdf_with_llm,
            )
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")

    def _process_pdf_with_llm(self, response):
        file_path = self.current_filepath
        dirname, filenameext = os.path.split(file_path)
        filename, ext = os.path.splitext(filenameext)

        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        with tempfile.TemporaryDirectory() as tmp_dir:
            images = pdf2image.convert_from_bytes(pdf_bytes)
            image = images[0]
            page_path = os.path.join(tmp_dir, "frontpage.png")
            image.save(page_path, "PNG")
            base64_image = self.encode_image(page_path)

        try:
            notify(
                title="GPT Paper Renamer",
                progress={
                    "title": filenameext,
                    "status": "Analyzing PDF File...",
                    "value": 1 / 2,
                    "valueStringOverride": "Step 1 / 2",
                },
            )
            response = self.client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                },
                            },
                        ],
                    },
                ],
                response_format=Paper,
            )
            response = response.choices[0].message.content.strip()
            parsed = json.loads(response)
            title = parsed.get("title", "Unknown")
            author = parsed.get("author", "Unknown")

            safe_title = self.make_filename_safe(title)
            safe_author = self.make_filename_safe(author)
            new_name = (
                f"{safe_title}_({filename})_{safe_author}{ext}"
                if safe_title and safe_author
                else f"{filename}{ext}"
            )

            if self.rename_file(file_path, new_name):
                update_progress(
                    {
                        "title": new_name,
                        "value": 2 / 2,
                        "status": "Renaming file...",
                        "valueStringOverride": "Step 2 / 2",
                    }
                )
            else:
                print("Duplicate name")
                update_progress(
                    {
                        "title": filenameext,
                        "value": 2 / 2,
                        "status": "Duplicate name",
                        "valueStringOverride": "Step 2 / 2",
                    }
                )

        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")

    def make_filename_safe(self, name):
        for char in INVALID_CHARS:
            name = name.replace(char, "_")
        return name.strip()

    def rename_file(self, old_path, new_name):
        directory = os.path.dirname(old_path)
        new_path = os.path.join(directory, new_name)
        if os.path.exists(new_path):
            return False
        else:
            os.rename(old_path, new_path)
            print(f"Renamed: {old_path} -> {new_path}")
            self.processed_files.add(new_path)
            return True


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    config = load_config()
    notify("GPT Paper Renamer", "GPT Paper Renamer is running...")
    files = os.listdir(config["watch_folder"])
    print(len(files))
    event_handler = PDFHandler(config)
    observer = Observer()
    observer.schedule(event_handler, path=config["watch_folder"], recursive=False)
    observer.start()

    try:
        print(f"Monitoring {config['watch_folder']} for papers...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    #
    # at exit, notify user
    # register the exit function

    atexit.register(lambda: notify("GPT Paper Renamer", "GPT Paper Renamer is stopped"))
