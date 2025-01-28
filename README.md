# GPT_Paper_Renamer
When a new paper is added to a folder, automatically determine whether the paper is a scientific paper and rename it accordingly.

# Usage
`config.yaml`
```yaml
watch_folder: "<the folder you want to watch>"
api_key: "<openai api key>"
prompt: |
  You are a PDF classification and metadata extraction assistant.
  Determine whether the paper is a scientific paper or arxiv preprint based on its title and content, if it is, return is_paper as true, otherwise false.
  Also, extract the title and corresponding author from the paper.
  Given the image of an academic paper, please return the following JSON structure:
  {
     "is_paper": <true or false>,
     "title": "<paper title in str>",
     "author": "<corresponding author in str>",
  }
  Make sure it is valid JSON and includes each field.
```