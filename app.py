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

if 'WB' in selected_exp:
    t_label, t_ph, l_label, l_ph, y_label_def = '目的(Target):', '例: HO-1', '基準(Loading):', '例: HSP90', 'Relative Band Intensity'
elif 'HPLC' in selected_exp:
    t_label, t_ph, l_label, l_ph, y_label_def = '目的代謝物:', '例: PpIX', '基準(IS):', '例: protein', 'Intracellular Concentration'
elif 'qPCR' in selected_exp:
    t_label, t_ph, l_label, l_ph, y_label_def = '目的遺伝子:', '例: PDK1', '内部標準:', '例: β-ACTIN', 'Relative mRNA level'
elif is_mtt:
    t_label, t_ph, l_label, l_ph, y_label_def = '細胞株:', '例: PC3', '薬物:', '例: ALA', 'Cell Viability [%]'
elif is_microscope:
    t_label, t_ph, l_label, l_ph, y_label_def = '観察対象:', '例: ROS / GFP', '', '', 'Relative Fluorescence Intensity'

c_side1, c_side2 = st.sidebar.columns(2)
with c_side1: target_prot = st.text_input(t_label, placeholder=t_ph)
with c_side2: loading_prot = st.text_input(l_label, placeholder=l_ph) if not is_microscope else ""

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

def parse_text(text):
    if not text.strip(): return [np.nan]
    return [float(line.strip()) for line in text.replace(',', '\n').split('\n') if line.strip()]

def parse_plate(text):
    if not text.strip(): return np.full((8, 12), np.nan)
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
    st.info("💡 左の枠に文字を打つとグラフの枠が連動し、数値をペーストすると棒が出現します。")
    
    try:
        if is_mtt:
            i_rows, i_cols = parse_idx(mtt_ignore_row, True), parse_idx(mtt_ignore_col, False)
            b_cols, c_cols, s_cols = parse_idx(mtt_blank_col, False), parse_idx(mtt_control_col, False), parse_idx(mtt_sample_cols, False)
            s_cols.sort()
            valid_rows = [r for r in range(8) if r not in i_rows]
            conc_vals_plot = [mtt_start_conc / (mtt_dilution ** i) for i in range(len(s_cols))][::-1]
            s_cols_plot = s_cols[::-1]
            
            plates_data, plate_names, ctrl_sd_pct_list = [], [], []
            for idx, (pn, pd_text) in enumerate(input_data):
                arr = parse_plate(pd_text); plate_names.append(pn or f"Plate {idx+1}")
                blank_vals = [arr[r, c] for r in valid_rows for c in b_cols if c not in i_cols and not np.isnan(arr[r, c])]
                blank_mean = np.nanmean(blank_vals) if blank_vals else 0.0
                
                ctrl_vals = [arr[r, c] - blank_mean for r in valid_rows for c in c_cols if c not in i_cols and not np.isnan(arr[r, c])]
                ctrl_mean = np.nanmean(ctrl_vals) if ctrl_vals else np.nan
                ctrl_sd_pct_list.append((np.nanstd(ctrl_vals) / ctrl_mean) * 100 if not np.isnan(ctrl_mean) and ctrl_mean != 0 else 0)
                
                if np.isnan(ctrl_mean) or ctrl_mean == 0: plates_data.append(np.full((8, 12), np.nan))
                else: plates_data.append((arr - blank_mean) / ctrl_mean * 100)
            
            num_p = len(plates_data)
            
            indiv_figs = []
            for i in range(num_p):
                fig_i, ax_i = plt.subplots(figsize=(6, 4))
                fig_i.patch.set_facecolor('white')
                ax_i.set_facecolor('white')
                
                means_i = [np.nanmean(plates_data[i][valid_rows, c]) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
                sds_i = [np.nanstd(plates_data[i][valid_rows, c]) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
                ax_i.errorbar(conc_vals_plot, means_i, yerr=sds_i, fmt='-o', color='black', capsize=4, mfc='black', mec='black', lw=1.5)
                
                ax_i.set_xscale('log'); ax_i.set_ylim(bottom=0, top=125)
                ax_i.yaxis.set_major_locator(ticker.MultipleLocator(20))
                ax_i.xaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: '{:g}'.format(y)))
                
                for spine in ax_i.spines.values(): spine.set_color('black'); spine.set_linewidth(1.2)
                ax_i.tick_params(direction='in', length=5, width=1.2, labelsize=12, colors='black', which='both')
                
                ax_i.set_ylabel(ylabel_input, fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
                ax_i.set_xlabel(f"{l_name} [{mtt_unit}]", fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
                n_indiv = max([np.count_nonzero(~np.isnan(plates_data[i][valid_rows, c])) for c in s_cols_plot]) if s_cols_plot else len(valid_rows)
                ax_i.set_title(f"n={n_indiv}", fontsize=14, pad=15, fontname='Arial')
                indiv_figs.append((plate_names[i], fig_i))

            fig_comb, ax = plt.subplots(figsize=(7, 5))
            fig_comb.patch.set_facecolor('white')
            ax.set_facecolor('white')
            
            colors = sns.color_palette("Set1", max(num_p, 2)) if num_p > 1 else ['black']
            for i in range(num_p):
                means = [np.nanmean(plates_data[i][valid_rows, c]) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
                sds = [np.nanstd(plates_data[i][valid_rows, c]) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
                ax.plot(conc_vals_plot, means, '-o', color=colors[i], mfc=colors[i], mec=colors[i], lw=1.8, label=plate_names[i])
                ax.errorbar(conc_vals_plot, means, yerr=sds, fmt='none', color=colors[i], capsize=4, lw=1.8)
            
            for idx_c, c in enumerate(s_cols_plot):
                col_data = [d[~np.isnan(d)] for d in [plates_data[p][valid_rows, c] for p in range(num_p)]]
                col_data_valid = [d for d in col_data if len(d) > 0]
                p_val = np.nan
                if len(col_data_valid) == 2: _, p_val = stats.ttest_ind(col_data_valid[0], col_data_valid[1], equal_var=False)
                elif len(col_data_valid) >= 3: _, p_val = stats.f_oneway(*col_data_valid)
                if not np.isnan(p_val) and p_val < 0.05:
                    stars = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*"
                    max_y_at_c = max([np.nanmean(d)+np.nanstd(d) for d in col_data_valid])
                    ax.text(conc_vals_plot[idx_c], max_y_at_c + 6, stars, ha='center', va='bottom', fontsize=14, fontweight='bold', fontname='Arial', color='black')

            ax.set_xscale('log'); ax.set_ylim(bottom=0, top=125)
            ax.yaxis.set_major_locator(ticker.MultipleLocator(20))
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: '{:g}'.format(y)))
            
            for spine in ax.spines.values(): spine.set_color('black'); spine.set_linewidth(1.2)
            ax.tick_params(direction='in', length=5, width=1.2, labelsize=12, colors='black', which='both')
            
            ax.set_ylabel(ylabel_input, fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
            ax.set_xlabel(f"{l_name} [{mtt_unit}]", fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
            ax.legend(loc='lower left', frameon=False, prop={'family': 'Arial', 'size': 13})
            
            mtt_test_desc = "Welch's t-test" if num_p == 2 else "One-way ANOVA (Tukey)" if num_p >= 3 else "MTT Assay"
            max_n = max([np.count_nonzero(~np.isnan(plates_data[i][valid_rows, c])) for i in range(num_p) for c in s_cols_plot]) if num_p > 0 else 0
            ax.set_title(f"{mtt_test_desc}, n={max_n}", fontsize=14, pad=15, fontname='Arial')

            st.pyplot(fig_comb)
            
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                mtt_summary_dict = {"濃度 (Concentration)": [0.0] + [float(x) for x in conc_vals_plot]}
                for i, p_name in enumerate(plate_names):
                    mtt_summary_dict[f"{p_name}_Mean(%)"] = [100.0] + [float(np.nanmean(plates_data[i][valid_rows, c])) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
                    mtt_summary_dict[f"{p_name}_SD(%)"] = [float(ctrl_sd_pct_list[i])] + [float(np.nanstd(plates_data[i][valid_rows, c])) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
                pd.DataFrame(mtt_summary_dict).to_excel(writer, sheet_name='Summary', index=False)
                
                long_mtt_list = []
                for i, p_name in enumerate(plate_names):
                    ctrl_vals = [plates_data[i][r, c] for r in valid_rows for c in c_cols if c not in i_cols]
                    for val in ctrl_vals:
                        if not np.isnan(val): long_mtt_list.append({"条件名": f"{p_name}_0_{mtt_unit}", "正規化生存率 (%)": float(val)})
                    for idx_c, c in enumerate(s_cols_plot):
                        for val in plates_data[i][valid_rows, c]:
                            if not np.isnan(val): long_mtt_list.append({"条件名": f"{p_name}_{conc_vals_plot[idx_c]}_{mtt_unit}", "正規化生存率 (%)": float(val)})
                pd.DataFrame(long_mtt_list).to_excel(writer, sheet_name='Normalized_Data', index=False)
                
                for i in range(num_p):
                    df_norm = pd.DataFrame(plates_data[i])
                    df_norm.index = ['A','B','C','D','E','F','G','H']
                    df_norm.columns = [str(x+1) for x in range(12)]
                    df_norm.to_excel(writer, sheet_name=re.sub(r'[\\/*?:\[\]]', '', f"Plate_{i+1}_{plate_names[i]}")[:31])
                
                if num_p > 1:
                    stat_data = []
                    for idx_c, c in enumerate(s_cols_plot):
                        conc_str = f"{conc_vals_plot[idx_c]:g}"
                        col_data_valid = [d[~np.isnan(d)] for d in [plates_data[p][valid_rows, c] for p in range(num_p)] if len(d[~np.isnan(d)]) > 0]
                        p_val, test_name = np.nan, ""
                        if len(col_data_valid) == 2: _, p_val = stats.ttest_ind(col_data_valid[0], col_data_valid[1], equal_var=False); test_name = "Welch's t-test"
                        elif len(col_data_valid) >= 3: _, p_val = stats.f_oneway(*col_data_valid); test_name = "One-way ANOVA"
                        signif = "***" if p_val<0.001 else "**" if p_val<0.01 else "*" if p_val<0.05 else "ns" if not np.isnan(p_val) else "N/A"
                        stat_data.append({f"濃度({mtt_unit})": conc_str, "p値": p_val if not np.isnan(p_val) else "N/A", "有意差": signif, "検定手法": test_name or "データ不足"})
                    if stat_data: pd.DataFrame(stat_data).to_excel(writer, sheet_name='Statistical_Details', index=False)

                try:
                    ws = writer.book['Summary']
                    sc = len(mtt_summary_dict.keys()) + 2
                    ws.cell(row=2, column=sc, value="💡 【エラーバー付き折れ線グラフの最短作成手順】")
                    ws.cell(row=3, column=sc, value="1. 左の濃度と各条件の『Mean』の列だけをCtrlキーで選択し、[挿入] ＞ [散布図(直線とマーカー)]")
                    ws.cell(row=4, column=sc, value="2. グラフ上の線をクリックし、[＋] ＞ [誤差範囲] ＞ [その他の誤差範囲オプション]")
                    ws.cell(row=5, column=sc, value="3. 『両方向』『キャップ』にし、『カスタム』にチェックを入れ『値の指定』")
                    ws.cell(row=6, column=sc, value="4. 正負両方に、該当条件の『SD』列の数値を指定すれば完成！")
                except: pass

            st.download_button("📥 Excelデータをダウンロード (全データ・統計詳細シート同梱)", excel_buffer.getvalue(), "Analysis_Data.xlsx", type="primary", use_container_width=True)
            
            dl_col1, dl_col2 = st.columns(2)
            buf_c = io.BytesIO()
            fig_comb.savefig(buf_c, format='svg', bbox_inches='tight')
            with dl_col1: st.download_button("📥 統合グラフ(SVG)を保存", buf_c.getvalue(), "Combined_Graph.svg", "image/svg+xml", use_container_width=True)
            
            with st.expander("個別プレートのグラフ(SVG)をダウンロード"):
                for p_name, f in indiv_figs:
                    buf_i = io.BytesIO()
                    f.savefig(buf_i, format='svg', bbox_inches='tight')
                    st.download_button(f"📥 {p_name} のグラフ", buf_i.getvalue(), f"{p_name}_Graph.svg", "image/svg+xml")

        else:
            # --- 一般手法 (WB, HPLC, qPCR, 顕微鏡) ---
            is_paired = '対応あり' in pairing_mode
            is_non_param = 'ノンパラ' in pairing_mode
            is_grouped_test = 'グループ内' in test_target_mode
            
            upper_labels, lower_labels, internal_ids, raw_processed = [], [], [], {}
            
            for idx, item in enumerate(input_data):
                if is_microscope:
                    u, d, val = item
                    raw_processed[f"C_{idx}"] = parse_text(val)
                else:
                    u, d, t_text, l_text = item
                    t_nums, l_nums = parse_text(t_text), parse_text(l_text)
                    length = max(len(t_nums), len(l_nums))
                    t_nums.extend([np.nan] * (length - len(t_nums)))
                    l_nums.extend([np.nan] * (length - len(l_nums)))
                    if is_qpcr: raw_processed[f"C_{idx}"] = [t - l for t, l in zip(t_nums, l_nums)]
                    else: raw_processed[f"C_{idx}"] = [t / l for t, l in zip(t_nums, l_nums)]
                
                upper_labels.append(u or f"U_{idx+1}"); lower_labels.append(d or "")
                internal_ids.append(f"C_{idx}")
            
            final_norm = {}
            ctrl_id = internal_ids[0]
            for i, uid in enumerate(internal_ids):
                c_id = internal_ids[lower_labels.index(lower_labels[i])] if 'グループ' in norm_mode else ctrl_id
                c_mean = np.nanmean(raw_processed[c_id])
                if np.isnan(c_mean) or c_mean == 0: c_mean = 1.0 
                
                if is_qpcr: final_norm[uid] = [2 ** -(v - c_mean) for v in raw_processed[uid]]
                else: final_norm[uid] = [v / c_mean for v in raw_processed[uid]]
            
            p_pairs = []
            for u1, u2 in combinations(internal_ids, 2):
                if is_grouped_test and lower_labels[internal_ids.index(u1)] != lower_labels[internal_ids.index(u2)]: continue
                d1, d2 = [v for v in raw_processed[u1] if not np.isnan(v)], [v for v in raw_processed[u2] if not np.isnan(v)]
                if len(d1) < 2 or len(d2) < 2:
                    p_pairs.append((u1, u2, np.nan)); continue
                try:
                    if is_non_param: _, p = stats.mannwhitneyu(d1, d2)
                    elif is_paired: _, p = stats.ttest_rel(d1, d2)
                    else: _, p = stats.ttest_ind(d1, d2, equal_var=False)
                except: p = np.nan
                p_pairs.append((u1, u2, p))

            unique_low = sorted(list(set(lower_labels)), key=lambda x: lower_labels.index(x))
            unique_up = sorted(list(set(upper_labels)), key=lambda x: upper_labels.index(x))
            gray_palette = ['black', 'darkgray', 'lightgray', 'dimgray', 'whitesmoke', '#E0E0E0']
            palette = {u: gray_palette[i % len(gray_palette)] for i, u in enumerate(unique_up)} if "色分け" in color_mode else {u: "black" for u in unique_up}
            
            # ★ グラフの「完璧な」白背景とサイズ指定
            fig, ax = plt.subplots(figsize=(max(4.0, len(internal_ids)*1.5+1.5), 5.5))
            fig.patch.set_facecolor('white')
            ax.set_facecolor('white')
            
            x_coords = {}
            bar_width = 0.17 # ★ 完璧だった時の細い棒のサイズ
            
            if layout_mode == "下段ラベルでグループ化":
                bar_width = 0.25 # グループ化時は少しだけ太くする
                current_x = 0; group_centers = []
                for low in unique_low:
                    members = [i for i, l in enumerate(lower_labels) if l == low]
                    g_start = current_x
                    for i in members:
                        x_coords[internal_ids[i]] = current_x
                        current_x += bar_width + 0.02
                    group_centers.append((g_start + current_x - bar_width - 0.02) / 2)
                    current_x += 0.5
            else:
                for i, uid in enumerate(internal_ids):
                    x_coords[uid] = float(i)

            # --- 棒グラフ / 箱ひげ図 の描画 ---
            if is_microscope:
                positions = [x_coords[uid] for uid in internal_ids]
                box_data = [final_norm[uid] for uid in internal_ids]
                # 全てをクリーンにするためNaNを除外
                box_data_clean = [[v for v in d if not np.isnan(v)] for d in box_data]
                ax.boxplot(box_data_clean, positions=positions, widths=bar_width*1.5, patch_artist=True, 
                           boxprops=dict(facecolor='white', color='black', linewidth=1.2), 
                           capprops=dict(color='black', linewidth=1.2),
                           whiskerprops=dict(color='black', linewidth=1.2),
                           medianprops=dict(color='black', linewidth=1.5), 
                           flierprops=dict(marker='o', markerfacecolor='black', markeredgecolor='black', alpha=0.8, markersize=4))
            else:
                for i, uid in enumerate(internal_ids):
                    mean_val = np.nanmean(final_norm[uid])
                    sd_val = np.nanstd(final_norm[uid])
                    color = palette[upper_labels[i]]
                    # ★ 完璧だった時のエラーバー指定（ecolor='black', lw=1.2, capsize=3）
                    ax.bar(x_coords[uid], mean_val if not np.isnan(mean_val) else 0, yerr=sd_val if not np.isnan(sd_val) else 0, 
                           width=bar_width, color=color, edgecolor='black', capsize=3, error_kw=dict(ecolor='black', lw=1.2), 
                           label=upper_labels[i] if i == upper_labels.index(upper_labels[i]) else "")

            # ★ 完璧だった時の軸設定（太さ、内向き、ラベルサイズ）
            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_color('black')
                spine.set_linewidth(1.5)
            ax.tick_params(axis='y', colors='black', direction='in', left=True, right=False, length=5, width=1.5, labelsize=14)
            ax.tick_params(axis='x', bottom=False, top=False)
            
            # --- 美しいX軸の2段ラベル描画 ---
            ax.set_xticklabels([]) 
            trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
            
            if layout_mode == "下段ラベルでグループ化" and "色分け" in color_mode:
                # 色分け時は下段ラベルのみ中央に配置
                for low in unique_low:
                    members = [i for i, l in enumerate(lower_labels) if l == low]
                    xs = [x_coords[internal_ids[i]] for i in members]
                    x_center = sum(xs) / len(xs)
                    ax.text(x_center, -0.05, low, ha='center', va='top', transform=trans, fontsize=16, fontweight='bold', color='black')
            else:
                # 上段ラベル配置
                for i, uid in enumerate(internal_ids):
                    ax.text(x_coords[uid], -0.05, upper_labels[i], ha='center', va='top', transform=trans, fontsize=16, color='black', fontweight='bold')
                # 下段ラベルとグループ線の配置
                grouped_lower = [(k, list(g)) for k, g in itertools.groupby(enumerate(lower_labels), key=lambda x: x[1])]
                line_y = -0.16
                text_y = -0.21
                for label, elements in grouped_lower:
                    if not label: continue
                    indices = [x[0] for x in elements]
                    xs = [x_coords[internal_ids[i]] for i in indices]
                    x_start, x_end = min(xs), max(xs)
                    if x_start != x_end:
                        ax.plot([x_start - bar_width/2, x_end + bar_width/2], [line_y, line_y], color='black', lw=1.5, transform=trans, clip_on=False)
                    x_center = (x_start + x_end) / 2
                    ax.text(x_center, text_y, label, ha='center', va='top', transform=trans, fontsize=16, fontweight='bold', color='black')

            # --- 有意差ブラケット（完璧だった時の正確な計算式） ---
            all_vals = [v for vals in final_norm.values() for v in vals if not np.isnan(v)]
            max_y = max(all_vals + [0]) if all_vals else 1.0
            if max_y == 0: max_y = 1.0
            
            y_shift = max_y * 0.15
            h = max_y * 0.025
            base_bracket_y = max_y * 1.15
            
            levels = []
            max_level = 0
            sig_pairs = []
            for u1, u2, p in p_pairs:
                if p >= 0.05 or np.isnan(p): continue
                stars = "***" if p < 0.001 else "**" if p < 0.01 else "*"
                x1, x2 = x_coords[u1], x_coords[u2]
                sig_pairs.append((min(x1, x2), max(x1, x2), stars))
            
            sig_pairs.sort(key=lambda x: x[1] - x[0])
            for x_start, x_end, stars in sig_pairs:
                placed_level = -1
                for level_idx, intervals in enumerate(levels):
                    overlap = False
                    for (s, e) in intervals:
                        if not (x_end < s or x_start > e):
                            overlap = True; break
                    if not overlap:
                        placed_level = level_idx; break
                if placed_level == -1:
                    placed_level = len(levels)
                    levels.append([])
                levels[placed_level].append((x_start, x_end))
                max_level = max(max_level, placed_level)
                bracket_y = base_bracket_y + placed_level * y_shift
                ax.plot([x_start, x_start, x_end, x_end], [bracket_y - h, bracket_y, bracket_y, bracket_y - h], color='black', lw=1.2)
                ax.text((x_start + x_end) / 2, bracket_y + h*0.2, stars, ha='center', va='bottom', color='black', fontsize=14, fontweight='bold')

            final_max_y = base_bracket_y + (max_level + 1) * y_shift if sig_pairs else max_y * 1.3
            ax.set_ylim(0, final_max_y)
            
            x_vals = list(x_coords.values())
            ax.set_xlim(min(x_vals) - 0.6, max(x_vals) + 0.6)
            
            ax.set_ylabel(ylabel_input, fontsize=16, fontweight="bold", color='black', labelpad=10)
            
            if "色分け" in color_mode:
                handles, labels = ax.get_legend_handles_labels()
                by_label = dict(zip(labels, handles))
                if by_label: ax.legend(by_label.values(), by_label.keys(), loc='upper right', frameon=False, prop={'family':'Arial', 'size': 12, 'weight': 'bold'})

            n_list = [len([v for v in raw_processed[u] if not np.isnan(v)]) for u in internal_ids]
            expected_n = n_list[0] if n_list and len(set(n_list)) == 1 else "varies"
            
            if is_grouped_test:
                g_lens = [len([u for u in internal_ids if lower_labels[internal_ids.index(u)] == low]) for low in unique_low]
                max_g_len = max(g_lens) if g_lens else 0
                if max_g_len == 2: test_desc_flat = "Mann-Whitney U" if is_non_param else "Paired t-test" if is_paired else "Welch's t-test"
                elif max_g_len >= 3: test_desc_flat = "Kruskal-Wallis (Holm)" if is_non_param else "Paired t-test (Holm)" if is_paired else "One-way ANOVA (Tukey)"
                else: test_desc_flat = "Statistical Test"
            else:
                num_g = len(internal_ids)
                if num_g == 2: test_desc_flat = "Mann-Whitney U" if is_non_param else "Paired t-test" if is_paired else "Welch's t-test"
                elif num_g >= 3: test_desc_flat = "Kruskal-Wallis (Holm)" if is_non_param else "Paired t-test (Holm)" if is_paired else "One-way ANOVA (Tukey)"
                else: test_desc_flat = "Statistical Test"
                
            ax.set_title(test_desc_flat if is_microscope else f"{test_desc_flat}, n={expected_n}", fontsize=14, pad=15, fontname='Arial')

            st.pyplot(fig)
            
            # --- 完全版 Excel生成 (一般手法) ---
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                summary = pd.DataFrame({
                    '上段ラベル': upper_labels, '下段ラベル': lower_labels,
                    '平均': [np.nanmean(final_norm[u]) for u in internal_ids],
                    'SD': [np.nanstd(final_norm[u]) for u in internal_ids]
                })
                summary.to_excel(writer, sheet_name='Summary', index=False)
                
                long_data = [{"条件名": f"{upper_labels[i]} ({lower_labels[i]})" if lower_labels[i] else upper_labels[i], "正規化データ": float(val)} for i, u in enumerate(internal_ids) for val in final_norm[u] if not np.isnan(val)]
                pd.DataFrame(long_data).to_excel(writer, sheet_name='Normalized_Data', index=False)
                
                stats_df = pd.DataFrame([{"比較": f"{upper_labels[internal_ids.index(u1)]} vs {upper_labels[internal_ids.index(u2)]}", "p値": p if not np.isnan(p) else "N/A", "判定": "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns" if not np.isnan(p) else "N/A"} for u1, u2, p in p_pairs])
                stats_df.to_excel(writer, sheet_name='Statistical_Details', index=False)
                
                try:
                    if is_microscope:
                        ws = writer.book['Normalized_Data']
                        ws.cell(row=2, column=4, value="💡 【箱ひげ図の最短作成手順】")
                        ws.cell(row=3, column=4, value="1. 左のA列とB列をすべて全選択します。")
                        ws.cell(row=4, column=4, value="2. [挿入]タブ ＞ [統計グラフ] ＞ [箱ひげ図] をクリックします。")
                    elif layout_mode == "下段ラベルでグループ化":
                        matrix_mean = pd.DataFrame(index=unique_up, columns=unique_low)
                        matrix_sd = pd.DataFrame(index=unique_up, columns=unique_low)
                        for i, uid in enumerate(internal_ids):
                            matrix_mean.at[upper_labels[i], lower_labels[i]] = np.nanmean(final_norm[uid])
                            matrix_sd.at[upper_labels[i], lower_labels[i]] = np.nanstd(final_norm[uid])
                        
                        matrix_mean.to_excel(writer, sheet_name='Summary_Matrix', startrow=1, startcol=0)
                        matrix_sd.to_excel(writer, sheet_name='Summary_Matrix', startrow=len(unique_up)+4, startcol=0)
                        
                        ws = writer.book['Summary_Matrix']
                        ws.cell(row=1, column=1, value="【平均値 (Mean)】")
                        ws.cell(row=len(unique_up)+4, column=1, value="【標準偏差 (SD)】")
                        
                        sc = len(unique_low) + 3
                        ws.cell(row=2, column=sc, value="💡 【グループ化棒グラフの最短作成手順】")
                        ws.cell(row=3, column=sc, value="1. 左上の【平均値】の表(A2から)を丸ごと選択し、[挿入] ＞ [2D 縦棒 (集合縦棒)] をクリック。")
                        ws.cell(row=4, column=sc, value="2. 追加された棒をクリックし、[誤差範囲] ＞ [その他の誤差範囲オプション] ＞ [カスタム]")
                        ws.cell(row=5, column=sc, value="3. 値の指定で、下の【標準偏差】の表の該当する行をドラッグして指定すれば完成です！")
                    else:
                        ws = writer.book['Summary']
                        sc = len(summary.columns) + 2
                        ws.cell(row=2, column=sc, value="💡 【エラーバー(SD)付き棒グラフの最短作成手順】")
                        ws.cell(row=3, column=sc, value="1. 左の『上段ラベル』と『平均』の列を選択し、[挿入] ＞ [縦棒グラフ] を作成。")
                        ws.cell(row=4, column=sc, value="2. グラフの棒をクリックし、[＋] ＞ [誤差範囲] ＞ [その他の誤差範囲オプション]。")
                        ws.cell(row=5, column=sc, value="3. 『カスタム』にチェックを入れ、『値の指定』。")
                        ws.cell(row=6, column=sc, value="4. 正負両方に、左の『SD』の数値をドラッグして指定すれば完成！")
                except: pass
                
        # --- 共通ダウンロード処理 ---
        buf_svg = io.BytesIO()
        fig.savefig(buf_svg, format='svg', bbox_inches='tight')
        
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1: st.download_button("📥 Excelデータをダウンロード (全データ・統計詳細シート同梱)", excel_buffer.getvalue(), "Analysis_Data.xlsx", type="primary", use_container_width=True)
        with col_dl2: st.download_button("📥 完成グラフ(SVG)を保存", buf_svg.getvalue(), "Graph.svg", "image/svg+xml", use_container_width=True)

    except Exception as e:
        st.error(f"エラーが発生しました:\n{traceback.format_exc()}")
