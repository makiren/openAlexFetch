import streamlit as st
import requests
import pandas as pd


# ─── キャッシュ付きフェッチ関数 ───────────────────────────────
@st.cache_data
def fetch_json(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.json()


@st.cache_data
def get_all_topics(mailto):
    """
    OpenAlex /topics を page-based pagination で全件取得し、
    id, display_name, description を返す。
    要 email（mailto）必須。
    """
    df_list = []
    per_page = 200
    page = 1
    while True:
        url = (
            "https://api.openalex.org/topics"
            f"?select=id,display_name,description&per-page={per_page}&page={page}"
            f"&mailto={mailto}"
        )
        j = fetch_json(url)
        results = j.get("results", [])
        if not results:
            break
        df = pd.DataFrame(results)[["id", "display_name", "description"]]
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


# ─── UI ──────────────────────────────────────────────────────────────
st.sidebar.title("設定")

# 必須メール入力
mailto = st.sidebar.text_input("Email (必須)")
if not mailto:
    st.sidebar.warning("API利用のため、Email の入力が必須です。")
    st.stop()

countries = st.sidebar.text_input("Country Codes (CSV)", "JP")

# トピック一覧取得 (メール必須後)
topics_df = get_all_topics(mailto)
st.sidebar.write(f"Loaded {len(topics_df)} topics")

# トピック選択 UI
selected = st.sidebar.multiselect(
    "Select Topics",
    options=topics_df["id"],
    format_func=lambda x: topics_df.loc[topics_df.id == x, "display_name"].iloc[0]
)

# 選択トピックの Description 表示
if selected:
    with st.sidebar.expander("Topic Descriptions", expanded=False):
        for tid in selected:
            label = topics_df.loc[topics_df.id == tid, "display_name"].iloc[0]
            desc = topics_df.loc[topics_df.id == tid, "description"].iloc[0]
            st.markdown(f"**{label}**: {desc}")

# 年度レンジ
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
    # 年昇順ソート
    ai_df = ai_df.sort_values(["topic", "country", "year"])

    st.success("完了！🎉")

    # インフォメーション
    with st.expander("ℹ️ Info", expanded=False):
        st.markdown(
            """
This tool uses the OpenAlex public data and API to retrieve the number of papers published by topic and year. Polite Pool is required, and email address input is mandatory. The definitions of various indices calculated within the tool are based on the following paper.

Rousseau, Ronald, and Liying Yang. ‘Reflections on the Activity Index and Related Indicators’. Journal of Informetrics, vol. 6, no. 3, Elsevier BV, July 2012, pp. 413–421, doi:10.1016/j.joi.2012.01.004.

©️Ren Makishima (https://github.com/makiren)
"""
        )

    st.dataframe(ai_df)

    csv = ai_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "activity_index.csv", "text/csv")

# requirements.txt
# streamlit
# pandas
# requests
