## Is there a relationship between trees and crime in San Francisco?
Previous studies in Baltimore, Austin, and Cincinnati have linked more trees with increased public safety, and we would like to analyze if this extends to San Francisco.

## Team Members

| Name             | GitHubID     | Role / Focus                                                             |
|------------------|--------------|--------------------------------------------------------------------------|
| Korbin White     | korbinvwhite | API calls - Census Bureau and DataSF San Francisco Street Tree Inventory |
| Sophia Chung     | szphzz       | Visualization - StreamLit                                                |
| Brendan Waterval | Brendanw1    | Webscraping - SF Police Reports                                          |
| Miguel Cerna     | dudedatas    | Data Cleaning & EDA                                                      |

---

## Problem Statement
- We combine San Francisco Police Department Crime Reports and DataSF San Francisco Street Tree Inventory to test whether there is an association between trees and crime by district, while also considering demographic and socioeconomic characteristics. We will create a dashboard with tree and crime counts on a map, with the features to narrow down types of tree by species, types of crime, and month/year and demographic and socioeconomic factors such as population, median household income, poverty, and employment. This could be helpful for city planners, landscapers, residents, and police.


---

## Data Sources and Integration Goal

### Sources
| #   | Source & Link                                                                                                          | Method   | What it contains                                         | Update frequency    | Access requirements |
|-----|------------------------------------------------------------------------------------------------------------------------|----------|----------------------------------------------------------|---------------------|---------------------|
| 1   | [San Francisco Police Department Crime Reports](https://www.sanfranciscopolice.org/stay-safe/crime-data/crime-reports) | SCRAPING | rows, columns, time range, geography — in your own words | monthly             | none                |
| 2   | [DataSF San Francisco Street Tree Inventory](https://data.sf.gov/resource/tkzw-k3nq.json)                              | API      | ...                                                      | regularly refreshed | none                |
| 3   | [U.S. Census Bureau, 2024 American Community Survey 5-Year Estimates](https://api.census.gov/data/2024/acs/acs5)       | API      | ...                                                      | annually            | census api key      |

Note: If we need a key, say which environment variable holds it and make sure that variable also appears in the .env_template

### Integration Goal

---

## Setup Instructions (Locally)

### Prerequisites
- Python 3.11+
- A GCP service account key with access to PROJECT/BUCKET/DATASET
- Any source API keys listed in the table below

### 1. Clone the repository
```bash
git clone https://github.com/szphzz/git-branch-crime.git
cd git-branch-crime
git switch branch_name
```

### 2. Configure environment variables
Copy the example file and fill in your own values:

```bash
cp .env_template .env_template
```

| Variable | Description | Example |
| --- | --- | --- |
| `GCP_SERVICE_ACCOUNT_KEY` | Absolute path to your service account JSON | `/Users/you/.ssh/key.json` |
| `SOURCE_API_KEY` | Key for SOURCE NAME (free tier) | `abc123...` |
| `API_SERVICE_URL` | Where the web app reaches the API | `http://api-server:8000` |

### 4. How to call your endpoint
To start the API server,
```python
fastapi run mycode.py
```

```python
requests.post("http://localhost:8000/something", json=something)
```
Make sure it writes the data in the bucket.

---
## Repository Structure
Work is split across five branches, one per area of the project:

| Branch         | Owner            | Purpose                                                          |
|----------------|------------------|------------------------------------------------------------------|
| `main`         | Everyone         | Project overview, README, and team contract                      |
| `fastapi`      | Korbin White     | FastAPI endpoints for Census Bureau and DataSF Street Tree APIs  |
| `scraping`     | Brendan Waterval | Web scraping of SF Police crime reports                          |
| `cleaning-eda` | Miguel Cerna     | Data cleaning and exploratory data analysis                      |
| `streamlit`    | Sophia Chung     | Streamlit dashboard and visualizations                           |

```
main
├── README.md
└── Team_Contract.pdf

fastapi
├── fast_api/
│   └── fast_api.py
├── .env_template
└── README.md

scraping
└── README.md

cleaning-eda
├── cleaning_eda/
│   ├── cleaning_eda.py
│   └── test_inspect_data.py
├── .gitignore
└── README.md

streamlit
└── README.md
```
