import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

# ------------------------------------------------------------------
# 데이터 로드 (원본 경로)
# ------------------------------------------------------------------
gr_path = "/home/user/uploads/0_______________.csv"
env_path = "/home/user/uploads/1_____________.csv"

gr  = pd.read_csv(gr_path)
env = pd.read_csv(env_path)

shoot_col = "지상부 길이(mm)"
root_col  = "지하부길이(mm)"

# ------------------------------------------------------------------
# 생육 데이터 정리
# ------------------------------------------------------------------
shoot = pd.to_numeric(gr[shoot_col], errors="coerce").dropna()
root  = pd.to_numeric(gr[root_col],  errors="coerce").dropna()

shoot_mean = float(shoot.mean())
root_mean  = float(root.mean())
total_mean = shoot_mean + root_mean
shoot_pct  = shoot_mean / total_mean * 100
root_pct   = root_mean  / total_mean * 100

print(f"지상부 평균: {shoot_mean:.1f} mm  ({shoot_pct:.1f}%)")
print(f"지하부 평균: {root_mean:.1f} mm  ({root_pct:.1f}%)")
print(f"총 길이 평균: {total_mean:.1f} mm")
print(f"유효 개체 수(shoot): {len(shoot)}, (root): {len(root)}")
print(f"총 개체 수: {len(gr['개체번호'])}")

# ------------------------------------------------------------------
# 한글 폰트 설정
# ------------------------------------------------------------------
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

# ============================================================
# 그림 1 — 원그래프: 총 길이 평균 대비 지상부·지하부 비율
# ============================================================
fig1, ax1 = plt.subplots(figsize=(6, 5.2))

wedges, texts, autotexts = ax1.pie(
    [shoot_mean, root_mean],
    labels=["지상부 길이 평균", "지하부 길이 평균"],
    autopct="%1.1f%%",
    colors=["forestgreen", "brown"],
    startangle=90,
    wedgeprops=dict(width=0.42, edgecolor="white"),
    textprops=dict(fontsize=12),
)

for at in autotexts:
    at.set_color("white")
    at.set_fontweight("bold")

ax1.set_title(
    f"총 길이 평균({total_mean:.1f} mm) 중\n"
    f"지상부({shoot_mean:.1f} mm) · 지하부({root_mean:.1f} mm) 비율",
    fontsize=13,
    pad=14,
)

ax1.text(
    0, 0,
    f"총 길이\n{total_mean:.1f} mm",
    ha="center", va="center",
    fontsize=12, fontweight="bold", color="#333333",
)

plt.tight_layout()
plt.savefig("/home/user/outputs/pie_ratio.png", dpi=130, bbox_inches="tight")
plt.close(fig1)
print("저장 완료: pie_ratio.png")

# ============================================================
# 그림 2 — 누적 막대그래프: 아래(지하부) + 위(지상부)
# ============================================================
df_plot = gr[["개체번호", shoot_col, root_col]].copy()
df_plot[shoot_col] = pd.to_numeric(df_plot[shoot_col], errors="coerce")
df_plot[root_col]  = pd.to_numeric(df_plot[root_col],  errors="coerce")
df_plot = df_plot.dropna(subset=[shoot_col, root_col])
df_plot = df_plot.sort_values(shoot_col, ascending=False).reset_index(drop=True)

x_labels   = [str(x) for x in df_plot["개체번호"].tolist()]
shoot_vals = df_plot[shoot_col].tolist()
root_vals  = df_plot[root_col].tolist()

fig2, ax2 = plt.subplots(figsize=(11, 5.2))

# 바닥: 지하부 길이 (갈색)
ax2.bar(x_labels, root_vals, color="chocolate", label="지하부 길이", width=0.72)
# 그 위: 지상부 길이 (초록)
ax2.bar(x_labels, shoot_vals, bottom=root_vals, color="forestgreen", label="지상부 길이", width=0.72)

total_len = df_plot[shoot_col] + df_plot[root_col]
max_total_idx = total_len.idxmax()
max_total_id  = df_plot.loc[max_total_idx, "개체번호"]

ax2.set_title("개체별 지상부 길이 + 지하부 길이 누적 (총 길이)", fontsize=14, pad=12)
ax2.set_xlabel("개체번호", fontsize=11)
ax2.set_ylabel("길이 (mm)", fontsize=11)
ax2.legend(fontsize=11, loc="upper right")
ax2.tick_params(axis="x", rotation=45, labelsize=8)
ax2.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
ax2.grid(axis="y", alpha=0.32, linestyle="--")
ax2.set_axisbelow(True)

for spine in ("top", "right"):
    ax2.spines[spine].set_visible(False)

plt.tight_layout()
plt.savefig("/home/user/outputs/stacked_bar.png", dpi=130, bbox_inches="tight")
plt.close(fig2)
print("저장 완료: stacked_bar.png")

# 저장 확인
for p in ["/home/user/outputs/pie_ratio.png", "/home/user/outputs/stacked_bar.png"]:
    print(os.path.basename(p), os.path.getsize(p), "bytes")
