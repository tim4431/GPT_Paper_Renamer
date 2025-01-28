import os
import time
import yaml
import json
import ctypes
import pdfplumber
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pydantic import BaseModel
from openai import OpenAI
import base64
import pdf2image
import tempfile
from win11toast import notify, update_progress


class Paper(BaseModel):
    is_paper: bool
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

    def on_moved(self, event):
        # FileMovedEvent(src_path='C://Users//Tim//Downloads\\science.aav9105.pdf.crdownload',
        # dest_path='C://Users//Tim//Downloads\\science.aav9105.pdf', event_type='moved', is_directory=False, is_synthetic=False)
        if (
            not event.is_directory
            and event.src_path.lower().endswith(".pdf.crdownload")
            and event.dest_path.lower().endswith(".pdf")
        ):
            print(f"File Moved: {event}")
            time.sleep(1)  # Allow time for file to be fully written
            if os.path.exists(event.dest_path):
                self.process_pdf_with_llm(event.dest_path)

    def on_created(self, event):
        # File Created: FileCreatedEvent(src_path='C://Users//Tim//Downloads\\thorlabs.pdf', dest_path='', event_type='created', is_directory=False, is_synthetic=False)
        if not event.is_directory and event.src_path.lower().endswith(".pdf"):
            print(f"File Created: {event}")
            time.sleep(1)  # Allow time for file to be fully written
            if os.path.exists(event.dest_path):
                self.process_pdf_with_llm(event.dest_path)

    def encode_image(self, image_path):
        """
        Utility to read an image file from disk and return its base64-encoded string.
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def process_pdf_with_llm(self, file_path):
        if file_path in self.processed_files:
            print(f"Already processed: {file_path}")
            return
        dirname, filenameext = os.path.split(file_path)
        filename, ext = os.path.splitext(filenameext)
        #
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
        # Create a temporary directory that will be cleaned up automatically
        with tempfile.TemporaryDirectory() as tmp_dir:
            images = pdf2image.convert_from_bytes(pdf_bytes)
            # just take the first page
            image = images[0]
            page_path = os.path.join(tmp_dir, f"frontpage.png")
            image.save(page_path, "PNG")
            print(f"Saved frontpage to {page_path}")

            # Encode the image in Base64
            base64_image = self.encode_image(page_path)
        #
        try:
            notify(
                title="GPT Paper Renamer",
                progress={
                    "title": filenameext,
                    "status": "Analyzing PDF File...",
                    "value": 1 / 2,
                    "valueStringOverride": "Step 1 / 2",
                },
                # buttons=["Yes", "No"],
                # duration="long",
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
                    }
                ],
                response_format=Paper,
            )
            response = response.choices[0].message.content.strip()
            print(f"Response: {response}")
            try:
                # Expect valid JSON with "amount" and "rationale"
                parsed = json.loads(response)
                # amt_str = parsed.get("amount", "0.0")
                is_paper = parsed.get("is_paper", False)
                title = parsed.get("title", "")
                author = parsed.get("author", "")
                #
                print(f"Physics paper: {is_paper}")
                print(f"Title: {title}")
                print(f"Author: {author}")
                new_name = f"{title}({filename}){ext}"

                if is_paper:
                    # if self.confirm_rename(file_path, new_name):
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
                else:
                    print("Not a paper")
                    update_progress(
                        {
                            "title": filenameext,
                            "value": 2 / 2,
                            "status": "Not a paper",
                            "valueStringOverride": "Step 2 / 2",
                        }
                    )
            except Exception as e:
                print(f"Error parsing response: {str(e)}")

        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")

    def confirm_rename(self, filenameext, new_name):
        response = ctypes.windll.user32.MessageBoxW(
            0,
            f"Rename the paper {filenameext}\n to {new_name}?",
            f"Physics paper detected: {filenameext}",
            4,  # MB_YESNO
        )
        return response == 6  # IDYES

    def rename_file(self, old_path, new_name):
        directory = os.path.dirname(old_path)
        new_path = os.path.join(directory, new_name)
        # handle duplicate names
        if os.path.exists(new_path):
            return False
        else:
            os.rename(old_path, new_path)
            print(f"Renamed:\n{old_path}\nto\n{new_path}")
            self.processed_files.add(new_path)
            return True


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    config = load_config()
    notify(
        "GPT Paper Renamer",
        "GPT Paper Renamer is running...",
        # duration="long",
    )
    # list number of files in the watch folder
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
