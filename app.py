import streamlit as st

from amass_api import search_trials

FIELDS = [
    "briefTitle",
    "phase",
    "overallStatus",
    "studyType",
    "enrollment",
    "sponsorName",
    "nctId",
]

st.title("Amass TrialCore demo")

disease = st.text_input("Disease")
search = st.button("Search")

if search:
    if not disease.strip():
        st.warning("Enter a disease to search.")
    else:
        try:
            records = search_trials(disease, limit=10)
        except Exception as e:
            st.error(str(e))
        else:
            if not records:
                st.info("No trials found.")
            else:
                rows = [{field: record.get(field) for field in FIELDS} for record in records]
                st.dataframe(rows, use_container_width=True)
