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
plt.rcParams['font.sans-serif'] = ['Arial', 'MS PGothic', 'IPAexGothic']
plt.rcParams['mathtext.fontset'] = 'custom'
plt.rcParams['mathtext.rm'] = 'Arial'
plt.rcParams['mathtext.it'] = 'Arial:italic'
plt.rcParams['mathtext.bf'] = 'Arial:bold'
plt.rcParams['svg.fonttype'] = 'none'

st.set_page_config(page_title="実験データ自動解析ツール", layout="wide")
st.title("🧪 実験データ自動解析ツール")

# テキストエリアの「自動折り返し」を防止し、横スクロールを有効にするCSS
st.markdown("""
    <style>
    textarea {
        white-space: pre !important;
        overflow-wrap: normal !important;
        overflow-x: scroll !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# サイドバー設定
# ==========================================
st.sidebar.header("⚙️ 全体設定")
selected_exp = st.sidebar.selectbox('実験手法:', ['Western Blotting (WB)', 'HPLC', 'qPCR', 'MTT Assay (細胞生存率)', '蛍光顕微鏡 (Box Plot)'])
num_cond = st.sidebar.number_input('手動モード時の条件数:', min_value=1, max_value=20, value=4, step=1)

is_mtt = 'MTT' in selected_exp
is_microscope = '顕微鏡' in selected_exp
is_qpcr = 'qPCR' in selected_exp
is_hplc = 'HPLC' in selected_exp

if 'WB' in selected_exp:
    t_label, t_ph, l_label, l_ph, y_label_def = 'Target:', '例: HO-1', 'Loading Control:', '例: HSP90', 'Relative Band Intensity'
elif 'HPLC' in selected_exp:
    t_label, t_ph, l_label, l_ph, y_label_def = '物質名:', '例: PpIX', 'タンパク質濃度:', '例: protein', 'Intracellular Concentration\n[nmol / mg ・ protein]'
elif 'qPCR' in selected_exp:
    t_label, t_ph, l_label, l_ph, y_label_def = 'Target:', '例: PDK1', 'Loading Control:', '例: β-ACTIN', 'Relative mRNA level'
elif is_mtt:
    t_label, t_ph, l_label, l_ph, y_label_def = '細胞株:', '例: PC3', '薬剤名:', '例: ALA', 'Cell Viability [%]'
elif is_microscope:
    t_label, t_ph, l_label, l_ph, y_label_def = '観察対象:', '例: ROS / GFP', '', '', 'Relative Fluorescence Intensity'

c_side1, c_side2 = st.sidebar.columns(2)
with c_side1: target_prot = st.text_input(t_label, placeholder=t_ph)
with c_side2: loading_prot = st.text_input(l_label, placeholder=l_ph) if not is_microscope else ""

t_name_raw = target_prot.strip()
l_name_raw = loading_prot.strip()

if is_mtt:
    t_name = t_name_raw or "Cell Line"
    l_name = l_name_raw or "Drug"
elif is_microscope:
    t_name = t_name_raw or "Target"
    l_name = ""
else:
    t_name = t_name_raw or "Target"
    l_name = l_name_raw or "Loading Control"

if is_mtt or is_microscope or is_hplc: 
    y_label_full = y_label_def
else: 
    y_label_full = f"{y_label_def}\n[{t_name} / {l_name}]"
    
ylabel_input = st.sidebar.text_area('Y軸ラベル:', value=y_label_full, height=68)

if not is_mtt:
    st.sidebar.markdown("---")
    st.sidebar.header("🖌️ レイアウト・配色設定")
    layout_mode = st.sidebar.radio("棒の配置:", ["均等に並べる", "条件ごとにグループ化"])
    color_mode = st.sidebar.radio("配色:", ["すべて黒", "上段ラベルで色分け（黒/グレー）"])
    
    default_width = 0.25 if layout_mode == "条件ごとにグループ化" else 0.17
    bar_width_input = st.sidebar.slider("棒の太さ調整:", min_value=0.05, max_value=0.80, value=default_width, step=0.01)
    
    pairing_options = ['独立 (Welch・ANOVA等)', 'ノンパラ (Mann-Whitney / Kruskal-Wallis等)'] if is_microscope else ['独立 (Welch・ANOVA等)', '対応あり (Paired等)']
    pairing_mode = st.sidebar.radio('統計検定:', pairing_options)
    norm_mode = st.sidebar.radio('規格化:', ['全体基準 (一番上の条件で全て規格化)', 'グループ基準 (下段ラベル毎の先頭条件で規格化)'])
    test_target_mode = st.sidebar.radio('検定範囲:', ['すべての条件間で検定', 'グループ内でのみ検定 (下段ラベルが同じ条件間)'])
else:
    layout_mode, color_mode, pairing_mode, norm_mode, test_target_mode = "", "", "", "", ""
    bar_width_input = 0.17

if not is_mtt:
    if layout_mode == "条件ごとにグループ化" and "色分け" in color_mode:
        u_label_name = "系列名"
        d_label_name = "横ラベル"
    else:
        u_label_name = "横ラベル上段"
        d_label_name = "横ラベル下段"
else:
    u_label_name, d_label_name = "", ""

if 'WB' in selected_exp or 'qPCR' in selected_exp:
    paste_t_label = 'Target'
    paste_l_label = 'Loading Control'
elif 'HPLC' in selected_exp:
    paste_t_label = '物質名'
    paste_l_label = 'タンパク質濃度'
else:
    paste_t_label = t_name
    paste_l_label = l_name

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
        with c1: mtt_ignore_row = st.text_input('空のWell(除外行):', 'A, H')
        with c2: mtt_ignore_col = st.text_input('空のWell(除外列):', '1')
        with c3: mtt_blank_col = st.text_input('バックグラウンド（培地のみ）(列):', '12')
        c4, c5 = st.columns(2)
        with c4: mtt_control_col = st.text_input('Control（細胞生存率100%の基準）(列):', '11')
        with c5: mtt_sample_cols = st.text_input('Sample(列):', '2-10')
        c6, c7, c8 = st.columns(3)
        with c6: mtt_start_conc = st.number_input('開始濃度:', value=4000.0)
        with c7: mtt_dilution = st.number_input('希釈倍率(n倍):', value=2.0)
        with c8: mtt_unit = st.text_input('単位:', 'μM')
        
        mtt_conc_direction = st.radio("濃度の配置方向:", ["左が高濃度 (右へ希釈)", "右が高濃度 (左へ希釈)"], horizontal=True)
        mtt_custom_xticks = st.text_input('横軸の目盛りに明示したい数値（カンマ区切りで追加指定、空欄なら自動）', value='', placeholder='例: 10, 50, 250')
        
        for i in range(num_cond):
            p_name = st.text_input(f'プレート {i+1} 条件名:', placeholder=f'例: プレート{i+1}', key=f"pname_{i}")
            p_data = st.text_area(f'プレート {i+1} データ (8行x12列):', placeholder='ここにペースト', height=220, key=f"pdata_{i}")
            input_data.append((p_name, p_data))
    else:
        # ★ 修正：蛍光顕微鏡の時はラジオボタンを出さず、手動モードのみに固定
        if is_microscope:
            input_mode = "手動で1条件ずつ入力"
        else:
            input_mode = st.radio("入力モード:", ["エクセル列ごとに一括ペースト（おすすめ✨）", "手動で1条件ずつ入力"], horizontal=True)
        
        if input_mode == "エクセル列ごとに一括ペースト（おすすめ✨）" and not is_microscope:
            st.info("💡 エクセル上で離れた列にあってもOK！必要な列だけを個別にコピーしてペーストしてください。\nペースト後に出現する表で、離れたサンプルを隣同士に整理できます。")
            
            c_n, c_t, c_l = st.columns(3)
            with c_n: bulk_n = st.text_area("1. 【名前】の列をペースト", height=150, placeholder="例:\nsiNC30\nsiNC30\nsiHSPA930")
            with c_l: bulk_l = st.text_area(f"2. 【{paste_l_label}】をペースト", height=150)
            with c_t: bulk_t = st.text_area(f"3. 【{paste_t_label}】をペースト", height=150)
            
            if bulk_n.strip():
                try:
                    n_lines = [line.strip() for line in bulk_n.replace('\r', '').split('\n') if line.strip()]
                    t_lines = [line.strip() for line in bulk_t.replace('\r', '').split('\n') if line.strip()] if bulk_t.strip() else []
                    l_lines = [line.strip() for line in bulk_l.replace('\r', '').split('\n') if line.strip()] if bulk_l.strip() else []

                    raw_dict = {}
                    for i, name in enumerate(n_lines):
                        if not name: continue
                        if name not in raw_dict: raw_dict[name] = {'t': [], 'l': []}
                        
                        if i < len(t_lines):
                            t_vals = [float(x) for x in re.sub(r'[\s,]+', ',', t_lines[i]).split(',') if x.strip()]
                            raw_dict[name]['t'].extend(t_vals)
                        if i < len(l_lines):
                            l_vals = [float(x) for x in re.sub(r'[\s,]+', ',', l_lines[i]).split(',') if x.strip()]
                            raw_dict[name]['l'].extend(l_vals)

                    unique_names = list(raw_dict.keys())
                    
                    st.markdown("### 🔄 サンプルの整理・並び替え")
                    st.write("Excelで離れていたサンプルも、**「表示順」**の数字を打ち換えることでグラフ上で隣同士にできます！")
                    
                    mapping_df = pd.DataFrame({
                        "表示順 (1,2,3...)": range(1, len(unique_names) + 1),
                        "エクセルの名前 (読取専用)": unique_names,
                        f"{u_label_name}": unique_names,
                        f"{d_label_name} (空欄可)": [""] * len(unique_names)
                    })
                    
                    edited_df = st.data_editor(mapping_df, hide_index=True, use_container_width=True, disabled=["エクセルの名前 (読取専用)"])
                    edited_df = edited_df.sort_values(by="表示順 (1,2,3...)")
                    
                    for _, row in edited_df.iterrows():
                        orig_name = row["エクセルの名前 (読取専用)"]
                        u_label = str(row[f"{u_label_name}"]) if pd.notna(row[f"{u_label_name}"]) and str(row[f"{u_label_name}"]).strip() else ""
                        d_label = str(row[f"{d_label_name} (空欄可)"]) if pd.notna(row[f"{d_label_name} (空欄可)"]) and str(row[f"{d_label_name} (空欄可)"]).strip() else ""
                        
                        t_data = '\n'.join(map(str, raw_dict[orig_name]['t']))
                        l_data = '\n'.join(map(str, raw_dict[orig_name]['l']))
                        input_data.append((u_label, d_label, t_data, l_data))
                            
                except Exception as e:
                    st.error("データの読み取りに失敗しました。数字や文字の形式を確認してください。")
        else:
            for i in range(num_cond):
                # ★ 修正：蛍光顕微鏡の時は1枠のみ（横幅3.0）に綺麗に整列、 Loading枠を非表示に
                if is_microscope:
                    col_up, col_dn, col_t = st.columns([1, 1, 3.0])
                    with col_up: n_up = st.text_input(f'{u_label_name}:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
                    with col_dn: n_down = st.text_input(f'{d_label_name}:', placeholder='(空欄可)', key=f"dn_{i}")
                    with col_t: n_t = st.text_area(f'{paste_t_label}:', placeholder='縦にペースト', height=100, key=f"t_{i}")
                    input_data.append((n_up, n_down, n_t))
                else:
                    col_up, col_dn, col_t, col_l = st.columns([1, 1, 1.5, 1.5])
                    with col_up: n_up = st.text_input(f'{u_label_name}:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
                    with col_dn: n_down = st.text_input(f'{d_label_name}:', placeholder='(空欄可)', key=f"dn_{i}")
                    with col_t: n_t = st.text_area(f'{paste_t_label}:', placeholder='縦にペースト', height=100, key=f"t_{i}")
                    with col_l: n_l = st.text_area(f'{paste_l_label}:', placeholder='縦にペースト', height=100, key=f"l_{i}")
                    input_data.append((n_up, n_down, n_t, n_l))

# ==========================================
# 🛡️ エラー完全回避(防弾)ヘルパー関数
# ==========================================
def parse_text(text):
    if not text.strip(): return [np.nan]
    res = []
    for line in text.replace(',', '\n').split('\n'):
        if line.strip():
            try: res.append(float(line.strip()))
            except ValueError: res.append(np.nan)
    return res if res else [np.nan]

def parse_plate(text):
    if not text.strip(): return np.full((8, 12), np.nan)
    lines = [line for line in text.replace('\r', '').split('\n')]
    data = []
    for line in lines:
        if not line.strip(): continue
        row = []
        parts = line.split('\t') if '\t' in line else re.sub(r'[\s,]+', ',', line.strip()).split(',')
        for x in parts:
            x = x.strip()
            if not x: row.append(np.nan)
            else:
                try: row.append(float(x))
                except ValueError: row.append(np.nan)
        while len(row) < 12: row.append(np.nan)
        data.append(row[:12])
    while len(data) < 8: data.append([np.nan] * 12)
    return np.array(data[:8])

def parse_idx(text, is_alpha=False):
    res = []
    try:
        for p in text.replace(' ', '').split(','):
            if not p: continue
            if '-' in p:
                start, end = p.split('-')
                if start and end: 
                    res.extend(range(ord(start.upper())-65, ord(end.upper())-65+1) if is_alpha else range(int(start)-1, int(end)))
            else: 
                res.append(ord(p.upper())-65 if is_alpha else int(p)-1)
    except Exception:
        pass 
    return list(set(res))

# ==========================================
# 解析・描画ロジック
# ==========================================
with col_graph:
    st.header("📊 リアルタイムプレビュー")
    st.info("💡 左の枠に文字を打つとグラフの枠が連動し、数値をペーストすると棒が出現します。")
    
    try:
        if is_mtt:
            i_rows, i_cols = parse_idx(mtt_ignore_row, True), parse_idx(mtt_ignore_col, False)
            b_cols, c_cols, s_cols = parse_idx(mtt_blank_col, False), parse_idx(mtt_control_col, False), parse_idx(mtt_sample_cols, False)
            s_cols.sort()
            valid_rows = [r for r in range(8) if r not in i_rows]
            
            safe_dilution = mtt_dilution if mtt_dilution != 0 else 1.0
            conc_vals_plot = [mtt_start_conc / (safe_dilution ** i) for i in range(len(s_cols))][::-1]
            
            if "左が高濃度" in mtt_conc_direction:
                s_cols_plot = s_cols[::-1]
            else:
                s_cols_plot = s_cols
            
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
                
                for spine in ax_i.spines.values(): spine.set_color('black'); spine.set_linewidth(1.2)
                ax_i.minorticks_off()
                
                if mtt_custom_xticks.strip() and len(conc_vals_plot) > 0:
                    try:
                        c_ticks = [float(x.strip()) for x in mtt_custom_xticks.split(',') if x.strip()]
                        all_x = conc_vals_plot + c_ticks
                        min_x, max_x = min(all_x), max(all_x)
                        low_exp = int(np.floor(np.log10(min_x)))
                        high_exp = int(np.ceil(np.log10(max_x)))
                        default_ticks = [10**e for e in range(low_exp, high_exp + 1)]
                        combined_ticks = sorted(list(set(default_ticks + c_ticks)))
                        ax_i.set_xticks(combined_ticks)
                        ax_i.get_xaxis().set_major_formatter(ticker.ScalarFormatter())
                        ax_i.set_xlim(min_x * 0.8, max_x * 1.2)
                    except: pass
                else:
                    ax_i.xaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: '{:g}'.format(y)))
                    
                ax_i.tick_params(direction='in', length=5, width=1.2, labelsize=12, colors='black', which='major')
                
                ax_i.set_ylabel(ylabel_input, fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
                ax_i.set_xlabel(f"{l_name} [{mtt_unit}]", fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
                n_indiv = max([np.count_nonzero(~np.isnan(plates_data[i][valid_rows, c])) for c in s_cols_plot]) if s_cols_plot else len(valid_rows)
                
                ax_i.set_title(f"n={n_indiv}", fontsize=14, pad=15, loc='right')
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
            
            plotted_stars = set()
            for idx_c, c in enumerate(s_cols_plot):
                col_data = [d[~np.isnan(d)] for d in [plates_data[p][valid_rows, c] for p in range(num_p)]]
                col_data_valid = [d for d in col_data if len(d) > 0]
                p_val = np.nan
                if len(col_data_valid) == 2: _, p_val = stats.ttest_ind(col_data_valid[0], col_data_valid[1], equal_var=False)
                elif len(col_data_valid) >= 3: _, p_val = stats.f_oneway(*col_data_valid)
                if not np.isnan(p_val) and p_val < 0.05:
                    stars = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*"
                    plotted_stars.add(stars)
                    max_y_at_c = max([np.nanmean(d)+np.nanstd(d) for d in col_data_valid])
                    ax.text(conc_vals_plot[idx_c], max_y_at_c + 6, stars, ha='center', va='bottom', fontsize=14, fontweight='bold', color='black')

            ax.set_xscale('log'); ax.set_ylim(bottom=0, top=125)
            ax.yaxis.set_major_locator(ticker.MultipleLocator(20))
            
            for spine in ax.spines.values(): spine.set_color('black'); spine.set_linewidth(1.2)
            ax.minorticks_off()
            
            if mtt_custom_xticks.strip() and len(conc_vals_plot) > 0:
                try:
                    c_ticks = [float(x.strip()) for x in mtt_custom_xticks.split(',') if x.strip()]
                    all_x = conc_vals_plot + c_ticks
                    min_x, max_x = min(all_x), max(all_x)
                    low_exp = int(np.floor(np.log10(min_x)))
                    high_exp = int(np.ceil(np.log10(max_x)))
                    default_ticks = [10**e for e in range(low_exp, high_exp + 1)]
                    combined_ticks = sorted(list(set(default_ticks + c_ticks)))
                    ax.set_xticks(combined_ticks)
                    ax.get_xaxis().set_major_formatter(ticker.ScalarFormatter())
                    ax.set_xlim(min_x * 0.8, max_x * 1.2)
                except: pass
            else:
                ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: '{:g}'.format(y)))
                
            ax.tick_params(direction='in', length=5, width=1.2, labelsize=12, colors='black', which='major')
            
            ax.set_ylabel(ylabel_input, fontsize=14, fontweight='bold', labelpad=8)
            ax.set_xlabel(f"{l_name} [{mtt_unit}]", fontsize=14, fontweight='bold', labelpad=8)
            
            if num_p > 1:
                ax.legend(loc='lower left', frameon=False, prop={'size': 13})
            
            mtt_test_desc = "Welch's t-test" if num_p == 2 else "One-way ANOVA followed by Tukey's test" if num_p >= 3 else ""
            max_n = max([np.count_nonzero(~np.isnan(plates_data[i][valid_rows, c])) for i in range(num_p) for c in s_cols_plot]) if num_p > 0 else 0
            
            star_str = ""
            if plotted_stars:
                star_texts = []
                if "*" in plotted_stars: star_texts.append("* p < 0.05")
                if "**" in plotted_stars: star_texts.append("** p < 0.01")
                if "***" in plotted_stars: star_texts.append("*** p < 0.001")
                star_str = ", " + ", ".join(star_texts)
                
            if mtt_test_desc:
                ax.set_title(f"{mtt_test_desc}{star_str}, n={max_n}", fontsize=14, pad=15, loc='right')
            else:
                ax.set_title(f"n={max_n}", fontsize=14, pad=15, loc='right')

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
            
            has_data = any(len([v for v in raw_processed[uid] if not np.isnan(v)]) > 0 for uid in internal_ids)
            if not has_data:
                st.stop()
                
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
                if is_grouped_test && lower_labels[internal_ids.index(u1)] != lower_labels[internal_ids.index(u2)]: continue
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
            
            fig, ax = plt.subplots(figsize=(max(4.0, len(internal_ids)*1.5+1.5), 5.5))
            fig.patch.set_facecolor('white')
            ax.set_facecolor('white')
            
            x_coords = {}
            bar_width = bar_width_input
            
            if layout_mode == "条件ごとにグループ化":
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

            if is_microscope:
                positions = [x_coords[uid] for uid in internal_ids]
                box_data = [[v for v in final_norm[uid] if not np.isnan(v)] for uid in internal_ids]
                ax.boxplot(box_data, positions=positions, widths=bar_width*1.5, patch_artist=True, 
                           boxprops=dict(facecolor='white', color='black', linewidth=1.2), 
                           capprops=dict(color='black', linewidth=1.2),
                           whiskerprops=dict(color='black', linewidth=1.2),
                           medianprops=dict(color='black', linewidth=1.5), 
                           flierprops=dict(marker='o', markerfacecolor='black', markeredgecolor='black', alpha=0.8, markersize=4))
            else:
                for i, uid in enumerate(internal_ids):
                    mean_val = np.nanmean(final_norm[uid])
                    sd_val = np.nanstd(final_norm[uid])
                    ax.bar(x_coords[uid], mean_val if not np.isnan(mean_val) else 0, yerr=sd_val if not np.isnan(sd_val) else 0, 
                           width=bar_width, color=palette[upper_labels[i]], edgecolor='black', capsize=3, error_kw=dict(ecolor='black', lw=1.2), 
                           label=upper_labels[i] if i == upper_labels.index(upper_labels[i]) else "")

            for spine in ax.spines.values():
                spine.set_visible(True); spine.set_color('black'); spine.set_linewidth(1.5)
            ax.tick_params(axis='y', colors='black', direction='in', left=True, right=False, length=5, width=1.5, labelsize=14)
            ax.tick_params(axis='x', bottom=False, top=False)
            
            ax.set_xticklabels([]) 
            trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
            
            if layout_mode == "条件ごとにグループ化" and "色分け" in color_mode:
                for low in unique_low:
                    members = [i for i, l in enumerate(lower_labels) if l == low]
                    xs = [x_coords[internal_ids[i]] for i in members]
                    if xs: ax.text(sum(xs) / len(xs), -0.05, low, ha='center', va='top', transform=trans, fontsize=16, fontweight='bold', color='black')
            else:
                for i, uid in enumerate(internal_ids):
                    ax.text(x_coords[uid], -0.05, upper_labels[i], ha='center', va='top', transform=trans, fontsize=16, color='black', fontweight='bold')
                grouped_lower = [(k, list(g)) for k, g in itertools.groupby(enumerate(lower_labels), key=lambda x: x[1])]
                for label, elements in grouped_lower:
                    if not label: continue
                    xs = [x_coords[internal_ids[x[0]]] for x in elements]
                    x_start, x_end = min(xs), max(xs)
                    if x_start != x_end:
                        ax.plot([x_start - bar_width/2, x_end + bar_width/2], [-0.16, -0.16], color='black', lw=1.5, transform=trans, clip_on=False)
                    ax.text((x_start + x_end) / 2, -0.21, label, ha='center', va='top', transform=trans, fontsize=16, fontweight='bold', color='black')

            all_vals = [v for vals in final_norm.values() for v in vals if not np.isnan(v)]
            max_y = max(all_vals + [0]) if all_vals else 1.0
            if max_y == 0: max_y = 1.0
            
            y_shift, h, base_bracket_y = max_y * 0.15, max_y * 0.025, max_y * 1.15
            levels, max_level, sig_pairs = [], 0, []
            for u1, u2, p in p_pairs:
                if p >= 0.05 or np.isnan(p): continue
                stars = "***" if p < 0.001 else "**" if p < 0.01 else "*"
                x1, x2 = x_coords[u1], x_coords[u2]
                sig_pairs.append((min(x1, x2), max(x1, x2), stars))
            
            plotted_stars = set()
            sig_pairs.sort(key=lambda x: x[1] - x[0])
            for x_start, x_end, stars in sig_pairs:
                plotted_stars.add(stars)
                placed_level = -1
                for l_idx, intervals in enumerate(levels):
                    if not any(not (x_end < s or x_start > e) for s, e in intervals): placed_level = l_idx; break
                if placed_level == -1: placed_level = len(levels); levels.append([])
                levels[placed_level].append((x_start, x_end))
                max_level = max(max_level, placed_level)
                by = base_bracket_y + placed_level * y_shift
                ax.plot([x_start, x_start, x_end, x_end], [by - h, by, by, by - h], color='black', lw=1.2)
                ax.text((x_start + x_end) / 2, by + h*0.2, stars, ha='center', va='bottom', color='black', fontsize=14, fontweight='bold')

            ax.set_ylim(0, base_bracket_y + (max_level + 1) * y_shift if sig_pairs else max_y * 1.3)
            x_vals = list(x_coords.values())
            if x_vals: ax.set_xlim(min(x_vals) - 0.6, max(x_vals) + 0.6)
            ax.set_ylabel(ylabel_input, fontsize=16, fontweight="bold", color='black', labelpad=10)
            
            if "色分け" in color_mode:
                handles, labels = ax.get_legend_handles_labels()
                by_label = dict(zip(labels, handles))
                if by_label: ax.legend(by_label.values(), by_label.keys(), loc='upper right', frameon=False, prop={'size': 12, 'weight': 'bold'})

            n_list = [len([v for v in raw_processed[u] if not np.isnan(v)]) for u in internal_ids]
            expected_n = n_list[0] if n_list and len(set(n_list)) == 1 else "varies"
            
            if is_grouped_test:
                g_lens = [len([u for u in internal_ids if lower_labels[internal_ids.index(u)] == low]) for low in unique_low]
                max_g_len = max(g_lens) if g_lens else 0
                if max_g_len == 2: test_desc_flat = "Mann-Whitney U" if is_non_param else "Paired t-test" if is_paired else "Welch's t-test"
                elif max_g_len >= 3: test_desc_flat = "Kruskal-Wallis (Holm)" if is_non_param else "Paired t-test (Holm)" if is_paired else "One-way ANOVA followed by Tukey's test"
                else: test_desc_flat = ""
            else:
                num_g = len(internal_ids)
                if num_g == 2: test_desc_flat = "Mann-Whitney U" if is_non_param else "Paired t-test" if is_paired else "Welch's t-test"
                elif num_g >= 3: test_desc_flat = "Kruskal-Wallis (Holm)" if is_non_param else "Paired t-test (Holm)" if is_paired else "One-way ANOVA followed by Tukey's test"
                else: test_desc_flat = ""
                
            star_str = ""
            if plotted_stars:
                star_texts = []
                if "*" in plotted_stars: star_texts.append("* p < 0.05")
                if "**" in plotted_stars: star_texts.append("** p < 0.01")
                if "***" in plotted_stars: star_texts.append("*** p < 0.001")
                star_str = ", " + ", ".join(star_texts)
                
            if is_microscope:
                title_str = f"{test_desc_flat}{star_str}" if test_desc_flat else ""
                if title_str: ax.set_title(title_str, fontsize=14, pad=15, loc='right')
            else:
                title_str = f"{test_desc_flat}{star_str}, n={expected_n}" if test_desc_flat else f"n={expected_n}"
                ax.set_title(title_str, fontsize=14, pad=15, loc='right')

            st.pyplot(fig)
            
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
                    elif layout_mode == "条件ごとにグループ化":
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
                
        buf_svg = io.BytesIO()
        fig.savefig(buf_svg, format='svg', bbox_inches='tight')
        
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1: st.download_button("📥 Excelデータをダウンロード", excel_buffer.getvalue(), "Analysis_Data.xlsx", type="primary", use_container_width=True)
        with col_dl2: st.download_button("📥 完成グラフ(SVG)を保存", buf_svg.getvalue(), "Graph.svg", "image/svg+xml", use_container_width=True)

    except Exception as e:
        pass
