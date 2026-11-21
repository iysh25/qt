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
def load_env_bytes(file):
    return file.getvalue() if file is not None else b""


@st.cache_data
def load_growth_bytes(file):
    return file.getvalue() if file is not None else b""


def _try_read_csv(data: bytes) -> pd.DataFrame:
    """utf-8-sig → cp949 순으로 시도. 둘 다 실패하면 빈 DataFrame."""
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

    if "생중량" not in df.columns and {"지상부 질량", "지하부 질량"} <= set(df.columns):
        df["생중량"] = df["지상부 질량"] + df["지하부 질량"]

    if "time" in df.columns:
        t = df["time"].astype(str).str.strip()
        parsed = pd.to_datetime(t, errors="coerce", format="mixed")
        bad = parsed.isna() & t.str.match(r"^\d{8}_\d{1,2}$")
        if bad.any():
            parts = t[bad].str.split("_", expand=True)
            parsed[bad] = pd.to_datetime(
                parts[0], format="%Y%m%d"
            ) + pd.to_timedelta(parts[1].astype(int), unit="h")
        df["time"] = parsed

    return df


# ------------------------------------------------------------------
# 공유: Plotly 한글 폰트 설정
# ------------------------------------------------------------------
PLOT_FONT = dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif")


def set_plot_font(fig: go.Figure) -> go.Figure:
    fig.update_layout(font=PLOT_FONT)
    return fig


# ------------------------------------------------------------------
# 다운로드용 CSV 바이트 (utf-8-sig → 한글 깨짐 방지)
# ------------------------------------------------------------------
def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    # 개체번호가 float로 표시되는 것을 막기 위해 문자열 열은 그대로 유지
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

st.title("🌱 우리 학교 극지식물 개체별 생육 차이 분석")

# ---- 사이드바: 업로드 + 측정 항목 ----
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
    help="개체별로 비교할 생육 항목을 고릅니다.",
)

# 학교명: 업로드한 파일명 앞부분에서 추출 (하드코딩 금지)
school_name = "우리 학교"
if env_file is not None:
    raw = os.path.basename(env_file.name)
    school_name = raw.split("_")[0].split(".")[0]
elif growth_file is not None:
    raw = os.path.basename(growth_file.name)
    school_name = raw.split("_")[0].split(".")[0]

st.sidebar.caption(f"🏫 학교명: {school_name}")

# ---- 맨 위에서 한 번만 읽기 (사이드바·탭 모두 재사용) ----
env_bytes = load_env_bytes(env_file)
growth_bytes = load_growth_bytes(growth_file)

env_df = _try_read_csv(env_bytes) if env_bytes else pd.DataFrame()
growth_df = _try_read_csv(growth_bytes) if growth_bytes else pd.DataFrame()

if not env_df.empty:
    env_df = std_cols(env_df)
if not growth_df.empty:
    growth_df = std_cols(growth_df)

# ==================================================================
# TAB 1 — 📖 실험 개요
# ==================================================================
tab1, tab2, tab3 = st.tabs(
    ["📖 실험 개요", "🌡️ 환경 데이터", "📊 생육 결과"]
)

with tab1:
    try:
        with st.expander("📌 연구 배경 및 목적"):
            st.markdown(
                f"""
**연구 배경**
- 극지방은 낮은 온도와 짧은 생육 기간 때문에 식물이 자라는 데 제약이 큽니다.
- 같은 종이라도 개체마다 자라는 속도가 다를 수 있어, 개체별 차이를 수치로 비교해 보는 것이 중요합니다.

**연구 목적**
- {school_name}에서 재배 중인 극지식물 개체들의 **생중량(fresh weight)** 과 잎 수·길이 등 생육 지표를 비교하여 개체 간 차이를 파악합니다.
- 환경 데이터(온도·습도·pH·EC)와 함께 생육 결과를 살펴, 어떤 환경에서 잘 자라는지 경향을 이해합니다.

---
**주요 통계 용어 간단 설명**
- **평균(mean)**: 모든 값을 더해 개수로 나눈 값. 집단의 대표적인 크기를 나타냅니다.
- **표준편차(standard deviation)**: 값들이 평균에서 얼마나 넓게 퍼져 있는지 나타내는 값입니다. 클수록 개체 간 차이가 큽니다.
- **변동계수(CV, coefficient of variation)**: 표준편차를 평균으로 나눈 값(백분율). 평균이 다른 집단끼리도 흩어진 정도를 비교할 수 있습니다.
- **상관계수(Pearson r)**: 두 변수가 함께 움직이는 정도를 −1 ∼ +1 사이 숫자로 나타냅니다. +1에 가까울수록 함께 증가, −1에 가까울수록 반대 방향으로 움직입니다.
"""
            )

        # 데이터 요약 표
        st.subheader("📋 데이터 요약")
        has_env = not env_df.empty and {"time", "temperature"} <= set(env_df.columns)
        has_growth = not growth_df.empty and "생중량" in growth_df.columns

        rows = []
        rows.append(["분석 대상", f"{school_name} 극지식물"])
        if has_growth:
            rows.append(["총 개체 수", f"{len(growth_df)}개체"])
        else:
            rows.append(["총 개체 수", "—"])
        if has_env and "time" in env_df.columns and env_df["time"].notna().any():
            t_min = env_df["time"].min()
            t_max = env_df["time"].max()
            rows.append(
                [
                    "측정 기간",
                    f"{t_min.strftime('%Y-%m-%d') if pd.notna(t_min) else '?'}"
                    f" ~ "
                    f"{t_max.strftime('%Y-%m-%d') if pd.notna(t_max) else '?'}",
                ]
            )
        else:
            rows.append(["측정 기간", "—"])
        if has_growth:
            meas_cols = [
                c for c in ["잎 수", "지상부 길이", "지하부 길이", "생중량"]
                if c in growth_df.columns
            ]
            rows.append(["생육 측정 항목", ", ".join(meas_cols) if meas_cols else "—"])
        if has_env:
            env_cols = [
                c for c in ["temperature", "humidity", "ph", "ec"]
                if c in env_df.columns
            ]
            rows.append(["환경 측정 항목", ", ".join(env_cols) if env_cols else "—"])
        else:
            rows.append(["환경 측정 항목", "업로드된 환경 데이터가 없습니다."])

        summary_df = pd.DataFrame(rows, columns=["항목", "내용"])
        st.dataframe(summary_df, width="stretch", use_container_width=False)

        st.divider()

        # 주요 지표 카드 4개
        st.subheader("📊 주요 지표")
        m1, m2, m3, m4 = st.columns(4)

        total = len(growth_df) if has_growth else 0
        m1.metric("총 개체수", f"{total}개체" if total else "—")

        if has_env and "temperature" in env_df.columns:
            t_vals = pd.to_numeric(env_df["temperature"], errors="coerce").dropna()
            if len(t_vals) >= 2:
                m2.metric(
                    "평균 온도",
                    f"{t_vals.mean():.1f} °C",
                    delta=f"최소 {t_vals.min():.1f} / 최대 {t_vals.max():.1f}",
                )
            else:
                m2.metric("평균 온도", "—", delta="데이터 부족")
        else:
            m2.metric("평균 온도", "환경 데이터 없음", delta=None)

        if has_env and "humidity" in env_df.columns:
            h_vals = pd.to_numeric(env_df["humidity"], errors="coerce").dropna()
            if len(h_vals) >= 2:
                m3.metric(
                    "평균 습도",
                    f"{h_vals.mean():.1f} %",
                    delta=f"최소 {h_vals.min():.1f} / 최대 {h_vals.max():.1f}",
                )
            else:
                m3.metric("평균 습도", "—", delta="데이터 부족")
        else:
            m3.metric("평균 습도", "환경 데이터 없음", delta=None)

        if has_growth and "생중량" in growth_df.columns:
            fw = pd.to_numeric(growth_df["생중량"], errors="coerce").dropna()
            if len(fw) >= 2:
                m4.metric(
                    "평균 생중량",
                    f"{fw.mean():.1f} g",
                    delta=f"CV = {fw.std()/fw.mean()*100:.1f}%",
                )
            else:
                m4.metric("평균 생중량", "—", delta="데이터 부족")
        else:
            m4.metric("평균 생중량", "생육 데이터 없음", delta=None)

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ==================================================================
# TAB 2 — 🌡️ 환경 데이터
# ==================================================================
with tab2:
    try:
        if env_df.empty or not {"time"} <= set(env_df.columns):
            st.info("🌡️ 환경 데이터 CSV를 사이드바에 업로드하면 이 탭의 내용이 표시됩니다.")
        else:
            st.subheader("🌡️ 환경 데이터 요약")
            st.caption(f"출처: {school_name} 환경 데이터")

            # 평균·최소·최대 표 (열이 있는 것만)
            num_cols = [
                c for c in ["temperature", "humidity", "ph", "ec"]
                if c in env_df.columns
            ]
            if num_cols:
                stats = []
                for c in num_cols:
                    s = pd.to_numeric(env_df[c], errors="coerce").dropna()
                    if len(s) >= 1:
                        stats.append(
                            {
                                "측정 항목": c,
                                "평균": round(float(s.mean()), 2),
                                "최소": round(float(s.min()), 2),
                                "최대": round(float(s.max()), 2),
                                "표본 수": int(len(s)),
                            }
                        )
                if stats:
                    st.dataframe(pd.DataFrame(stats), width="stretch")
                else:
                    st.info("계산 가능한 숫자가 없어 환경 요약을 표시하지 못했습니다.")
            else:
                st.info("온도·습도·pH·EC 열이 모두 없어 환경 요약 표를 표시할 수 없습니다.")

            st.divider()

            st.subheader("📈 날짜별 시계열 (일별 평균)")

            if "time" in env_df.columns:
                env_df["date"] = env_df["time"].dt.date
                daily = env_df.groupby("date").mean(numeric_only=True).reset_index()
                daily["date"] = pd.to_datetime(daily["date"])

                # 온도
                if "temperature" in daily.columns:
                    fig_t = px.line(
                        daily,
                        x="date",
                        y="temperature",
                        markers=True,
                        title="일별 평균 온도",
                        labels={"temperature": "온도 (°C)", "date": "날짜"},
                    )
                    set_plot_font(fig_t)
                    fig_t.update_layout(xaxis_title="날짜", yaxis_title="온도 (°C)")
                    st.plotly_chart(fig_t, width="stretch")

                # 습도
                if "humidity" in daily.columns:
                    fig_h = px.line(
                        daily,
                        x="date",
                        y="humidity",
                        markers=True,
                        title="일별 평균 습도",
                        labels={"humidity": "습도 (%)", "date": "날짜"},
                    )
                    set_plot_font(fig_h)
                    fig_h.update_layout(xaxis_title="날짜", yaxis_title="습도 (%)")
                    st.plotly_chart(fig_h, width="stretch")

                # pH·EC (열이 있을 때만)
                env_has_extra = {"ph", "ec"} & set(env_df.columns)
                if env_has_extra:
                    sub_cols = [c for c in ["ph", "ec"] if c in daily.columns]
                    if sub_cols:
                        fig_pe = make_subplots(
                            rows=1, cols=len(sub_cols),
                            subplot_titles=["일별 평균 pH", "일별 평균 EC"],
                        )
                        for i, c in enumerate(sub_cols, start=1):
                            fig_p = px.line(
                                daily, x="date", y=c,
                                markers=True,
                                labels={c: c.upper(), "date": "날짜"},
                            )
                            for trace in fig_p.data:
                                trace.name = f"{c}"
                                fig_pe.add_trace(trace, row=1, col=i)
                        fig_pe.update_layout(
                            title="일별 pH · EC 변화",
                            xaxis_title="날짜",
                            xaxis2_title="날짜",
                            showlegend=False,
                        )
                        set_plot_font(fig_pe)
                        st.plotly_chart(fig_pe, width="stretch")

            st.divider()

            with st.expander("📄 환경 데이터 원본 테이블 + CSV 다운로드"):
                st.caption("업로드된 환경 데이터 원문입니다.")
                display_df = env_df.copy()
                for c in display_df.columns:
                    if pd.api.types.is_datetime64_any_dtype(display_df[c]):
                        display_df[c] = display_df[c].dt.strftime("%Y-%m-%d %H:%M")
                    elif pd.api.types.is_numeric_dtype(display_df[c]):
                        display_df[c] = display_df[c].round(2)
                st.dataframe(display_df, width="stretch")
                st.download_button(
                    label="⬇ 환경 데이터 CSV 다운로드 (utf-8-sig)",
                    data=df_to_csv_bytes(display_df),
                    file_name=f"{school_name}_환경데이터.csv",
                    mime="text/csv",
                )
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ==================================================================
# TAB 3 — 📊 생육 결과
# ==================================================================
with tab3:
    try:
        if growth_df.empty or "생중량" not in growth_df.columns:
            st.info("📊 생육 결과 CSV를 사이드바에 업로드하면 이 탭의 내용이 표시됩니다.")
        else:
            fw_vals = pd.to_numeric(growth_df["생중량"], errors="coerce").dropna()
            has_fw = len(fw_vals) >= 2
            has_leaves = "잎 수" in growth_df.columns
            has_shoot = "지상부 길이" in growth_df.columns

            # ---- 🥇 핵심 결과 카드 ----
            st.subheader("🥇 핵심 결과")
            c1, c2, c3 = st.columns(3)
            if has_fw:
                mean_fw = float(fw_vals.mean())
                max_idx = fw_vals.idxmax()
                min_idx = fw_vals.idxna()
                # 개체번호는 원래 값 그대로
                max_label = growth_df.loc[max_idx, "개체번호"] if "개체번호" in growth_df.columns else "—"
                min_label = growth_df.loc[min_idx, "개체번호"] if "개체번호" in growth_df.columns else "—"
                c1.metric("평균 생중량", f"{mean_fw:.1f} g")
                c2.metric("최대 생중량 개체", f"#{max_label}  {fw_vals.max():.1f} g")
                c3.metric("최소 생중량 개체", f"#{min_label}  {fw_vals.min():.1f} g")
            else:
                st.info("생중량 데이터가 없어 핵심 결과 카드를 표시할 수 없습니다.")

            st.divider()

            # ---- 개체별 생육 비교 (막대 그래프) ----
            st.subheader("📊 개체별 생육 비교")

            # 같은 모양의 막대 그래프를 만드는 재사용 함수
            def bar_metric(col_name, title, y_label, color):
                if col_name not in growth_df.columns:
                    st.info(f"{title}을(를) 그릴 열이 없어 표시하지 못했습니다.")
                    return None
                s = pd.to_numeric(growth_df[col_name], errors="coerce").dropna()
                if len(s) < 2:
                    st.info(f"{title} 값이 부족해 그래프를 표시할 수 없습니다.")
                    return None
                tmp = growth_df.loc[s.index, ["개체번호", col_name]].copy()
                tmp[col_name] = pd.to_numeric(tmp[col_name], errors="coerce")
                tmp = tmp.sort_values(col_name, ascending=False)
                fig = px.bar(
                    tmp,
                    x="개체번호",
                    y=col_name,
                    title=title,
                    labels={"개체번호": "개체번호", col_name: y_label},
                    color=col_name,
                    color_continuous_scale=color,
                    hover_data={"개체번호": True, col_name: ":,.1f"},
                )
                set_plot_font(fig)
                fig.update_layout(
                    xaxis_title="개체번호",
                    yaxis_title=y_label,
                    coloraxis_showscale=False,
                )
                return fig

            fig_fw_bar = bar_metric(
                "생중량",
                "⭐ 평균 생중량 (개체별)",
                "생중량 (g)",
                "Viridis",
            )
            if fig_fw_bar is not None:
                st.plotly_chart(fig_fw_bar, width="stretch")

            fig_leaves = bar_metric(
                "잎 수",
                "평균 잎 수 (개체별)",
                "잎 수 (장)",
                "Viridis",
            )
            if fig_leaves is not None:
                st.plotly_chart(fig_leaves, width="stretch")

            fig_shoot = bar_metric(
                "지상부 길이",
                "평균 지상부 길이 (개체별)",
                "지상부 길이 (mm)",
                "Viridis",
            )
            if fig_shoot is not None:
                st.plotly_chart(fig_shoot, width="stretch")

            fig_root = bar_metric(
                "지하부 길이",
                "평균 지하부 길이 (개체별)",
                "지하부 길이 (mm)",
                "Viridis",
            )
            if fig_root is not None:
                st.plotly_chart(fig_root, width="stretch")

            st.divider()

            # ---- 생중량 분포 (박스플롯 / 바이올린 플롯) ----
            st.subheader("📦 생중량 분포")
            if has_fw:
                dist_df = growth_df.loc[fw_vals.index, ["개체번호", "생중량"]].copy()
                dist_df["생중량"] = pd.to_numeric(dist_df["생중량"], errors="coerce")
                dist_df = dist_df.dropna(subset=["생중량"])

                fig_box = px.box(
                    dist_df,
                    y="생중량",
                    title="생중량 분포 (박스플롯: 상자 안은 중간 50% 범위)",
                    labels={"생중량": "생중량 (g)"},
                )
                set_plot_font(fig_box)
                fig_box.update_layout(yaxis_title="생중량 (g)")
                st.plotly_chart(fig_box, width="stretch")

                fig_violin = px.violin(
                    dist_df,
                    y="생중량",
                    title="생중량 분포 (바이올린 플롯: 분포 밀도 형태)",
                    labels={"생중량": "생중량 (g)"},
                    box=True,
                    points="outliers",
                )
                set_plot_font(fig_violin)
                fig_violin.update_layout(yaxis_title="생중량 (g)")
                st.plotly_chart(fig_violin, width="stretch")
            else:
                st.info("생중량 데이터가 충분하지 않아 분포 그래프를 표시할 수 없습니다.")

            st.divider()

            # ---- 상관관계 분석 (산점도 + 추세선) ----
            st.subheader("🔗 상관관계 분석")

            if has_leaves and has_fw:
                lr = growth_df[["잎 수", "생중량"]].dropna()
                lr["잎 수"] = pd.to_numeric(lr["잎 수"], errors="coerce")
                lr["생중량"] = pd.to_numeric(lr["생중량"], errors="coerce")
                lr = lr.dropna()
                if len(lr) >= 2:
                    x_l, y_l = lr["잎 수"], lr["생중량"]
                    r_l = float(np.corrcoef(x_l, y_l)[0, 1])
                    m_l, b_l = np.polyfit(x_l, y_l, 1)
                    x_line = np.linspace(x_l.min(), x_l.max(), 100)
                    y_line = m_l * x_line + b_l

                    fig_l = go.Figure()
                    fig_l.add_trace(
                        go.Scatter(
                            x=x_l,
                            y=y_l,
                            mode="markers",
                            name="데이터",
                            marker=dict(size=8, color="royalblue"),
                            hovertemplate="잎 수: %{x}장<br>생중량: %{y:.1f}g<extra></extra>",
                        )
                    )
                    fig_l.add_trace(
                        go.Scatter(
                            x=x_line,
                            y=y_line,
                            mode="lines",
                            name=f"추세선 (r = {r_l:.2f})",
                            line=dict(color="crimson", width=2),
                        )
                    )
                    fig_l.update_layout(
                        title=f"잎 수 vs 생중량  (r = {r_l:.2f})",
                        xaxis_title="잎 수 (장)",
                        yaxis_title="생중량 (g)",
                        width=700,
                        height=420,
                    )
                    set_plot_font(fig_l)
                    st.plotly_chart(fig_l, width="stretch")
                    st.caption(
                        f"상관계수 r = {r_l:.2f}  — "
                        + ("강한 양의 상관" if r_l > 0.7 else
                           "중간 정도의 양의 상관" if r_l > 0.4 else
                           "약한 상관 또는 무상관")
                    )
                else:
                    st.info("잎 수와 생중량 데이터가 충분하지 않아 상관관계를 계산할 수 없습니다.")
            else:
                st.info("잎 수 열이 없거나 생중량 데이터가 없어 잎 수 상관 그래프를 표시할 수 없습니다.")

            if has_shoot and has_fw:
                sr = growth_df[["지상부 길이", "생중량"]].dropna()
                sr["지상부 길이"] = pd.to_numeric(sr["지상부 길이"], errors="coerce")
                sr["생중량"] = pd.to_numeric(sr["생중량"], errors="coerce")
                sr = sr.dropna()
                if len(sr) >= 2:
                    x_s, y_s = sr["지상부 길이"], sr["생중량"]
                    r_s = float(np.corrcoef(x_s, y_s)[0, 1])
                    m_s, b_s = np.polyfit(x_s, y_s, 1)
                    x_line_s = np.linspace(x_s.min(), x_s.max(), 100)
                    y_line_s = m_s * x_line_s + b_s

                    fig_s = go.Figure()
                    fig_s.add_trace(
                        go.Scatter(
                            x=x_s,
                            y=y_s,
                            mode="markers",
                            name="데이터",
                            marker=dict(size=8, color="darkorange"),
                            hovertemplate="지상부 길이: %{x:.0f}mm<br>생중량: %{y:.1f}g<extra></extra>",
                        )
                    )
                    fig_s.add_trace(
                        go.Scatter(
                            x=x_line_s,
                            y=y_line_s,
                            mode="lines",
                            name=f"추세선 (r = {r_s:.2f})",
                            line=dict(color="crimson", width=2),
                        )
                    )
                    fig_s.update_layout(
                        title=f"지상부 길이 vs 생중량  (r = {r_s:.2f})",
                        xaxis_title="지상부 길이 (mm)",
                        yaxis_title="생중량 (g)",
                        width=700,
                        height=420,
                    )
                    set_plot_font(fig_s)
                    st.plotly_chart(fig_s, width="stretch")
                    st.caption(
                        f"상관계수 r = {r_s:.2f}  — "
                        + ("강한 양의 상관" if r_s > 0.7 else
                           "중간 정도의 양의 상관" if r_s > 0.4 else
                           "약한 상관 또는 무상관")
                    )
                else:
                    st.info("지상부 길이와 생중량 데이터가 충분하지 않아 상관관계를 계산할 수 없습니다.")
            else:
                st.info("지상부 길이 열이 없거나 생중량 데이터가 없어 지상부 길이 상관 그래프를 표시할 수 없습니다.")

            st.divider()

            # ---- 상위 25% vs 하위 25% 비교 ----
            st.subheader(f"🏆 상위 25% vs 하위 25% ({selected_metric})")

            if has_fw and selected_metric in growth_df.columns:
                ranked = growth_df[["개체번호", "생중량", selected_metric]].copy()
                ranked["생중량"] = pd.to_numeric(ranked["생중량"], errors="coerce")
                ranked[selected_metric] = pd.to_numeric(
                    ranked[selected_metric], errors="coerce"
                )
                ranked = ranked.dropna(subset=["생중량", selected_metric])
                ranked = ranked.sort_values("생중량", ascending=False).reset_index(drop=True)

                n = len(ranked)
                if n >= 4:
                    hi_n = max(1, int(n * 0.25))
                    lo_n = max(1, int(n * 0.25))
                    top = ranked.head(hi_n)
                    bottom = ranked.tail(lo_n)

                    rows = []
                    rows.append(
                        {
                            "구분": "상위 25%",
                            "개체번호": ", ".join(
                                str(x) for x in top["개체번호"].tolist()
                            ),
                            selected_metric: round(
                                float(top[selected_metric].mean()), 2
                            ),
                            "생중량(평균)": round(float(top["생중량"].mean()), 2),
                        }
                    )
                    rows.append(
                        {
                            "구분": "하위 25%",
                            "개체번호": ", ".join(
                                str(x) for x in bottom["개체번호"].tolist()
                            ),
                            selected_metric: round(
                                float(bottom[selected_metric].mean()), 2
                            ),
                            "생중량(평균)": round(float(bottom["생중량"].mean()), 2),
                        }
                    )
                    comp_df = pd.DataFrame(rows)
                    st.dataframe(comp_df, width="stretch", use_container_width=False)
                    st.caption(
                        f"생중량이 큰 상위 {hi_n}개체와 작은 하위 {lo_n}개체의 "
                        f"{selected_metric} 평균을 비교했습니다."
                    )

                    fig_comp = go.Figure()
                    fig_comp.add_trace(
                        go.Bar(
                            name="상위 25%",
                            x=["상위 25%"],
                            y=[float(top[selected_metric].mean())],
                            marker_color="mediumseagreen",
                        )
                    )
                    fig_comp.add_trace(
                        go.Bar(
                            name="하위 25%",
                            x=["하위 25%"],
                            y=[float(bottom[selected_metric].mean())],
                            marker_color="lightcoral",
                        )
                    )
                    fig_comp.update_layout(
                        title=f"{selected_metric} 평균: 상위 25% vs 하위 25%",
                        xaxis_title="",
                        yaxis_title=f"{selected_metric} 평균",
                        barmode="group",
                    )
                    set_plot_font(fig_comp)
                    st.plotly_chart(fig_comp, width="stretch")
                else:
                    st.info("개체 수가 너무 적어 상위·하위 25%를 나눌 수 없습니다.")
            else:
                st.info("생중량 또는 선택한 측정 항목 데이터가 없어 비교표를 표시할 수 없습니다.")

            st.divider()

            # ---- 원본 테이블 + CSV 다운로드 ----
            with st.expander("📄 생육 결과 데이터 원본 + CSV 다운로드"):
                st.caption("업로드된 생육 결과 데이터 원문입니다.")
                display_g = growth_df.copy()
                for c in display_g.columns:
                    if pd.api.types.is_datetime64_any_dtype(display_g[c]):
                        display_g[c] = display_g[c].dt.strftime("%Y-%m-%d %H:%M")
                    elif pd.api.types.is_numeric_dtype(display_g[c]):
                        display_g[c] = display_g[c].round(2)
                st.dataframe(display_g, width="stretch")
                st.download_button(
                    label="⬇ 생육 결과 CSV 다운로드 (utf-8-sig)",
                    data=df_to_csv_bytes(display_g),
                    file_name=f"{school_name}_생육결과데이터.csv",
                    mime="text/csv",
                )

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


st.caption("※ 일회용 분석용 임시 코드가 아닌, Streamlit Cloud에서 바로 실행되는 대시보드 main.py입니다.")
