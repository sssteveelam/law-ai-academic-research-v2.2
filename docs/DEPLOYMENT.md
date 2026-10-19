# Deployment

## Streamlit Community Cloud

This is the quickest public demo deployment:

1. Push the source files to a GitHub repository. Do not commit `.env`,
   `data/*.db`, `data/cache`, or `data/downloads`.
2. In Streamlit Community Cloud, create an app from the repository.
3. Set the branch to `main` and the main file to `app/main.py`.
4. Add the following values under the app's Secrets settings:

```toml
LAW_RESEARCH_DATABASE_URL = "sqlite:///data/research.db"
LAW_RESEARCH_CACHE_DIR = "data/cache"
LAW_RESEARCH_CACHE_TTL_SECONDS = 86400
LAW_RESEARCH_OPENALEX_EMAIL = ""
LAW_RESEARCH_OPENALEX_API_KEY = ""
LAW_RESEARCH_SEMANTIC_SCHOLAR_API_KEY = ""
LAW_RESEARCH_CROSSREF_MAILTO = ""
LAW_RESEARCH_UNPAYWALL_EMAIL = ""
LAW_RESEARCH_HTTP_TIMEOUT_SECONDS = 20
LAW_RESEARCH_MAX_DOWNLOAD_BYTES = 52428800
LAW_RESEARCH_DOWNLOAD_DIR = "data/downloads"
```

The application reads both local `.env` values and Streamlit Secrets. Restart
the app after changing secrets.

The current application uses SQLite and local cache/download directories.
Those files are suitable for a demo but should not be treated as durable
production storage on a managed cloud runtime. For persistent multi-user
deployment, use a persistent volume or migrate the database and downloaded
files to managed storage before exposing the app publicly.

## Local network sharing

To share the app on the same LAN from Windows:

```powershell
uv run streamlit run app/main.py --server.address 0.0.0.0 --server.port 8501
ipconfig
```

Open `http://<IPv4-address>:8501` from another device on the same network.
