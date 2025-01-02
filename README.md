# Taaghche downloader

**Save books purchased from [taaghche.com](https://taaghche.com) !**

this is a Python script that allows users to save books purchased from taaghche.com. The script utilizes Selenium to  downloading the pages of the purchased books as images. Finally, it converts these images into a single PDF file for easy access and reading.

## Requirements
  + Python 3.x
  + Selenium
  + Pillow (PIL)
  + Chrome WebDriver

## Installation
### Clone the repository:
```bash
git clone https://github.com/hctilg/taaghche-dl.git
cd taaghche-dl
```

### Install the required packages:
```bash
pip install -r requirements.txt
```

Download and install Chrome WebDriver that matches your Chrome version from [here](https://sites.google.com/chromium.org/driver/).

### Usage

Open the script in your preferred Python environment.

Run the script:
```bash
python downloader.py
```

+ When prompted, login to your taaghche account and press Enter.

+ Navigate to the reading page of the book you want to download and customize the settings, then press Enter.

+ The script will automatically save the pages as images and convert them into a PDF file.
