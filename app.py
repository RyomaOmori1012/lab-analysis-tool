import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import japanize_matplotlib
from scipy import stats
from itertools import combinations
import matplotlib.transforms as transforms
import matplotlib.ticker as ticker
import itertools
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import openpyxl
import re
import warnings
import traceback
import io

warnings.filterwarnings('ignore')

# --- フォントのグローバル設定 ---
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Liberation Sans', 'IPAexGothic']
plt.rcParams['mathtext.fontset'] = 'custom'
plt.rcParams['mathtext.rm'] = 'Arial'
plt.rcParams['mathtext.it'] = 'Arial:italic'
plt.rcParams['mathtext.bf'] = 'Arial:bold'
plt.rcParams['svg.fonttype'] = 'none'

st.set_page_config(page_title="実験データ自動解析ツール", layout="wide")
st.title("🧪 実験データ自動解析ツール")

# ==========================================
# UIパーツの構築
# ==========================================
st.sidebar.header("⚙️ 全体設定")
selected_exp = st.sidebar.selectbox('実験手法:', ['Western Blotting (WB)', 'HPLC', 'qPCR', 'MTT Assay (細胞生存率)', '蛍光顕微鏡 (Box Plot)'])
num_cond = st.sidebar.number_input('総条件数(Control含):', min_value=1, max_value=20, value=4, step=1)

is_mtt = 'MTT' in selected_exp
is_microscope = '顕微鏡' in selected_exp
is_qpcr = 'qPCR' in selected_exp

# 手法ごとのラベル設定
if 'WB' in selected_exp:
    t_label, t_ph = '目的(Target):', '例: HO-1'
    l_label, l_ph = '基準(Loading):', '例: HSP90'
    y_label_def = 'Relative Band Intensity'
elif 'HPLC' in selected_exp:
    t_label, t_ph = '目的代謝物:', '例: PpIX'
    l_label, l_ph = '基準(IS):', '例: protein'
    y_label_def = 'Intracellular Concentration'
elif 'qPCR' in selected_exp:
    t_label, t_ph = '目的遺伝子:', '例: PDK1'
    l_label, l_ph = '内部標準:', '例: β-ACTIN'
    y_label_def = 'Relative mRNA level'
elif is_mtt:
    t_label, t_ph = '細胞株:', '例: PC3'
    l_label, l_ph = '薬物:', '例: ALA'
    y_label_def = 'Cell Viability [%]'
elif is_microscope:
    t_label, t_ph = '観察対象:', '例: ROS / GFP'
    l_label, l_ph = '', ''
    y_label_def = 'Relative Fluorescence Intensity'

col1, col2 = st.sidebar.columns(2)
with col1: target_prot = st.text_input(t_label, placeholder=t_ph)
with col2: loading_prot = st.text_input(l_label, placeholder=l_ph) if not is_microscope else ""

t_name = target_prot.strip() or "Target"
l_name = loading_prot.strip() or "Loading"

if is_mtt or is_microscope: y_label_full = y_label_def
else: y_label_full = f"{y_label_def}\n[{t_name} / {l_name}]"

ylabel_input = st.sidebar.text_area('Y軸ラベル:', value=y_label_full, height=68)

# ★ 新機能：グループ化とカラー設定 (MTT以外)
if not is_mtt:
    st.sidebar.markdown("---")
    st.sidebar.header("🖌️ レイアウト・配色設定")
    layout_mode = st.sidebar.radio("棒の配置:", ["均等に並べる", "下段ラベルでグループ化"])
    color_mode = st.sidebar.radio("配色:", ["すべて黒", "上段ラベルで色分け"])
    
    if is_microscope: pairing_options = ['独立 (Welch・ANOVA等)', 'ノンパラ (Mann-Whitney / Kruskal-Wallis等)']
    else: pairing_options = ['独立 (Welch・ANOVA等)', '対応あり (Paired等)']
    
    pairing_mode = st.sidebar.radio('統計検定:', pairing_options)
    norm_mode = st.sidebar.radio('規格化:', ['全体基準 (一番上の条件で全て規格化)', 'グループ基準 (下段ラベル毎の先頭条件で規格化)'])
    test_target_mode = st.sidebar.radio('検定範囲:', ['すべての条件間で検定', 'グループ内でのみ検定 (下段ラベルが同じ条件間)'])
else:
    layout_mode, color_mode, pairing_mode, norm_mode, test_target_mode = "", "", "", "", ""

st.markdown("---")

# ==========================================
# データ入力エリア
# ==========================================
st.header("📝 データ入力")
input_data = []

if is_mtt:
    st.info("💡 **【MTTアッセイ モード】**")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: mtt_ignore_row = st.text_input('空(除外行):', 'A, H')
    with c2: mtt_ignore_col = st.text_input('空(除外列):', '1')
    with c3: mtt_blank_col = st.text_input('Blank(列):', '12')
    with c4: mtt_control_col = st.text_input('Control(列):', '11')
    with c5: mtt_sample_cols = st.text_input('Sample(列):', '2-10')
    c6, c7, c8 = st.columns(3)
    with c6: mtt_start_conc = st.number_input('開始濃度:', value=4000.0)
    with c7: mtt_dilution = st.number_input('希釈倍率(n倍):', value=2.0)
    with c8: mtt_unit = st.text_input('単位:', 'μM')
    for i in range(num_cond):
        p_name = st.text_input(f'プレート {i+1} 条件名:', placeholder=f'例: プレート{i+1}', key=f"pname_{i}")
        p_data = st.text_area(f'プレート {i+1} データ (8行x12列):', placeholder='ここにペースト', height=100, key=f"pdata_{i}")
        input_data.append((p_name, p_data))
elif is_microscope:
    for i in range(num_cond):
        st.markdown(f"**条件 {i+1}**")
        col_up, col_dn, col_val = st.columns([1, 1, 2])
        with col_up: n_up = st.text_input('上段ラベル:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
        with col_dn: n_down = st.text_input('下段ラベル:', placeholder='(空欄可)', key=f"dn_{i}")
        with col_val: n_val = st.text_area(f'{t_name}:', placeholder='数値を縦にコピペ', height=100, key=f"val_{i}")
        input_data.append((n_up, n_down, n_val))
else:
    for i in range(num_cond):
        st.markdown(f"**条件 {i+1}**")
        col_up, col_dn, col_t, col_l = st.columns([1, 1, 1.5, 1.5])
        with col_up: n_up = st.text_input('上段ラベル:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
        with col_dn: n_down = st.text_input('下段ラベル:', placeholder='(空欄可)', key=f"dn_{i}")
        with col_t: n_t = st.text_area(f'{t_name}:', placeholder='数値を縦にコピペ', height=100, key=f"t_{i}")
        with col_l: n_l = st.text_area(f'{l_name}:', placeholder='数値を縦にコピペ', height=100, key=f"l_{i}")
        input_data.append((n_up, n_down, n_t, n_l))

# ==========================================
# 解析・描画ロジック
# ==========================================
def parse_text(text):
    raw_lines = text.replace(',', '\n').split('\n')
    return [float(line.strip()) for line in raw_lines if line.strip()]

def parse_plate(text):
    lines = [line for line in text.replace('\r', '').split('\n') if line.strip()]
    data = []
    for line in lines:
        row = [float(x) if x.strip() else np.nan for x in (line.split('\t') if '\t' in line else re.sub(r'[\s,]+', ',', line.strip()).split(','))]
        while len(row) < 12: row.append(np.nan)
        data.append(row[:12])
    return np.array(data)

def parse_idx(text, is_alpha=False):
    res = []
    for p in text.replace(' ', '').split(','):
        if not p: continue
        if '-' in p:
            start, end = p.split('-')
            if is_alpha: res.extend(range(ord(start.upper())-65, ord(end.upper())-65+1))
            else: res.extend(range(int(start)-1, int(end)))
        else:
            if is_alpha: res.append(ord(p.upper())-65)
            else: res.append(int(p)-1)
    return list(set(res))

if st.button("📊 データ確定 ＆ 自動解析実行", type="primary"):
    with st.spinner("解析中..."):
        try:
            if is_mtt:
                # --- MTT 解析 (前バージョンのロジック維持) ---
                i_rows = parse_idx(mtt_ignore_row, True); i_cols = parse_idx(mtt_ignore_col, False)
                b_cols = parse_idx(mtt_blank_col, False); c_cols = parse_idx(mtt_control_col, False)
                s_cols = parse_idx(mtt_sample_cols, False); s_cols.sort()
                valid_rows = [r for r in range(8) if r not in i_rows]
                conc_vals_raw = [mtt_start_conc / (mtt_dilution ** i) for i in range(len(s_cols))]
                s_cols_plot = s_cols[::-1]; conc_vals_plot = conc_vals_raw[::-1]
                
                plates_data, plate_names, ctrl_sd_pct_list = [], [], []
                for idx, (pn, pd_text) in enumerate(input_data):
                    if not pd_text.strip(): continue
                    arr = parse_plate(pd_text); plate_names.append(pn or f"Plate {idx+1}")
                    blank_mean = np.nanmean([arr[r, c] for r in valid_rows for c in b_cols if c not in i_cols])
                    ctrl_vals = [arr[r, c] - blank_mean for r in valid_rows for c in c_cols if c not in i_cols]
                    ctrl_mean = np.nanmean(ctrl_vals)
                    ctrl_sd_pct_list.append((np.nanstd(ctrl_vals) / ctrl_mean) * 100 if ctrl_mean else 0)
                    plates_data.append((arr - blank_mean) / ctrl_mean * 100)
                
                num_p = len(plates_data)
                fig_comb, ax = plt.subplots(figsize=(7, 5))
                colors = sns.color_palette("Set1", num_p)
                for i in range(num_p):
                    means = [np.nanmean(plates_data[i][valid_rows, c]) for c in s_cols_plot]
                    sds = [np.nanstd(plates_data[i][valid_rows, c]) for c in s_cols_plot]
                    ax.plot(conc_vals_plot, means, '-o', color=colors[i], label=plate_names[i])
                    ax.errorbar(conc_vals_plot, means, yerr=sds, fmt='none', color=colors[i], capsize=4)
                ax.set_xscale('log'); ax.set_ylim(0, 125); ax.set_ylabel(ylabel_input); ax.legend()
                st.pyplot(fig_comb)
                
            else:
                # --- 一般手法 (WB, HPLC, qPCR, 顕微鏡) ---
                is_paired = '対応あり' in pairing_mode
                is_non_param = 'ノンパラ' in pairing_mode
                is_grouped_test = 'グループ内' in test_target_mode
                
                upper_labels, lower_labels, internal_ids, raw_processed = [], [], [], {}
                for idx, item in enumerate(input_data):
                    if is_microscope:
                        u, d, val = item
                        if not val.strip(): continue
                        t_nums = parse_text(val); raw_processed[f"C_{idx}"] = t_nums
                    else:
                        u, d, t_text, l_text = item
                        if not t_text.strip() or not l_text.strip(): continue
                        t_nums, l_nums = parse_text(t_text), parse_text(l_text)
                        if is_qpcr: raw_processed[f"C_{idx}"] = [t - l for t, l in zip(t_nums, l_nums)]
                        else: raw_processed[f"C_{idx}"] = [t / l for t, l in zip(t_nums, l_nums)]
                    upper_labels.append(u or f"U_{idx+1}"); lower_labels.append(d or ""); internal_ids.append(f"C_{idx}")
                
                # 規格化
                final_norm = {}
                ctrl_id = internal_ids[0]
                for uid in internal_ids:
                    if is_qpcr: final_norm[uid] = [2 ** -(v - np.mean(raw_processed[ctrl_id])) for v in raw_processed[uid]]
                    else: final_norm[uid] = [v / np.mean(raw_processed[ctrl_id]) for v in raw_processed[uid]]
                
                # 統計検定
                p_pairs = []
                for u1, u2 in combinations(internal_ids, 2):
                    if is_grouped_test and lower_labels[internal_ids.index(u1)] != lower_labels[internal_ids.index(u2)]: continue
                    if is_non_param: _, p = stats.mannwhitneyu(raw_processed[u1], raw_processed[u2])
                    elif is_paired: _, p = stats.ttest_rel(raw_processed[u1], raw_processed[u2])
                    else: _, p = stats.ttest_ind(raw_processed[u1], raw_processed[u2], equal_var=False)
                    p_pairs.append((u1, u2, p))

                # --- グラフ描画 (レイアウト計算) ---
                unique_low = sorted(list(set(lower_labels)), key=lambda x: lower_labels.index(x))
                unique_up = sorted(list(set(upper_labels)), key=lambda x: upper_labels.index(x))
                palette = dict(zip(unique_up, sns.color_palette("Set1", len(unique_up)))) if color_mode == "上段ラベルで色分け" else {u: "black" for u in unique_up}
                
                fig, ax = plt.subplots(figsize=(max(6, len(internal_ids)*1.2), 5.5))
                bar_width = 0.3 if layout_mode == "下段ラベルでグループ化" else 0.6
                x_coords = {}
                
                if layout_mode == "下段ラベルでグループ化":
                    current_x = 0
                    group_centers = []
                    for low in unique_low:
                        members = [i for i, l in enumerate(lower_labels) if l == low]
                        group_start = current_x
                        for i in members:
                            x = current_x
                            x_coords[internal_ids[i]] = x
                            mean = np.mean(final_norm[internal_ids[i]])
                            sd = np.std(final_norm[internal_ids[i]])
                            ax.bar(x, mean, yerr=sd, width=bar_width, color=palette[upper_labels[i]], edgecolor="black", capsize=3, label=upper_labels[i] if i == upper_labels.index(upper_labels[i]) else "")
                            current_x += bar_width
                        group_centers.append((group_start + current_x - bar_width) / 2)
                        current_x += 0.5 # グループ間の隙間
                    ax.set_xticks(group_centers)
                    ax.set_xticklabels(unique_low, fontsize=15, fontweight="bold")
                else:
                    for i, uid in enumerate(internal_ids):
                        x = i
                        x_coords[uid] = x
                        ax.bar(x, np.mean(final_norm[uid]), yerr=np.std(final_norm[uid]), width=bar_width, color=palette[upper_labels[i]], edgecolor="black", capsize=3)
                    ax.set_xticks(range(len(internal_ids)))
                    ax.set_xticklabels([f"{u}\n{l}" for u, l in zip(upper_labels, lower_labels)], fontsize=12, fontweight="bold")

                # 有意差バーの描画
                max_y_base = max([v for vals in final_norm.values() for v in vals])
                y_shift = max_y_base * 0.12
                sig_count = 0
                for u1, u2, p in p_pairs:
                    if p >= 0.05: continue
                    x1, x2 = x_coords[u1], x_coords[u2]
                    stars = "***" if p < 0.001 else "**" if p < 0.01 else "*"
                    y = max_y_base * 1.1 + sig_count * y_shift
                    ax.plot([x1, x1, x2, x2], [y - y_shift*0.2, y, y, y - y_shift*0.2], color="black", lw=1.2)
                    ax.text((x1+x2)/2, y, stars, ha='center', va='bottom', fontsize=14, fontweight='bold')
                    sig_count += 1
                
                ax.set_ylim(0, max_y_base * (1.3 + sig_count * 0.1))
                ax.set_ylabel(ylabel_input, fontsize=16, fontweight="bold")
                for s in ax.spines.values(): s.set_linewidth(1.5)
                ax.tick_params(direction="in", width=1.5, labelsize=14)
                
                if color_mode == "上段ラベルで色分け":
                    handles, labels = ax.get_legend_handles_labels()
                    by_label = dict(zip(labels, handles))
                    ax.legend(by_label.values(), by_label.keys(), loc='upper right', frameon=False, prop={'size': 12, 'weight': 'bold'})

                st.pyplot(fig)
                
                # --- ダウンロード ---
                buf_svg = io.BytesIO(); fig.savefig(buf_svg, format='svg', bbox_inches='tight')
                st.download_button("📥 グラフ (SVG)", buf_svg.getvalue(), "Graph.svg", "image/svg+xml")
                
                # Excel出力
                xlsx_buf = io.BytesIO()
                with pd.ExcelWriter(xlsx_buf, engine='openpyxl') as writer:
                    summary = pd.DataFrame({
                        '上段ラベル': upper_labels, '下段ラベル': lower_labels,
                        '平均': [np.mean(final_norm[u]) for u in internal_ids],
                        'SD': [np.std(final_norm[u]) for u in internal_ids]
                    })
                    summary.to_excel(writer, sheet_name='Summary', index=False)
                    stats_df = pd.DataFrame([{"比較": f"{u1} vs {u2}", "p値": p, "判定": "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns"} for u1, u2, p in p_pairs])
                    stats_df.to_excel(writer, sheet_name='Statistical_Details', index=False)
                st.download_button("📥 Excelデータをダウンロード", xlsx_buf.getvalue(), "Analysis_Data.xlsx", type="primary")

        except Exception as e:
            st.error(f"エラーが発生しました:\n{traceback.format_exc()}")
