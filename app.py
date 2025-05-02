import streamlit as st
import requests
import pandas as pd

#─── キャッシュ付きフェッチ関数 ───────────────────────────────
@st.cache_data
def fetch_json(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

@st.cache_data
def get_all_topics(mailto):
    """
    OpenAlex /topics を page-based pagination で全件取得し、
    id と display_name のみを返す
    """
    df_list = []
    per_page = 200
    page = 1
    while True:
        url = (
            "https://api.openalex.org/topics"
            f"?select=id,display_name&per-page={per_page}&page={page}"
            + (f"&mailto={mailto}" if mailto else "")
        )
        j = fetch_json(url)
        results = j.get("results", [])
        if not results:
            break
        df = pd.DataFrame(results)[["id", "display_name"]]
        df_list.append(df)
        if len(results) < per_page:
            break
        page += 1
    return pd.concat(df_list, ignore_index=True)

@st.cache_data
def fetch_grouped_counts(filter_params, group_by, mailto):
    """
    /works?filter=...&group_by=... の結果を key,count のDataFrameで返す。
    """
    url = (
        "https://api.openalex.org/works"
        f"?filter={filter_params}"
        f"&group_by={group_by}&per_page=200"
        + (f"&mailto={mailto}" if mailto else "")
    )
    j = fetch_json(url)
    df = pd.DataFrame(j.get("group_by", []))[["key", "count"]]
    return df.assign(key=df["key"].astype(str))

#─── UI ──────────────────────────────────────────────────────────────
st.sidebar.title("設定")
mailto    = st.sidebar.text_input("Email (オプション)", "")
countries = st.sidebar.text_input("Country Codes (CSV)", "JP")

topics_df = get_all_topics(mailto)
st.sidebar.write(f"Loaded {len(topics_df)} topics")
selected = st.sidebar.multiselect(
    "Select Topics",
    options=topics_df["id"],
    format_func=lambda x: topics_df.loc[topics_df.id == x, "display_name"].iloc[0]
)

year0, year1 = st.sidebar.slider("Year Range", 1990, 2025, (2000, 2025))

if st.sidebar.button("Run"):
    results = []
    for C in [c.strip() for c in countries.split(",")]:
        for tid in selected:
            name = topics_df.loc[topics_df.id == tid, "display_name"].iloc[0]

            # s(C,F,Y)
            s_df = fetch_grouped_counts(
                filter_params=(
                    f"type:article,"
                    f"authorships.countries:countries/{C},"
                    f"publication_year:{year0}-{year1},"
                    f"primary_topic.id:{tid}"
                ),
                group_by="publication_year",
                mailto=mailto
            ).rename(columns={"count": "s", "key": "year"})

            # t(C,Y)
            t_df = fetch_grouped_counts(
                filter_params=(
                    f"type:article,"
                    f"authorships.countries:countries/{C},"
                    f"publication_year:{year0}-{year1}"
                ),
                group_by="publication_year",
                mailto=mailto
            ).rename(columns={"count": "t", "key": "year"})

            # v(F,Y)
            v_df = fetch_grouped_counts(
                filter_params=(
                    f"type:article,"
                    f"publication_year:{year0}-{year1},"
                    f"primary_topic.id:{tid}"
                ),
                group_by="publication_year",
                mailto=mailto
            ).rename(columns={"count": "v", "key": "year"})

            # w(Y)
            w_df = fetch_grouped_counts(
                filter_params=f"type:article,publication_year:{year0}-{year1}",
                group_by="publication_year",
                mailto=mailto
            ).rename(columns={"count": "w", "key": "year"})

            # 結合＆AI計算
            df = (
                s_df.merge(t_df, on="year")
                    .merge(v_df, on="year")
                    .merge(w_df, on="year")
                    .assign(country=C, topic=name)
            )
            df["AI"] = (df["s"] / df["t"]) / (df["v"] / df["w"])
            results.append(df[["topic", "country", "year", "s", "t", "v", "w", "AI"]])

    ai_df = pd.concat(results, ignore_index=True)
    st.success("完了！🎉")
    st.dataframe(ai_df)

    csv = ai_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "activity_index.csv", "text/csv")
