import io, os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ------------------------------------------------------------------
# 캐싱된 데이터 로더
# ------------------------------------------------------------------
@st.cache_data
def load_bytes(file):
    return file.getvalue() if file is not None else b""


def read_csv_bytes(data: bytes) -> pd.DataFrame:
    """utf-8-sig → cp949 순으로 시도. 둘 다 실패 시 빈 DataFrame."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            pass
    return pd.DataFrame()


# ------------------------------------------------------------------
# 열 이름 표준화 (문서 예시 코드 그대로)
# ------------------------------------------------------------------
def std_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    rename = {}
    for c in df.columns:
        k = c.lower().replace(" ", "")
        if k in ("time", "categories", "시간", "날짜", "datetime", "date"):
            rename[c] = "time"
        elif k in ("temperature", "온도"):
            rename[c] = "temperature"
        elif k in ("humidity", "습도"):
            rename[c] = "humidity"
        elif k == "ph":
            rename[c] = "ph"
        elif k == "ec":
            rename[c] = "ec"
        elif "생중량" in k:
            rename[c] = "생중량"
        elif "잎" in k:
            rename[c] = "잎 수"
        elif "지상부" in k and "길이" in k:
            rename[c] = "지상부 길이"
        elif "지하부" in k and "길이" in k:
            rename[c] = "지하부 길이"
        elif "지상부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지상부 질량"
        elif "지하부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지하부 질량"
        elif "개체" in k:
            rename[c] = "개체번호"
    df = df.rename(columns=rename)

    # 숫자 아닌 열을 숫자로 변환 시도 (단위의 ',' 등 제거)
    for c in df.columns:
        if c in ("time", "개체번호"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            num = pd.to_numeric(
                df[c].astype(str).str.replace(",", "")
                .str.extract(r"(-?\d+\.?\d*)")[0],
                errors="coerce",
            )
            if num.notna().mean() >= 0.5:
                df[c] = num

    # 생중량 열이 없으면 지상부 질량 + 지하부 질량으로 계산
    if "생중량" not in df.columns and {"지상부 질량", "지하부 질량"} <= set(df.columns):
        df["생중량"] = df["지상부 질량"] + df["지하부 질량"]

    # 시간 열 파싱 (두 가지 형식 모두 지원)
    if "time" in df.columns:
        t = df["time"].astype(str).str.strip()
        parsed = pd.to_datetime(t, errors="coerce", format="mixed")
        bad = parsed.isna() & t.str.match(r"^\d{8}_\d{1,2}$")
        if bad.any():
            parts = t[bad].str.split("_", expand=True)
            parsed[bad] = pd.to_datetime(parts[0], format="%Y%m%d") + \
                          pd.to_timedelta(parts[1].astype(int), unit="h")
        df["time"] = parsed

    return df


# ------------------------------------------------------------------
# Plotly 한글 폰트 (공통)
# ------------------------------------------------------------------
KOR_FONT = dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif")


def apply_kor_font(fig: go.Figure) -> go.Figure:
    fig.update_layout(font=KOR_FONT)
    return fig


# ------------------------------------------------------------------
# CSV 다운로드 바이트 (한글 깨짐 방지: utf-8-sig)
# ------------------------------------------------------------------
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


# ------------------------------------------------------------------
# 앱 시작
# ------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="극지식물 생육 분석")
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🌱 극지식물 개체별 생육 차이 분석")

# ---- 사이드바 ----
env_file = st.sidebar.file_uploader("📁 환경 데이터 CSV", type="csv")
growth_file = st.sidebar.file_uploader("📁 생육 결과 데이터 CSV", type="csv")

growth_metrics = [
    "잎 수",
    "지상부 길이",
    "지하부 길이",
    "지상부 질량",
    "지하부 질량",
]
selected_metric = st.sidebar.selectbox(
    "📏 생육 측정 항목 선택",
    growth_metrics,
    index=0,
)

# 학교명: 업로드한 파일명 앞부분에서 추출 (하드코딩 금지)
school_name = "우리 학교"
for f in (env_file, growth_file):
    if f is not None:
        school_name = os.path.basename(f.name).split("_")[0].split(".")[0]
        break
st.sidebar.caption(f"🏫 학교명: {school_name}")

# ---- 맨 위에서 한 번만 읽기 (사이드바·탭 모두 재사용) ----
with st.spinner("데이터를 읽고 정리 중입니다…"):
    env_df = read_csv_bytes(load_bytes(env_file)) if env_file else pd.DataFrame()
    growth_df = read_csv_bytes(load_bytes(growth_file)) if growth_file else pd.DataFrame()

if not env_df.empty:
    env_df = std_cols(env_df)
if not growth_df.empty:
    growth_df = std_cols(growth_df)

# ==================================================================
# TAB 1 — 📖 실험 개요
# ==================================================================
tab1, tab2, tab3 = st.tabs(
    ["📖 실험 개요", "🥧 총 길이 비율 (원그래프)", "📊 개체별 누적 막대그래프"]
)

with tab1:
    try:
        with st.expander("📌 연구 배경 및 목적"):
            st.markdown(
                """
**연구 배경**
- 극지방은 낮은 온도와 짧은 생육 기간 때문에 식물이 자라는 데 제약이 큽니다.
- 같은 종이라도 개체마다 자라는 속도가 다를 수 있어, 개체별 차이를 수치로 비교해 보는 것이 중요합니다.

**연구 목적**
- 학교에서 재배 중인 극지식물 개체들의 **총 길이(지상부 길이 + 지하부 길이)** 를 기준으로
  - 지상부 길이 평균과 지하부 길이 평균이 총 길이 평균에서 차지하는 **비율(원그래프)**
  - 각 개체별로 지상부·지하부 길이에 따라 총 길이가 어떻게 달라지는지 **누적 막대그래프**
  를 통해 개체 간 차이를 파악합니다.

---
**통계 용어 간단 설명**
- **평균(mean)**: 모든 값을 더해 개체로 나눈 값. 집단의 대표적인 크기를 나타냅니다.
- **표준편차(standard deviation)**: 값들이 평균에서 얼마나 넓게 퍼져 있는지 나타냅니다. 클수록 개체 간 차이가 큽니다.
- **비율(ratio)**: 전체(최댓값 또는 합)에서 어떤 부분이 차지하는 크기를 %로 나타낸 것입니다.
"""
            )

        has_growth = not growth_df.empty and \
                     {"지상부 길이", "지하부 길이"} <= set(growth_df.columns)

        st.subheader("📋 데이터 요약")
        rows = []
        rows.append(["분석 대상", f"{school_name} 극지식물"])
        if has_growth:
            rows.append(["총 개체 수", f"{len(growth_df)}개체"])
        else:
            rows.append(["총 개체 수", "—"])
        if has_growth:
            meas_cols = [
                c for c in ["잎 수", "지상부 길이", "지하부 길이", "생중량"]
                if c in growth_df.columns
            ]
            rows.append(
                ["생육 측정 항목", ", ".join(meas_cols) if meas_cols else "—"]
            )
        else:
            rows.append(["생육 측정 항목", "업로드된 생육 데이터가 없습니다."])

        if not env_df.empty:
            env_cols = [
                c for c in ["temperature", "humidity", "ph", "ec"]
                if c in env_df.columns
            ]
            rows.append(
                ["환경 측정 항목", ", ".join(env_cols) if env_cols else "—"]
            )
        else:
            rows.append(["환경 측정 항목", "업로드된 환경 데이터가 없습니다."])

        summary_df = pd.DataFrame(rows, columns=["항목", "내용"])
        st.dataframe(summary_df, width="stretch")

        st.divider()
        st.subheader("📊 주요 지표")
        c1, c2, c3 = st.columns(3)

        if has_growth:
            shoot_vals = pd.to_numeric(
                growth_df["지상부 길이"], errors="coerce"
            ).dropna()
            root_vals = pd.to_numeric(
                growth_df["지하부 길이"], errors="coerce"
            ).dropna()
            if len(shoot_vals) >= 2 and len(root_vals) >= 2:
                c1.metric(
                    "평균 지상부 길이",
                    f"{shoot_vals.mean():.1f} mm",
                    delta=f"최소 {shoot_vals.min():.1f} / 최대 {shoot_vals.max():.1f}",
                )
                c2.metric(
                    "평균 지하부 길이",
                    f"{root_vals.mean():.1f} mm",
                    delta=f"최소 {root_vals.min():.1f} / 최대 {root_vals.max():.1f}",
                )
                total_mean = shoot_vals.mean() + root_vals.mean()
                c3.metric(
                    "평균 총 길이 (지상+지하)",
                    f"{total_mean:.1f} mm",
                    delta="지상부 + 지하부 길이 합",
                )
            else:
                st.info("지상부 길이·지하부 길이 데이터가 충분치 않습니다.")
        else:
            c1.metric("평균 지상부 길이", "—")
            c2.metric("평균 지하부 길이", "—")
            c3.metric("평균 총 길이", "생육 데이터 없음")

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ==================================================================
# TAB 2 — 🥧 총 길이 비율 (원그래프)
# ==================================================================
with tab2:
    try:
        st.subheader(
            "🥧 총 길이 평균 대비 지상부·지하부 길이 평균 비율 (원그래프)"
        )

        if not growth_df.empty and {"지상부 길이", "지하부 길이"} <= set(growth_df.columns):
            shoot = pd.to_numeric(growth_df["지상부 길이"], errors="coerce").dropna()
            root = pd.to_numeric(growth_df["지하부 길이"], errors="coerce").dropna()

            if len(shoot) >= 2 and len(root) >= 2:
                shoot_mean = float(shoot.mean())
                root_mean = float(root.mean())
                total_mean = shoot_mean + root_mean

                labels = ["지상부 길이 평균", "지하부 길이 평균"]
                values = [shoot_mean, root_mean]

                fig_pie = go.Figure()
                fig_pie.add_trace(
                    go.Pie(
                        labels=labels,
                        values=values,
                        hole=0.4,
                        marker=dict(colors=["forestgreen", "brown"]),
                        hovertemplate=(
                            "%{label}<br>"
                            "평균: %{value:.1f} mm<br>"
                            "비율: %{percent:.1f}%<extra></extra>"
                        ),
                    )
                )
                fig_pie.update_layout(
                    title=(
                        f"총 길이 평균({total_mean:.1f} mm) 중 "
                        f"지상부({shoot_mean:.1f} mm) · 지하부({root_mean:.1f} mm) 비율"
                    ),
                    width=600,
                    height=480,
                )
                apply_kor_font(fig_pie)
                st.plotly_chart(fig_pie, width="stretch")

                r_pct = shoot_mean / total_mean * 100
                root_pct = root_mean / total_mean * 100
                st.caption(
                    f"• 지상부 길이 평균 비율: {r_pct:.1f}%  "
                    f"• 지하부 길이 평균 비율: {root_pct:.1f}%"
                )
                st.caption(
                    "※ 평균값은 각 열에서 결측값을 제외한 값들의 평균입니다. "
                    "개체 수가 많으면 두 평균의 기준이 되는 개체 집합이 다를 수 있습니다."
                )
            else:
                st.info(
                    "지상부 길이 또는 지하부 길이의 유효 데이터가 부족해 "
                    "원그래프를 표시할 수 없습니다."
                )
        else:
            st.info(
                "생육 결과 CSV를 업로드하고 '지상부 길이', '지하부 길이' 열이 "
                "있어야 이 그래프를 표시할 수 있습니다."
            )

        st.divider()

        # 원본 테이블 + 다운로드  (key를 고유하게 부여 → 중복 ID 오류 방지)
        with st.expander("📄 생육 결과 데이터 원본 + CSV 다운로드"):
            if not growth_df.empty:
                display_g = growth_df.copy()
                for c in display_g.columns:
                    if pd.api.types.is_datetime64_any_dtype(display_g[c]):
                        display_g[c] = display_g[c].dt.strftime("%Y-%m-%d %H:%M")
                    elif pd.api.types.is_numeric_dtype(display_g[c]):
                        display_g[c] = display_g[c].round(2)
                st.dataframe(display_g, width="stretch")
                st.download_button(
                    label="⬇ 생육 결과 CSV 다운로드 (utf-8-sig)",
                    data=to_csv_bytes(display_g),
                    file_name=f"{school_name}_생육결과데이터.csv",
                    mime="text/csv",
                    key="download_growth_tab2",  # 고유 key — 중복 ID 방지
                )
            else:
                st.info("생육 데이터가 없어 원본을 표시할 수 없습니다.")

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ==================================================================
# TAB 3 — 📊 개체별 누적 막대그래프 (지상부 + 지하부)
# ==================================================================
with tab3:
    try:
        st.subheader(
            "📊 개체별 지상부 길이 · 지하부 길이 누적 막대그래프"
        )
        st.caption(
            "각 개체별로 지상부 길이(아래, 밝은 색)와 지하부 길이(위, 어두운 색)를 "
            "쌓아 올려 총 길이가 개체마다 얼마나 다른지 한눈에 볼 수 있습니다."
        )

        if not growth_df.empty and {"지상부 길이", "지하부 길이"} <= set(growth_df.columns):
            df_plot = growth_df[["개체번호", "지상부 길이", "지하부 길이"]].copy()
            df_plot["지상부 길이"] = pd.to_numeric(
                df_plot["지상부 길이"], errors="coerce"
            )
            df_plot["지하부 길이"] = pd.to_numeric(
                df_plot["지하부 길이"], errors="coerce"
            )
            df_plot = df_plot.dropna(subset=["지상부 길이", "지하부 길이"])
            df_plot = df_plot.sort_values(
                "지상부 길이", ascending=False
            ).reset_index(drop=True)

            if len(df_plot) >= 2:
                x_labels = [str(x) for x in df_plot["개체번호"].tolist()]

                fig_stack = go.Figure()
                fig_stack.add_trace(
                    go.Bar(
                        name="지상부 길이",
                        x=x_labels,
                        y=df_plot["지상부 길이"].tolist(),
                        marker_color="forestgreen",
                        hovertemplate=(
                            "개체: %{x}<br>"
                            "지상부 길이: %{y:.1f} mm<extra></extra>"
                        ),
                    )
                )
                fig_stack.add_trace(
                    go.Bar(
                        name="지하부 길이",
                        x=x_labels,
                        y=df_plot["지하부 길이"].tolist(),
                        marker_color="chocolate",
                        hovertemplate=(
                            "개체: %{x}<br>"
                            "지하부 길이: %{y:.1f} mm<extra></extra>"
                        ),
                    )
                )
                fig_stack.update_layout(
                    barmode="stack",
                    title="개체별 지상부 길이 + 지하부 길이 누적 (총 길이)",
                    xaxis_title="개체번호",
                    yaxis_title="길이 (mm)",
                    legend_title="구분",
                    width=900,
                    height=500,
                )
                apply_kor_font(fig_stack)
                st.plotly_chart(fig_stack, width="stretch")

                total_len = df_plot["지상부 길이"] + df_plot["지하부 길이"]
                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "평균 총 길이",
                    f"{float(total_len.mean()):.1f} mm",
                    delta=(
                        f"최소 {float(total_len.min()):.1f} "
                        f"/ 최대 {float(total_len.max()):.1f}"
                    ),
                )
                c2.metric(
                    "지상부 평균",
                    f"{float(df_plot['지상부 길이'].mean()):.1f} mm",
                )
                c3.metric(
                    "지하부 평균",
                    f"{float(df_plot['지하부 길이'].mean()):.1f} mm",
                )
            else:
                st.info(
                    "지상부 길이·지하부 길이 데이터가 충분하지 않아 "
                    "누적 막대그래프를 표시할 수 없습니다."
                )
        else:
            st.info(
                "생육 결과 CSV를 업로드하고 '지상부 길이', '지하부 길이' 열이 "
                "있어야 이 그래프를 표시할 수 있습니다."
            )

        st.divider()

        # 원본 테이블 + 다운로드  (key를 고유하게 부여 → 중복 ID 오류 방지)
        with st.expander("📄 생육 결과 데이터 원본 + CSV 다운로드"):
            if not growth_df.empty:
                display_g = growth_df.copy()
                for c in display_g.columns:
                    if pd.api.types.is_datetime64_any_dtype(display_g[c]):
                        display_g[c] = display_g[c].dt.strftime("%Y-%m-%d %H:%M")
                    elif pd.api.types.is_numeric_dtype(display_g[c]):
                        display_g[c] = display_g[c].round(2)
                st.dataframe(display_g, width="stretch")
                st.download_button(
                    label="⬇ 생육 결과 CSV 다운로드 (utf-8-sig)",
                    data=to_csv_bytes(display_g),
                    file_name=f"{school_name}_생육결과데이터.csv",
                    mime="text/csv",
                    key="download_growth_tab3",  # 고유 key — 중복 ID 방지
                )
            else:
                st.info("생육 데이터가 없어 원본을 표시할 수 없습니다.")

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")
