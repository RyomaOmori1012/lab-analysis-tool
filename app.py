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
# サイドバー設定
# ==========================================
st.sidebar.header("⚙️ 全体設定")
selected_exp = st.sidebar.selectbox('実験手法:', ['Western Blotting (WB)', 'HPLC', 'qPCR', 'MTT Assay (細胞生存率)', '蛍光顕微鏡 (Box Plot)'])
num_cond = st.sidebar.number_input('総条件数(Control含):', min_value=1, max_value=20, value=4, step=1)

is_mtt = 'MTT' in selected_exp
is_microscope = '顕微鏡' in selected_exp
is_qpcr = 'qPCR' in selected_exp

# ラベル設定
if 'WB' in selected_exp:
    t_label, t_ph, y_label_def = '目的(Target):', '例: HO-1', 'Relative Band Intensity'
elif 'HPLC' in selected_exp:
    t_label, t_ph, y_label_def = '目的代謝物:', '例: PpIX', 'Intracellular Concentration'
elif 'qPCR' in selected_exp:
    t_label, t_ph, y_label_def = '目的遺伝子:', '例: PDK1', 'Relative mRNA level'
elif is_mtt:
    t_label, t_ph, y_label_def = '細胞株:', '例: PC3', 'Cell Viability [%]'
elif is_microscope:
    t_label, t_ph, y_label_def = '観察対象:', '例: ROS / GFP', 'Relative Fluorescence Intensity'

c_side1, c_side2 = st.sidebar.columns(2)
with c_side1: target_prot = st.text_input(t_label, placeholder=t_ph)
with c_side2: loading_prot = st.text_input('基準(Loading):' if not is_microscope else '', placeholder='例: HSP90' if not is_microscope else '') if not is_microscope else ""

t_name = target_prot.strip() or "Target"
l_name = loading_prot.strip() or "Loading"

if is_mtt or is_microscope: y_label_full = y_label_def
else: y_label_full = f"{y_label_def}\n[{t_name} / {l_name}]"
ylabel_input = st.sidebar.text_area('Y軸ラベル:', value=y_label_full, height=68)

if not is_mtt:
    st.sidebar.markdown("---")
    st.sidebar.header("🖌️ レイアウト・配色設定")
    layout_mode = st.sidebar.radio("棒の配置:", ["均等に並べる", "下段ラベルでグループ化"])
    color_mode = st.sidebar.radio("配色:", ["すべて黒", "上段ラベルで色分け（黒/グレー）"])
    pairing_options = ['独立 (Welch・ANOVA等)', 'ノンパラ (Mann-Whitney / Kruskal-Wallis等)'] if is_microscope else ['独立 (Welch・ANOVA等)', '対応あり (Paired等)']
    pairing_mode = st.sidebar.radio('統計検定:', pairing_options)
    norm_mode = st.sidebar.radio('規格化:', ['全体基準 (一番上の条件で全て規格化)', 'グループ基準 (下段ラベル毎の先頭条件で規格化)'])
    test_target_mode = st.sidebar.radio('検定範囲:', ['すべての条件間で検定', 'グループ内でのみ検定 (下段ラベルが同じ条件間)'])
else:
    layout_mode, color_mode, pairing_mode, norm_mode, test_target_mode = "", "", "", "", ""

st.markdown("---")

# ==========================================
# 画面を左右に分割 (左:入力 / 右:プレビュー)
# ==========================================
col_input, col_graph = st.columns([1.2, 1.0], gap="large")

with col_input:
    st.header("📝 データ入力")
    input_data = []

    if is_mtt:
        c1, c2, c3 = st.columns(3)
        with c1: mtt_ignore_row = st.text_input('空(除外行):', 'A, H')
        with c2: mtt_ignore_col = st.text_input('空(除外列):', '1')
        with c3: mtt_blank_col = st.text_input('Blank(列):', '12')
        c4, c5 = st.columns(2)
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
            col_up, col_dn, col_val = st.columns([1, 1, 2])
            with col_up: n_up = st.text_input(f'条件{i+1} 上段:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
            with col_dn: n_down = st.text_input(f'条件{i+1} 下段:', placeholder='(空欄可)', key=f"dn_{i}")
            with col_val: n_val = st.text_area(f'{t_name}:', placeholder='縦にペースト', height=68, key=f"val_{i}")
            input_data.append((n_up, n_down, n_val))
    else:
        for i in range(num_cond):
            col_up, col_dn, col_t, col_l = st.columns([1, 1, 1.5, 1.5])
            with col_up: n_up = st.text_input(f'条件{i+1} 上段:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
            with col_dn: n_down = st.text_input(f'条件{i+1} 下段:', placeholder='(空欄可)', key=f"dn_{i}")
            with col_t: n_t = st.text_area(f'{t_name}:', placeholder='縦にペースト', height=68, key=f"t_{i}")
            with col_l: n_l = st.text_area(f'{l_name}:', placeholder='縦にペースト', height=68, key=f"l_{i}")
            input_data.append((n_up, n_down, n_t, n_l))

# ヘルパー関数
def parse_text(text): return [float(line.strip()) for line in text.replace(',', '\n').split('\n') if line.strip()]
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
            res.extend(range(ord(start.upper())-65, ord(end.upper())-65+1) if is_alpha else range(int(start)-1, int(end)))
        else: res.append(ord(p.upper())-65 if is_alpha else int(p)-1)
    return list(set(res))

with col_graph:
    st.header("📊 リアルタイムプレビュー")
    
    try:
        if is_mtt:
            active_data = [(pn, pd_text) for pn, pd_text in input_data if pd_text.strip()]
            if not active_data:
                st.info("👈 左側の入力枠にデータをペーストすると、ここに即座にグラフが表示されます。")
            else:
                i_rows, i_cols = parse_idx(mtt_ignore_row, True), parse_idx(mtt_ignore_col, False)
                b_cols, c_cols, s_cols = parse_idx(mtt_blank_col, False), parse_idx(mtt_control_col, False), parse_idx(mtt_sample_cols, False)
                s_cols.sort()
                valid_rows = [r for r in range(8) if r not in i_rows]
                conc_vals_plot = [mtt_start_conc / (mtt_dilution ** i) for i in range(len(s_cols))][::-1]
                s_cols_plot = s_cols[::-1]
                
                plates_data, plate_names, ctrl_sd_pct_list = [], [], []
                for pn, pd_text in active_data:
                    arr = parse_plate(pd_text); plate_names.append(pn or f"Plate {len(plate_names)+1}")
                    blank_mean = np.nanmean([arr[r, c] for r in valid_rows for c in b_cols if c not in i_cols])
                    ctrl_vals = [arr[r, c] - blank_mean for r in valid_rows for c in c_cols if c not in i_cols]
                    ctrl_mean = np.nanmean(ctrl_vals)
                    ctrl_sd_pct_list.append((np.nanstd(ctrl_vals) / ctrl_mean) * 100 if ctrl_mean else 0)
                    plates_data.append((arr - blank_mean) / ctrl_mean * 100)
                
                num_p = len(plates_data)
                fig_comb, ax = plt.subplots(figsize=(7, 5))
                colors = sns.color_palette("Set1", max(num_p, 2)) if num_p > 1 else ['black']
                for i in range(num_p):
                    means = [np.nanmean(plates_data[i][valid_rows, c]) for c in s_cols_plot]
                    sds = [np.nanstd(plates_data[i][valid_rows, c]) for c in s_cols_plot]
                    ax.plot(conc_vals_plot, means, '-o', color=colors[i], label=plate_names[i])
                    ax.errorbar(conc_vals_plot, means, yerr=sds, fmt='none', color=colors[i], capsize=4)
                
                ax.set_xscale('log'); ax.set_ylim(0, 125); ax.set_ylabel(ylabel_input); ax.legend()
                st.pyplot(fig_comb)
                
                # Excel生成
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    pass # (MTT Excel保存は容量と速度優先でプレビュー時は省略、必要な場合はここに追加)
                
        else:
            is_paired = '対応あり' in pairing_mode
            is_non_param = 'ノンパラ' in pairing_mode
            is_grouped_test = 'グループ内' in test_target_mode
            
            upper_labels, lower_labels, internal_ids, raw_processed = [], [], [], {}
            data_error = False
            
            for idx, item in enumerate(input_data):
                if is_microscope:
                    u, d, val = item
                    if not val.strip(): continue
                    raw_processed[f"C_{idx}"] = parse_text(val)
                else:
                    u, d, t_text, l_text = item
                    if not t_text.strip() and not l_text.strip(): continue
                    if not t_text.strip() or not l_text.strip():
                        st.warning(f"⚠️ 条件 {idx+1} のデータが片方だけです。")
                        data_error = True; break
                    t_nums, l_nums = parse_text(t_text), parse_text(l_text)
                    if len(t_nums) != len(l_nums):
                        st.warning(f"⚠️ 条件 {idx+1} の目的と基準のデータ数が一致しません。")
                        data_error = True; break
                    if is_qpcr: raw_processed[f"C_{idx}"] = [t - l for t, l in zip(t_nums, l_nums)]
                    else: raw_processed[f"C_{idx}"] = [t / l for t, l in zip(t_nums, l_nums)]
                
                upper_labels.append(u or f"U_{idx+1}"); lower_labels.append(d or "")
                internal_ids.append(f"C_{idx}")
            
            if not data_error:
                if len(internal_ids) < 2:
                    st.info("👈 左側の入力枠に **2つ以上** のデータをペーストすると、即座にグラフが表示されます。")
                else:
                    if is_paired and not is_microscope:
                        if len(set([len(raw_processed[u]) for u in internal_ids])) > 1:
                            st.warning("⚠️ 「対応あり」の場合、全条件のn数を揃える必要があります。")
                            data_error = True
                            
                    if not data_error:
                        final_norm = {}
                        ctrl_id = internal_ids[0]
                        for i, uid in enumerate(internal_ids):
                            c_id = internal_ids[lower_labels.index(lower_labels[i])] if 'グループ' in norm_mode else ctrl_id
                            if is_qpcr: final_norm[uid] = [2 ** -(v - np.mean(raw_processed[c_id])) for v in raw_processed[uid]]
                            else: final_norm[uid] = [v / np.mean(raw_processed[c_id]) for v in raw_processed[uid]]
                        
                        p_pairs = []
                        for u1, u2 in combinations(internal_ids, 2):
                            if is_grouped_test and lower_labels[internal_ids.index(u1)] != lower_labels[internal_ids.index(u2)]: continue
                            if is_non_param: _, p = stats.mannwhitneyu(raw_processed[u1], raw_processed[u2])
                            elif is_paired: _, p = stats.ttest_rel(raw_processed[u1], raw_processed[u2])
                            else: _, p = stats.ttest_ind(raw_processed[u1], raw_processed[u2], equal_var=False)
                            p_pairs.append((u1, u2, p))

                        unique_low = sorted(list(set(lower_labels)), key=lambda x: lower_labels.index(x))
                        unique_up = sorted(list(set(upper_labels)), key=lambda x: upper_labels.index(x))
                        gray_palette = ['black', 'darkgray', 'lightgray', 'dimgray', 'whitesmoke', '#E0E0E0']
                        palette = {u: gray_palette[i % len(gray_palette)] for i, u in enumerate(unique_up)} if "色分け" in color_mode else {u: "black" for u in unique_up}
                        
                        fig, ax = plt.subplots(figsize=(max(6, len(internal_ids)*1.2), 5.5))
                        bar_width = 0.3 if layout_mode == "下段ラベルでグループ化" else 0.6
                        x_coords = {}
                        
                        if layout_mode == "下段ラベルでグループ化":
                            current_x = 0; group_centers = []
                            for low in unique_low:
                                members = [i for i, l in enumerate(lower_labels) if l == low]
                                g_start = current_x
                                for i in members:
                                    x_coords[internal_ids[i]] = current_x
                                    ax.bar(current_x, np.mean(final_norm[internal_ids[i]]), yerr=np.std(final_norm[internal_ids[i]]), width=bar_width, color=palette[upper_labels[i]], edgecolor="black", capsize=3, label=upper_labels[i] if i == upper_labels.index(upper_labels[i]) else "")
                                    current_x += bar_width
                                group_centers.append((g_start + current_x - bar_width) / 2)
                                current_x += 0.5
                            ax.set_xticks(group_centers); ax.set_xticklabels(unique_low, fontsize=15, fontweight="bold")
                        else:
                            for i, uid in enumerate(internal_ids):
                                x_coords[uid] = i
                                ax.bar(i, np.mean(final_norm[uid]), yerr=np.std(final_norm[uid]), width=bar_width, color=palette[upper_labels[i]], edgecolor="black", capsize=3)
                            ax.set_xticks(range(len(internal_ids)))
                            ax.set_xticklabels([f"{u}\n{l}" for u, l in zip(upper_labels, lower_labels)], fontsize=12, fontweight="bold")

                        max_y = max([v for vals in final_norm.values() for v in vals])
                        y_shift = max_y * 0.12; sig_count = 0
                        for u1, u2, p in p_pairs:
                            if p >= 0.05: continue
                            x1, x2 = x_coords[u1], x_coords[u2]; stars = "***" if p < 0.001 else "**" if p < 0.01 else "*"
                            y = max_y * 1.1 + sig_count * y_shift
                            ax.plot([x1, x1, x2, x2], [y - y_shift*0.2, y, y, y - y_shift*0.2], color="black", lw=1.2)
                            ax.text((x1+x2)/2, y, stars, ha='center', va='bottom', fontsize=14, fontweight='bold')
                            sig_count += 1
                        
                        ax.set_ylim(0, max_y * (1.3 + sig_count * 0.1))
                        ax.set_ylabel(ylabel_input, fontsize=16, fontweight="bold")
                        for s in ax.spines.values(): s.set_linewidth(1.5)
                        ax.tick_params(direction="in", width=1.5, labelsize=14)
                        
                        if "色分け" in color_mode:
                            handles, labels = ax.get_legend_handles_labels()
                            by_label = dict(zip(labels, handles))
                            ax.legend(by_label.values(), by_label.keys(), loc='upper right', frameon=False, prop={'size': 12, 'weight': 'bold'})

                        st.pyplot(fig)
                        
                        buf_svg = io.BytesIO(); fig.savefig(buf_svg, format='svg', bbox_inches='tight')
                        st.download_button("📥 完成グラフ (SVG形式) をダウンロード", buf_svg.getvalue(), "Graph.svg", "image/svg+xml", use_container_width=True)

    except Exception as e:
        st.error(f"エラーが発生しました:\n{traceback.format_exc()}")
