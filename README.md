# Engineering Portfolio
This is the repo for my engineering portfolio, hosted by GitHub pages (Potentially, this might be hosted by an actual domain later). 

I made this repo and started hosting by GitHub because my school district has a very invasive internet filter and, quite frankly, stupid policies. Specifically, starting the year of 2025, all students of my district with their school email cannot share anything outside of the district, and nothing can be shared to them via the Google Workspace. 

This was a problem because my previous portfolio hosted by Google Sites relied on embeds from one of my personal accounts, with the new policy, the entire site broke. 

Migrating the data from my personal to school account would not only be slow, if I were to forget to migrate the data back from my school to personal account before I graduate, my school account will be terminated, and all data would be lost. This was the original reason for the data to be hosted on my personal account, so I wouldn't lose my data/work when I graduated.

## Notebook Compilation

The `compilation/` tooling builds a printable engineering notebook that includes the title page, table of contents, home page, and every entry:

1. Install Python dependencies and Playwright (only needs to be done once per machine):
   ```bash
   python3 -m pip install --upgrade pip
   python3 -m pip install -r compilation/requirements.txt
   python3 -m playwright install chromium
   ```
2. Generate the HTML + PDF locally:
   ```bash
   npm run notebook:pdf
   ```
   Use `npm run notebook:html` to skip the PDF step while iterating.

Outputs land in `compilation/output/notebook.html` and `compilation/output/notebook.pdf`.

A companion GitHub Action `Export Notebook` is available under the *Actions* tab for manual runs. It publishes the same HTML/PDF as build artifacts so reviewers can download the latest export without running the tooling locally.
