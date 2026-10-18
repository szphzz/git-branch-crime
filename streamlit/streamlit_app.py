import json
import re

from google.oauth2 import service_account
from google.cloud import storage
import streamlit as st
import pandas as pd

from user_definition import (bucket_name, project_id,
                             service_account_file_path)


def retrieve_data_from_gcs(service_account_key: str,
                           project_id: str,
                           bucket_name: str,
                           file_name_suffix: str
                           ) -> dict:
    credentials = service_account.Credentials.from_service_account_file(service_account_key)
    client = storage.Client(project=project_id,
                            credentials=credentials)
    
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs()

    content = []
    job_titles = []
    company_dict = dict()
    
    for blob in blobs:
        if blob.name.endswith(file_name_suffix):
            blob_data = json.loads(blob.download_as_string())
            content += blob_data["results"]
            job_titles.append(blob_data["job_title"])
            company_dict = company_dict | blob_data["company_dict"]
    job_titles = list(set(job_titles))
    job_titles.sort()
    return {"results": content,
            "job_titles": job_titles,
            "company_dict": company_dict}


def summarize_distribution(df: pd.DataFrame,
                           column_name: str,
                           top_n: int = 10) -> dict:
    """
    df[column_name] holds a list per row (e.g. skills per job). Explode
    those lists into individual items, then count how many rows each item
    appears in across the whole column, keeping only the top_n most
    frequent items.
    Ex. [['a','b','c'], ['a','d']], top_n=2 -> {'a': 2, 'b': 1}
    """
    distr = df[column_name].explode().value_counts()
    return distr.head(top_n).to_dict()


if __name__ == '__main__':
    gcs_data = retrieve_data_from_gcs(service_account_file_path,
                                      project_id,
                                      bucket_name,
                                      "crime-data.json")
    role_name = ", ".join(gcs_data["job_titles"])
    company_dictionary = gcs_data["company_dict"]
    data = pd.DataFrame(gcs_data["results"])

    st.title(f"{role_name} Job Listings")
    with st.sidebar:
        st.write("Filter by Month")
        unique_categories = list(company_dictionary.keys())
        unique_categories.sort()
        selected_categories = []

        for category in unique_categories:
            if st.checkbox(f"{category}",
                           value=True,
                           key=f"checkbox_{category}"):
                selected_categories.append(category.lower())

        pattern = "|".join(re.escape(category)
                           for category in selected_categories)
        if pattern:
            filtered_df = data[data["link"].str.contains(pattern)]
        else:
            filtered_df = data.iloc[0:0]
        filtered_df = filtered_df[["date", "title", "skills", "link"]]
        filtered_df = filtered_df.drop_duplicates(subset=["link"])
        filtered_df = filtered_df.sort_values(
            by=["date", "title"], ascending=[False, True])

    st.dataframe(filtered_df,
                 hide_index=True,
                 column_config={
                     "link": st.column_config.LinkColumn()})

    skill_counts = summarize_distribution(filtered_df, "skills")
    if skill_counts:
        skill_df = pd.DataFrame(
            {"count": skill_counts.values()},
            index=pd.CategoricalIndex(skill_counts.keys(),
                                      categories=skill_counts.keys(),
                                      ordered=True))
        st.bar_chart(skill_df)
