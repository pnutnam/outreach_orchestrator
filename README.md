# Outreach Orchestrator

This tool automates the process of researching potential clients and generating personalized "Lead Magnet" emails. It scrapes websites, investigates LinkedIn profiles, analyzes Google Reviews, and uses AI (Gemini) to draft high-converting cold emails.

## 🚀 Getting Started (No-Code Guide)

Follow these steps to get up and running.

### 1. Installation

**Step A: Get Antigravity**

1. **Download & Install**: If you haven't already, download and install Antigravity from [INSERT ANTIGRAVITY DOWNLOAD LINK HERE].
2. **Open Antigravity**: Launch the application.

**Step B: Load the Project**
You have two options to get this tool running inside Antigravity:

*Option 1: The "Git Link" Method (Easiest)*

1. In Antigravity, look for the input prompt or "New Project" button.
2. Type the following command (replace `[Your-Git-Link]` with the actual link to this repository):
    > *"Clone this repo: [Your-Git-Link] and help me set it up."*
3. Antigravity will handle the downloading for you.

*Option 2: The "Zip File" Method*

1. Download this repository as a ZIP file from Git.
2. Unzip the folder to a known location (e.g., `Documents/Outreach_Tool`).
3. In Antigravity, specify this folder as your "Workspace".

### 2. Configuration (API Keys)

Once the project is loaded in Antigravity:

1. Locate the file named `.env.example` in the file explorer.
2. **Duplicate it** and rename the copy to `.env`.
3. Paste your API keys after the `=` signs.
    - **Gemini Key**: [Get it here](https://aistudio.google.com/app/apikey)
    - **Search Key**: [Get it here](https://developers.google.com/custom-search/v1/overview)
    - **Search Engine ID (CX)**: [Get it here](https://programmablesearchengine.google.com/controlpanel/all)

### 3. How to Use

#### A. Prepare your Input

Open `urls.csv` in Excel or Numbers.

- Column A (`website`): Paste the website URLs you want to research.
- Column B (`email`): (Optional) Only if you don't have a website but have an email address.
- save the file.

#### B. Customize your Email Template (Optional)

Open `templates/prompt_template.txt`.

- This file contains the instructions for the AI.
- You can change the "Questions to Use" or the "CTA" to match your specific offer.
- **Do not** change the parts in curly braces like `{{CONTEXT_STR}}`.

#### C. Run the Tool

In your terminal, run:

```bash
python orchestrator.py --batch urls.csv
```

**What happens next?**

1. The tool will open a Chrome window and start visiting the sites in your list. **Do not close this window.**
2. It will save "Intelligence" files (JSON) for each company.
3. It will generate a final CSV file called `first_thirty_first_email.csv` with the drafted emails.

### Troubleshooting

- **"Command not found"**: Try using `python3` instead of `python`.
- **Chrome crashes**: Make sure your Chrome is up to date.
- **"Rate Limit"**: If the tool stops, it might mean you hit your daily quota for the free Google API. Just wait and try again tomorrow.

## Feature Flags

If you want to run only specific parts:

- `python orchestrator.py --batch urls.csv --scan` : Only does the research (scraping).
- `python orchestrator.py --batch urls.csv --generate` : Only writes the emails (uses existing research).
