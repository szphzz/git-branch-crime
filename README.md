# GIT BRANCH CRIME

Our project aims to find out if there is a correlation between the number of trees, crime rates, and socioeconomic
factors in San Francisco. Our findings could help residents, tourists, homebuyers, law enforcement, and city planners 
better understand neighborhood conditions and public safety.

**Live web app:** `https://git-branch-crime-streamlit-636031847641.us-west1.run.app/` --Cloud run url
**API (private):** `https://api-server-xxxxx-uw.a.run.app`

---

## Team Members


| Name             | GitHubID     | Role / Focus                                                             |
|------------------|--------------|--------------------------------------------------------------------------|
| Korbin White     | korbinvwhite | API calls - Census Bureau and DataSF San Francisco Street Tree Inventory |
| Sophia Chung     | szphzz       | Visualization - StreamLit                                                |
| Brendan Waterval | Brendanw1    | Webscraping - SF Police Reports                                          |
| Miguel Cerna     | dudedatas    | Data Cleansing - EDA                                                     |

## Problem Statement

We combine San Francisco Police Department Crime Reports and DataSF San Francisco Street Tree Inventory to test
whether there is an association between trees and crime by district. We will create a dashboard with tree and crime
counts on a map, with the features to narrow down by type of tree, type of crime, and month. This could be helpful for 
city planners, landscapers, residents, and police.


## Data Sources and Integration Goal

### Sources

| #   | Source & Link                                                                                                          | Method   | What it contains                                              | Update frequency | Access requirements |
|-----|------------------------------------------------------------------------------------------------------------------------|----------|---------------------------------------------------------------|------------------|---------------------|
| 1   | [San Francisco Police Department Crime Reports](https://www.sanfranciscopolice.org/stay-safe/crime-data/crime-reports) | SCRAPING | police_district, crime_count,crime_category,reporting_period  | monthly          | none                |
| 2   | [DataSF San Francisco Street Tree Inventory](https://data.sf.gov/resource/tkzw-k3nq.json)                              | API      | treeid, latitude, longitude, police_disctirct, species, GEOID | daily            | none                |
| 3   | [U.S. Census Bureau, 2024 American Community Survey 5-Year Estimates](https://api.census.gov/data/2024/acs/acs5)       | API      | GEOID, total_population, povverty_rate, unemployment_rate     | annually         | census api key      |

Every key listed here must also appear in `.env_template`.
```
GCP_SERVICE_ACCOUNT_KEY=
GCP_PROJECT_ID=
GCP_BUCKET_NAME=
CENSUS-API-KEY=
### Integration Goal
```

### Integration Goal
Combining these datasets allows us to see the relationship between the number of trees and the amount of crime in SF
Districts. Also, it allows us to see the relationship between the number of trees and poverty levels in SF districts.
It's not possible for one single dataset to do so becuause with only the data about trees, there's no information about
crimes or things such as poverty rates. Andwith the census data and crime data, alone, there's no way to know anything 
about trees.
---

## Repository Structure

```
git-branch-crime/
│
├── fast_api/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── fast_api.py              # FastAPI application and API endpoints
│
├── scraping/
│   ├── sfpd_scraper.py          # Scrapes SF Police crime reports
│   ├── crime_router.py          # Crime-related API routes
│   ├── run_scraper.sh           # Script to run the scraper
│   ├── requirements.txt
│   ├── __init__.py
│   ├── README.md
│   └── tests/
│       └── test_parser.py      # Scraper tests
│
├── cleaning_eda/
│   ├── cleaned_tree_data.ipynb  # Tree cleaning and geographic joins
│   ├── cleaned_census_data.ipynb # Census cleaning and processing
│   └── crime.ipynb              # Crime data notebook
│
├── streamlit/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── streamlit_app.py         # Streamlit dashboard
│   └── user_definition.py       # User-defined functions
│
├── Current_Police_Districts_20261017.csv
│                                 # Police district boundaries
│
├── Analysis_Neighborhoods_-_2020_census_tracts_assigned_to_neighborhoods_20261017.csv
│                                 # Census tract boundaries
│
├── gcloud_command.sh            # Google Cloud deployment commands
├── .env_template                # Environment variable template
├── .gitignore
├── Team_Contract.pdf
└── README.md                    # Project documentation
```
Feel free to change the structure and name your own modules, libraries and packages.
---

## API Endpoints

| Method | Path | Purpose | Example |
| --- | --- | --- | --- | --- |
| `POST` | `/tree-data`   | Fetches SF street tree data from DataSF and uploads it to GCS   |
| `POST` | `/census-data` | Fetches 2024 ACS census tract data for SF and uploads it to GCS | 


Document your real endpoints here - But also make sure how to access FastAPI auto-docs (Update them using docstrings)

---

## Setup — Local
1. Clone your GitHub repository.
2. Install the required Python libraries.
3. Set up the .env file with GCP credentials and the Census API key.
4. Start FastAPI.
5. Run the Streamlit web application.
### Prerequisites

- Python 3.13
- Docker
- pip
- GCP account with Cloud Storage access
- GCP service account JSON key
- U.S. Census Bureau API key

### 1. Clone and configure

```bash
git clone https://github.com/szphzz/git-branch-crime.git
cd git-branch-crime
cp .env_template .env     # then fill in your values
```

| Variable                  | Description                       | Example |
|---------------------------|-----------------------------------| --- |
| `GCP_PROJECT_ID`          | Your GCP project                  | `msds692-team3` |
| `GCP_BUCKET_NAME`         | Bucket for raw + processed data   | `team3-bay-data` |
| `GCP_SERVICE_ACCOUNT_KEY` | Path to the service account JSON  | `/tmp/gcp-key.json` |
| `CENSUS_API_KEY`          | Key for census api key            | `abc123...` |

`.env` and your `*.json` key are in `.gitignore`. **Never commit them.**

### 2. Run both services

On api folder,
```bash
docker build -t api .
```

On streamlit folder,
```bash
docker build -t streamlit .
```

- API docs: http://localhost:8000/docs
- Web app: http://localhost:8501

### 3. Trigger a collection run

```bash
curl -X POST http://localhost:8000/collect -H "Content-Type: application/json" -d '{}'
```

Then confirm the object landed in your bucket.

---

## Setup — Deploy to GCP

Edit the CONFIG block at the top of `gcloud_command.sh`, then:

```bash
./gcloud_command.sh all
```

Or one piece at a time while iterating:

```bash
./gcloud_command.sh bootstrap   # enable APIs, create Artifact Registry repo
./gcloud_command.sh api         # rebuild + redeploy the API
./gcloud_command.sh web         # rebuild + redeploy the web app
./gcloud_command.sh scheduler   # (re)create the Cloud Scheduler job
./gcloud_command.sh urls        # print both service URLs
```

---
