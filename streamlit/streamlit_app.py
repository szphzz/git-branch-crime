"""
Trees, Crime & Census in San Francisco — Streamlit app.

An interactive map with two views:
  1. Tree heat map over a choropleth of crime by police district (monthly).
  2. Tree heat map over census tracts (ACS socio-economic data).

Run:  streamlit run streamlit_app.py
Data from GCP
"""

import io
import json
import os

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import shapely
import streamlit as st
from google.cloud import storage
from shapely import wkt

from user_definition import bucket_name, project_id, service_account_file_path


# Constants
MONTHS = [f"2026-{m:02d}" for m in range(1, 9)]  # Jan – Aug 2026
MONTH_LABELS = {m: pd.Timestamp(m + "-01").strftime("%b %Y") for m in MONTHS}

# crime categories shown in the district breakdown: label -> (section, category)
CRIME_METRICS = {
    "Total": ("part1_total", "total_part1"),
    "Violent": ("part1_violent", "total_part1_violent"),
    "Property": ("part1_property", "total_part1_property"),
    "Firearm": ("firearm", "total_gun_violence_incidents"),
    "Domestic violence": ("domestic_violence", "domestic_violence_total"),
    "Other (misdemeanor assault)": ("other", "other_assaults_misdemeanor"),
}

ACS_MISSING = -666666666  # NA

CENSUS_METRICS = {
    "Median household income": ("median_income", "${:,.0f}"),
    "% below poverty": ("pct_poverty", "{:.1f}%"),
    "Trees per 1,000 residents": ("trees_per_1k", "{:.0f}"),
    "Number of trees": ("trees", "{:,.0f}"),
}

WARM = [(255, 247, 188), (254, 217, 118), (254, 153, 41), (217, 95, 14), (140, 45, 4)]
TREE_HEAT = [[198, 219, 239, 0], [158, 202, 225, 80], [107, 174, 214, 140],
             [66, 146, 198, 190], [33, 113, 181, 220], [8, 48, 107, 245]]
TREE_BLUE = "rgb(33,113,181)"
POINT_COLOR = "#d95f0e"
NO_DATA = [200, 200, 200, 120]

SF_VIEW = pdk.ViewState(latitude=37.758, longitude=-122.44, zoom=11.3, pitch=0)


# GCP
@st.cache_resource
def get_bucket():
    if service_account_file_path:
        client = storage.Client.from_service_account_json(service_account_file_path, project=project_id)
    else:
        client = storage.Client(project=project_id)
    return client.bucket(bucket_name)


@st.cache_data(ttl=3600, show_spinner=False)
def list_blob_names():
    return sorted(b.name for b in get_bucket().list_blobs())


def read_blob(name):
    return get_bucket().blob(name).download_as_bytes()


def find_blobs(match, label):
    names = [n for n in list_blob_names() if match(os.path.basename(n))]
    if not names:
        st.error(f"No {label} file found in bucket `{bucket_name}`.")
        st.stop()
    return names


def read_latest(match, label):
    return read_blob(find_blobs(match, label)[-1])


# Data loading & processing (all cached)
def acs_clean(s):
    s = pd.to_numeric(s, errors="coerce")
    return s.mask(s <= ACS_MISSING + 1)


def read_boundaries(prefix, label, **read_csv_kw):
    df = pd.read_csv(io.BytesIO(read_latest(lambda b: b.startswith(prefix), label)), **read_csv_kw)
    df["geometry"] = df["the_geom"].apply(wkt.loads)
    return df


@st.cache_data(ttl=86400, show_spinner="Loading police district boundaries…")
def load_police_districts():
    df = read_boundaries("Current_Police_Districts", "police district boundary")
    df["district"] = df["district"].str.upper().str.strip()
    return df[["district", "geometry"]]


@st.cache_data(ttl=86400, show_spinner="Loading census tract boundaries…")
def load_tracts():
    df = read_boundaries("Analysis_Neighborhoods", "census tract boundary", dtype={"tractce": str})
    df["tract"] = df["tractce"].str.zfill(6)
    return df.rename(columns={"name": "tract_name", "neighborhoods_analysis_boundaries": "neighborhood"})[
        ["tract", "tract_name", "neighborhood", "geometry"]]


@st.cache_data(ttl=86400, show_spinner="Loading census data…")
def load_census():
    raw = json.loads(read_latest(lambda b: "census-data" in b, "census"))
    df = pd.DataFrame(raw[1:], columns=raw[0])
    poverty = acs_clean(df["B17001_001E"]).replace(0, np.nan)
    return pd.DataFrame({
        "tract": df["tract"].str.zfill(6),
        "population": acs_clean(df["B01003_001E"]),
        "median_income": acs_clean(df["B19013_001E"]),
        "pct_poverty": 100 * acs_clean(df["B17001_002E"]) / poverty,
    })


@st.cache_data(ttl=86400, show_spinner="Loading crime data…")
def load_crime():
    names = find_blobs(lambda b: "crime-data" in b and b.endswith(".json"), "crime-data")
    df = pd.concat([pd.DataFrame(json.loads(read_blob(n))).assign(_file=n) for n in names],
                   ignore_index=True)
    # if a month was uploaded more than once, keep the newest file for it
    df = df[df["_file"] == df.groupby("report_period")["_file"].transform("max")]
    df = df[df["report_period"].isin(MONTHS)]
    df = df.assign(district=df["district"].str.upper().str.strip())

    wide = [
        df[(df["section"] == section) & (df["category"] == category)]
        .set_index(["report_period", "district"])[["current_month", "previous_month"]]
        .set_axis([label, f"{label} (prev)"], axis=1)
        for label, (section, category) in CRIME_METRICS.items()
    ]
    return pd.concat(wide, axis=1).reset_index()


@st.cache_data(ttl=86400, show_spinner="Loading street trees (large file)…")
def load_trees(_district_geoms, _tract_geoms, district_names, tract_ids):
    records = json.loads(read_latest(lambda b: "tree-data" in b, "tree"))
    trees = pd.DataFrame([(r.get("latitude"), r.get("longitude")) for r in records],
                         columns=["lat", "lon"])
    total_rows = len(trees)
    del records
    trees = trees.apply(pd.to_numeric, errors="coerce").dropna()
    # keep only points inside SF's bounding box
    trees = trees[trees.lat.between(37.6, 37.85) & trees.lon.between(-122.53, -122.35)]
    pts = shapely.points(trees["lon"].to_numpy(), trees["lat"].to_numpy())

    def count_within(geoms, labels):
        pt_i, poly_i = shapely.STRtree(list(geoms)).query(pts, predicate="within")
        # a point on a shared border could hit two polygons — count it once
        first = pd.Series(poly_i, index=pt_i).groupby(level=0).first()
        counts = first.value_counts().reindex(range(len(labels)), fill_value=0)
        return pd.Series(counts.to_numpy(), index=list(labels))

    heat = (trees.mul(2000).round().div(2000)
            .groupby(["lat", "lon"]).size().rename("weight").reset_index())
    return (heat, count_within(_district_geoms, district_names),
            count_within(_tract_geoms, tract_ids), {"mapped": len(trees), "total": total_rows})


# Helpers
def color_scale(values, vmin, vmax, alpha=210):
    """Map values onto the WARM ramp (linear interpolation); NaN -> NO_DATA."""
    vals = np.asarray(values, dtype=float)
    t = np.clip((vals - vmin) / ((vmax - vmin) or 1), 0, 1)
    stops = np.linspace(0, 1, len(WARM))
    rgb = np.column_stack([np.interp(t, stops, [c[k] for c in WARM]) for k in range(3)])
    return [NO_DATA if np.isnan(v) else [int(x) for x in c] + [alpha] for v, c in zip(vals, rgb)]


def geoms_to_polygon_rows(geoms, attrs, tolerance=0.00003):
    """Explode (multi)polygons into one row per polygon part for pydeck's
    PolygonLayer, carrying the attributes along."""
    rows = []
    for geom, attr in zip(geoms, attrs):
        geom = geom.simplify(tolerance, preserve_topology=True)
        for p in getattr(geom, "geoms", [geom]):
            rings = [p.exterior.coords, *(r.coords for r in p.interiors)]
            rows.append({**attr, "polygon": [[list(c) for c in ring] for ring in rings]})
    return rows


def legend(vmin, vmax, title, fmt):
    stops = ", ".join(f"rgb{c}" for c in WARM)
    st.markdown(
        f"""
        <div style="font-size:0.8rem;margin-top:-0.4rem">
          <b>{title}</b>
          <div style="height:10px;border-radius:3px;background:linear-gradient(to right,{stops});margin:4px 0"></div>
          <div style="display:flex;justify-content:space-between"><span>{fmt.format(vmin)}</span><span>{fmt.format(vmax)}</span></div>
          <div style="margin-top:4px"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;
               background:{TREE_BLUE};vertical-align:middle"></span> Tree density heat map (blue)</div>
        </div>""",
        unsafe_allow_html=True,
    )


def show_map(df, layer_id, key_field, tooltip, *legend_args):
    """Draw the choropleth + tree heat map and its legend, remember a clicked
    shape in st.session_state["sel_<key_field>"], and return the side column."""
    attrs = df.drop(columns="geometry").replace({np.nan: None}).to_dict("records")
    polygons = pdk.Layer(
        "PolygonLayer", id=layer_id, data=geoms_to_polygon_rows(df["geometry"], attrs),
        get_polygon="polygon", get_fill_color="fill", get_line_color=[80, 80, 80, 200],
        line_width_min_pixels=1, pickable=True, auto_highlight=True,
        highlight_color=[0, 0, 0, 70],  # darken on hover (no hue cue)
    )
    tree_heat = pdk.Layer(
        "HeatmapLayer", id="trees", data=heat, get_position=["lon", "lat"], get_weight="weight",
        radius_pixels=18, intensity=1, threshold=0.08, opacity=0.85,
        color_range=TREE_HEAT, aggregation="SUM",
    )
    deck = pdk.Deck(layers=[polygons, tree_heat], initial_view_state=SF_VIEW,
                    map_provider="carto", map_style="light", tooltip={"html": tooltip})

    col_map, col_info = st.columns([3, 1.3], gap="medium")
    with col_map:
        event = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object",
                                key=f"{layer_id}_map", height=620)
        try:
            objs = event.selection["objects"].get(layer_id, [])
        except (AttributeError, KeyError, TypeError):
            objs = []
        if objs:
            st.session_state[f"sel_{key_field}"] = objs[0][key_field]
        legend(*legend_args)
    return col_info


def subtitle(text):
    st.markdown(f"<div style='font-size:1.35rem;font-weight:500;opacity:0.8;"
                f"margin:-0.6rem 0 0.6rem'>{text}</div>", unsafe_allow_html=True)


def fmt_or_na(v, fmt):
    return "n/a" if v is None or pd.isna(v) else fmt.format(v)


# Main
st.set_page_config(page_title="SF Trees & Crime", page_icon="🌳", layout="wide")
st.title("🌳 Trees, Crime & Census in San Francisco")
st.caption("Street trees (DPW) · SFPD monthly crime reports · ACS census tract data")

districts = load_police_districts()
tracts = load_tracts()
census = load_census()
crime = load_crime()
heat, district_trees, tract_trees, tree_meta = load_trees(
    districts["geometry"], tracts["geometry"], tuple(districts["district"]), tuple(tracts["tract"]),
)

with st.sidebar:
    st.header("Map")
    view = st.radio("View", ["Crime by police district", "Census tracts"])
    if view == "Crime by police district":
        month = st.selectbox("Month", MONTHS, index=len(MONTHS) - 1, format_func=MONTH_LABELS.get)
        crime_metric = st.selectbox("Shade districts by", list(CRIME_METRICS), index=0)
    else:
        census_label = st.selectbox("Shade tracts by", list(CENSUS_METRICS), index=0)
    st.divider()
    st.caption(f"{tree_meta['mapped']:,} of {tree_meta['total']:,} trees have coordinates and are "
               "mapped. Click a district or tract on the map for details.")


# View 1 — crime by police district
if view == "Crime by police district":
    month_crime = crime[crime["report_period"] == month].set_index("district")
    all_district_vals = crime.loc[crime["district"] != "CITYWIDE", crime_metric]
    vmin, vmax = float(all_district_vals.min()), float(all_district_vals.max())

    dist = districts.assign(
        trees=districts["district"].map(district_trees).fillna(0).astype(int),
        name=districts["district"].str.title(),
    ).join(month_crime[list(CRIME_METRICS)], on="district")
    dist["fill"] = color_scale(dist[crime_metric], vmin, vmax)
    dist["metric_value"] = dist[crime_metric].map(lambda v: fmt_or_na(v, "{:,.0f}"))

    col_info = show_map(
        dist, "districts", "district",
        f"<b>{{name}}</b><br/>{crime_metric}: {{metric_value}}<br/>Trees: {{trees}}",
        vmin, vmax, f"{crime_metric} crimes per month (same scale for all months)", "{:,.0f}",
    )

    sel = st.session_state.get("sel_district")
    has_sel = bool(sel) and sel in month_crime.index
    with col_info:
        st.subheader(f"{sel.title()} District" if has_sel else "Citywide")
        subtitle(MONTH_LABELS[month])
        if not has_sel:
            st.caption("Click a district for its statistics")
        n_trees = district_trees.get(sel, 0) if has_sel else district_trees.sum()
        row = month_crime.loc[sel if has_sel else "CITYWIDE"]

        st.metric("🌳 Street trees", f"{int(n_trees):,}")
        cols = st.columns(2)
        for i, label in enumerate(CRIME_METRICS):
            cur, prev = row[label], row[f"{label} (prev)"]
            delta = None if pd.isna(prev) else f"{int(cur - prev):+,} vs prev. month"
            cols[i % 2].metric(label.replace(" (misdemeanor assault)", ""), f"{int(cur):,}",
                               delta=delta, delta_color="off")
        st.caption("Violent + property = total (SFPD Part I). Firearm = gun-violence incidents; "
                   "Other = misdemeanor assaults.")

    # scatterplot for high level overview
    st.subheader("Do SF districts with more trees have less crime?")
    scat = dist[["name", "trees", "Total"]].dropna()
    scat["selected"] = scat["name"].str.upper() == (sel or "")
    r = scat["trees"].corr(scat["Total"])
    base = alt.Chart(scat).encode(
        x=alt.X("trees:Q", title="Street trees in district", scale=alt.Scale(zero=False)),
        y=alt.Y("Total:Q", title=f"Total crimes, {MONTH_LABELS[month]}", scale=alt.Scale(zero=False)),
    )
    points = base.mark_circle(opacity=0.9, stroke="black", color=POINT_COLOR).encode(
        size=alt.condition("datum.selected", alt.value(260), alt.value(110)),
        strokeWidth=alt.condition("datum.selected", alt.value(2), alt.value(0)),
        tooltip=[alt.Tooltip("name:N", title="District"),
                 alt.Tooltip("trees:Q", title="Trees", format=","),
                 alt.Tooltip("Total:Q", title="Total crimes", format=",")],
    )
    labels = base.mark_text(align="left", dx=9, fontSize=12).encode(text="name:N")
    trend_line = base.transform_regression("trees", "Total").mark_line(
        color=TREE_BLUE, strokeDash=[6, 4], strokeWidth=2)
    st.altair_chart((trend_line + points + labels).properties(height=380), use_container_width=True)
    st.caption(
        f"Pearson r = {r:.2f} across 10 police districts ({MONTH_LABELS[month]})."
        f"Districts with more street trees tend to have {'more' if r > 0 else 'fewer'} "
        "total crimes this month, but with only 10 districts — which differ a lot in size, "
        "population and land use — this is a loose pattern, not evidence that trees affect crime."
    )

# View 2 — census tracts
else:
    col_name, fmt = CENSUS_METRICS[census_label]
    tr = tracts.merge(census, on="tract", how="left")
    tr["trees"] = tr["tract"].map(tract_trees).fillna(0).astype(int)
    tr["trees_per_1k"] = 1000 * tr["trees"] / tr["population"].where(tr["population"] >= 100)
    vals = tr[col_name]
    vmin, vmax = float(vals.quantile(0.02)), float(vals.quantile(0.98))  # trim outliers
    tr["fill"] = color_scale(vals, vmin, vmax, alpha=200)
    tr["name"] = "Tract " + tr["tract_name"].astype(str)
    tr["metric_value"] = vals.map(lambda v: fmt_or_na(v, fmt))

    col_info = show_map(
        tr, "tracts", "tract",
        f"<b>{{name}}</b> · {{neighborhood}}<br/>{census_label}: {{metric_value}}<br/>Trees: {{trees}}",
        vmin, vmax, f"{census_label} (gray = no data)", fmt,
    )

    with col_info:
        match = tr[tr["tract"] == st.session_state.get("sel_tract")]
        if len(match):
            r = match.iloc[0]
            st.subheader(f"Census Tract {r['tract_name']}")
            subtitle(r["neighborhood"])
            st.metric("🌳 Street trees", f"{r['trees']:,}")
            st.metric("Median household income", fmt_or_na(r["median_income"], "${:,.0f}"))
            c1, c2 = st.columns(2)
            c1.metric("Below poverty", fmt_or_na(r["pct_poverty"], "{:.1f}%"))
            c2.metric("Population", fmt_or_na(r["population"], "{:,.0f}"))
            c1.metric("Trees / 1k residents", fmt_or_na(r["trees_per_1k"], "{:.0f}"))
            med = tr[["median_income", "pct_poverty", "trees_per_1k"]].median()
            st.caption(
                f"Median SF tract: income {fmt_or_na(med['median_income'], '${:,.0f}')}, "
                f"poverty {med['pct_poverty']:.1f}%, {med['trees_per_1k']:.0f} trees per 1k residents."
            )
        else:
            st.subheader("Citywide")
            subtitle("All census tracts")
            st.caption("Click a census tract for its statistics")
            pop = tr["population"].sum()
            pov = 100 * (tr["pct_poverty"] / 100 * tr["population"]).sum() / pop
            st.metric("🌳 Street trees", f"{int(tract_trees.sum()):,}")
            st.metric("Median tract household income",
                      fmt_or_na(tr["median_income"].median(), "${:,.0f}"))
            st.metric("Population (ACS)", f"{pop:,.0f}")