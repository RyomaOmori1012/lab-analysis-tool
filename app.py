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
from openpyxl.chart import BarChart, LineChart, Reference
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
st.markdown("ペーストするだけで、統計処理から論文用グラフ（SVG）とExcel出力までを自動で行います。")

# ==========================================
# UIパーツの構築
# ==========================================
st.sidebar.header("⚙️ 全体設定")
selected_exp = st.sidebar.selectbox('実験手法:', ['Western Blotting (WB)', 'HPLC', 'qPCR', 'MTT Assay (細胞生存率)', '蛍光顕微鏡 (Box Plot)'])
num_cond = st.sidebar.number_input('総条件数(Control含):', min_value=1, max_value=20, value=4, step=1)

# 手法に応じたデフォルトラベルとUI表示の制御
is_mtt = 'MTT' in selected_exp
is_microscope = '顕微鏡' in selected_exp
is_qpcr = 'qPCR' in selected_exp

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
with col1:
    target_prot = st.text_input(t_label, placeholder=t_ph)
with col2:
    if not is_microscope:
        loading_prot = st.text_input(l_label, placeholder=l_ph)
    else:
        loading_prot = ""

t_name = target_prot.strip() or "Target"
l_name = loading_prot.strip() or "Loading"

if is_mtt:
    y_label_full = y_label_def
elif is_microscope:
    y_label_full = y_label_def
else:
    y_label_full = f"{y_label_def}\n[{t_name} / {l_name}]"

ylabel_input = st.sidebar.text_area('Y軸ラベル:', value=y_label_full, height=68)

if not is_mtt:
    if is_microscope:
        pairing_options = ['独立 (Welch・ANOVA等)', 'ノンパラ (Mann-Whitney / Kruskal-Wallis等)']
    else:
        pairing_options = ['独立 (Welch・ANOVA等)', '対応あり (Paired等)']
    
    pairing_mode = st.sidebar.radio('検定手法:', pairing_options)
    norm_mode = st.sidebar.radio('規格化:', ['全体基準 (一番上の条件で全て規格化)', 'グループ基準 (下段ラベル毎の先頭条件で規格化)'])
    test_target_mode = st.sidebar.radio('検定範囲:', ['すべての条件間で検定', 'グループ内でのみ検定 (下段ラベルが同じ条件間)'])
else:
    pairing_mode, norm_mode, test_target_mode = "", "", ""

st.markdown("---")

# ==========================================
# データ入力エリア
# ==========================================
st.header("📝 データ入力")
input_data = []

if is_mtt:
    st.info("💡 **【MTTアッセイ モード】** Excelから8行x12列のデータをそのままペーストしてください。")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: mtt_ignore_row = st.text_input('空(除外行):', 'A, H')
    with col2: mtt_ignore_col = st.text_input('空(除外列):', '1')
    with col3: mtt_blank_col = st.text_input('Blank(列):', '12')
    with col4: mtt_control_col = st.text_input('Control(列):', '11')
    with col5: mtt_sample_cols = st.text_input('Sample(列):', '2-10')
    
    col6, col7, col8 = st.columns(3)
    with col6: mtt_start_conc = st.number_input('開始濃度:', value=4000.0)
    with col7: mtt_dilution = st.number_input('希釈倍率(n倍):', value=2.0)
    with col8: mtt_unit = st.text_input('単位:', 'μM')
    
    for i in range(num_cond):
        st.markdown(f"**プレート {i+1}**")
        p_name = st.text_input('条件名:', placeholder=f'例: プレート{i+1}', key=f"pname_{i}")
        p_data = st.text_area('データ (8行x12列):', placeholder='ここにペースト', height=150, key=f"pdata_{i}")
        input_data.append((p_name, p_data))
        
elif is_microscope:
    st.info("💡 **【蛍光顕微鏡 モード】** 各細胞の輝度データを縦にペーストしてください。n数はバラバラでもOKです。")
    for i in range(num_cond):
        st.markdown(f"**条件 {i+1}**")
        col_up, col_dn, col_val = st.columns([1, 1, 2])
        with col_up: n_up = st.text_input('上段ラベル:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
        with col_dn: n_down = st.text_input('下段ラベル:', placeholder='(空欄可)', key=f"dn_{i}")
        with col_val: n_val = st.text_area(f'{t_name}:', placeholder='数値を縦にコピペ', height=100, key=f"val_{i}")
        input_data.append((n_up, n_down, n_val))
        
else:
    t_ph = 'Ct値を縦にコピペ' if is_qpcr else '数値を縦にコピペ'
    l_ph = 'Ct値を縦にコピペ' if is_qpcr else '数値を縦にコピペ'
    
    for i in range(num_cond):
        st.markdown(f"**条件 {i+1}**")
        col_up, col_dn, col_t, col_l = st.columns([1, 1, 1.5, 1.5])
        with col_up: n_up = st.text_input('上段ラベル:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
        with col_dn: n_down = st.text_input('下段ラベル:', placeholder='(空欄可)', key=f"dn_{i}")
        with col_t: n_t = st.text_area(f'{t_name}:', placeholder=t_ph, height=100, key=f"t_{i}")
        with col_l: n_l = st.text_area(f'{l_name}:', placeholder=l_ph, height=100, key=f"l_{i}")
        input_data.append((n_up, n_down, n_t, n_l))

st.markdown("---")

# ==========================================
# ヘルパー関数
# ==========================================
def parse_plate(text):
    lines = [line for line in text.replace('\r', '').split('\n') if line.strip()]
    data = []
    for line in lines:
        if '\t' in line:
            row = [float(x) if x.strip() else np.nan for x in line.split('\t')]
        else:
            row = [float(x) if x.strip() else np.nan for x in re.sub(r'[\s,]+', ',', line.strip()).split(',')]
        while len(row) < 12: row.append(np.nan)
        data.append(row[:12])
    arr = np.array(data)
    if arr.shape != (8, 12): raise ValueError("8行12列である必要があります")
    return arr

def parse_idx(text, is_alpha=False):
    res = []
    parts = text.replace(' ', '').split(',')
    for p in parts:
        if not p: continue
        if '-' in p:
            start, end = p.split('-')
            if is_alpha: res.extend(list(range(ord(start.upper())-65, ord(end.upper())-65+1)))
            else: res.extend(list(range(int(start)-1, int(end))))
        else:
            if is_alpha: res.append(ord(p.upper())-65)
            else: res.append(int(p)-1)
    return list(set(res))

def parse_text(text):
    raw_lines = text.replace(',', '\n').split('\n')
    return [float(line.strip()) for line in raw_lines if line.strip()]

# ==========================================
# 解析実行
# ==========================================
if st.button("📊 データ確定 ＆ 自動解析実行", type="primary"):
    with st.spinner("解析中..."):
        try:
            if is_mtt:
                i_rows = parse_idx(mtt_ignore_row, True)
                i_cols = parse_idx(mtt_ignore_col, False)
                b_cols = parse_idx(mtt_blank_col, False)
                c_cols = parse_idx(mtt_control_col, False)
                s_cols = parse_idx(mtt_sample_cols, False)
                s_cols.sort()
                
                valid_rows = [r for r in range(8) if r not in i_rows]
                conc_vals_raw = [mtt_start_conc / (mtt_dilution ** i) for i in range(len(s_cols))]
                s_cols_plot = s_cols[::-1]
                conc_vals_plot = conc_vals_raw[::-1]
                
                plates_data, plate_names, ctrl_sd_pct_list, ctrl_n_list = [], [], [], []
                global_blank_mean = 0.0
                global_ctrl_mean = None
                
                for idx, (p_name_w, p_data_w) in enumerate(input_data):
                    if not p_data_w.strip(): continue
                    p_name = p_name_w.strip() or f"Condition {idx+1}"
                    arr = parse_plate(p_data_w)
                    plate_names.append(p_name)
                    
                    blank_vals = [arr[r, c] for r in valid_rows for c in b_cols if c not in i_cols]
                    blank_vals = [v for v in blank_vals if not np.isnan(v)]
                    if len(blank_vals) > 0:
                        blank_mean = np.nanmean(blank_vals)
                        global_blank_mean = blank_mean
                    else: blank_mean = global_blank_mean
                    
                    ctrl_vals = [arr[r, c] - blank_mean for r in valid_rows for c in c_cols if c not in i_cols]
                    ctrl_vals = [v for v in ctrl_vals if not np.isnan(v)]
                    
                    if len(ctrl_vals) > 0:
                        ctrl_mean = np.nanmean(ctrl_vals)
                        global_ctrl_mean = ctrl_mean
                        ctrl_sd_pct = (np.nanstd(ctrl_vals) / ctrl_mean) * 100 if ctrl_mean else 0
                        ctrl_sd_pct_list.append(ctrl_sd_pct)
                        ctrl_n_list.append(len(ctrl_vals))
                    else:
                        ctrl_mean = global_ctrl_mean if global_ctrl_mean is not None else 1.0
                        ctrl_sd_pct_list.append(0.0)
                        ctrl_n_list.append(0)
                        
                    norm_arr = (arr - blank_mean) / ctrl_mean * 100
                    plates_data.append(norm_arr)
                
                num_p = len(plates_data)
                if num_p == 0:
                    st.error("解析可能なデータがありません。")
                    st.stop()

                colors = sns.color_palette("Set1", max(num_p, 2)) if num_p > 1 else ['black']
                x_axis_title = f"{l_name} [{mtt_unit}]" if mtt_unit else l_name
                
                # --- MTT グラフ描画 ---
                figs = []
                for i in range(num_p):
                    fig, ax = plt.subplots(figsize=(6, 4))
                    means = [np.nanmean(plates_data[i][valid_rows, c]) for c in s_cols_plot]
                    sds = [np.nanstd(plates_data[i][valid_rows, c]) for c in s_cols_plot]
                    ax.errorbar(conc_vals_plot, means, yerr=sds, fmt='-o', color='black', capsize=4, mfc='black', mec='black', lw=1.5)
                    ax.set_xscale('log')
                    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: '{:g}'.format(y)))
                    ax.set_ylim(bottom=0, top=125)
                    ax.yaxis.set_major_locator(ticker.MultipleLocator(20))
                    for spine in ax.spines.values(): spine.set_color('black'); spine.set_linewidth(1.2)
                    ax.tick_params(direction='in', length=5, width=1.2, labelsize=12)
                    ax.set_ylabel(ylabel_input, fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
                    ax.set_xlabel(x_axis_title, fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
                    n_indiv = max([np.count_nonzero(~np.isnan(plates_data[i][valid_rows, c])) for c in s_cols_plot]) if s_cols_plot else len(valid_rows)
                    ax.set_title(f"n={n_indiv}", fontsize=14, pad=15, fontname='Arial')
                    figs.append((f"MTT_Graph_{plate_names[i]}.svg", fig))
                
                fig_comb = None
                if num_p > 1:
                    fig_comb, ax = plt.subplots(figsize=(7, 5))
                    for i in range(num_p):
                        means = [np.nanmean(plates_data[i][valid_rows, c]) for c in s_cols_plot]
                        sds = [np.nanstd(plates_data[i][valid_rows, c]) for c in s_cols_plot]
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
                            
                    ax.set_xscale('log')
                    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: '{:g}'.format(y)))
                    ax.set_xlim(left=conc_vals_plot[0]*0.7, right=conc_vals_plot[-1]*2.0)
                    ax.set_ylim(bottom=0, top=125)
                    ax.yaxis.set_major_locator(ticker.MultipleLocator(20))
                    for spine in ax.spines.values(): spine.set_color('black'); spine.set_linewidth(1.2)
                    ax.tick_params(direction='in', length=5, width=1.2, labelsize=12)
                    ax.set_ylabel(ylabel_input, fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
                    ax.set_xlabel(x_axis_title, fontsize=14, fontweight='bold', fontname='Arial', labelpad=8)
                    
                    mtt_test_desc = "Welch's t-test" if num_p == 2 else "One-way ANOVA followed by Tukey test"
                    n_comb = max([np.count_nonzero(~np.isnan(plates_data[p][valid_rows, c])) for p in range(num_p) for c in s_cols_plot]) if s_cols_plot else len(valid_rows)
                    ax.set_title(f"{mtt_test_desc}, n={n_comb}", fontsize=14, pad=15, fontname='Arial')
                    ax.legend(loc='lower left', frameon=False, prop={'family': 'Arial', 'size': 13})
                
                # --- Excel作成 ---
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    mtt_summary_dict = {"濃度 (Concentration)": [0.0] + [float(x) for x in conc_vals_plot]}
                    for i, p_name in enumerate(plate_names):
                        mtt_summary_dict[f"{p_name}_Mean(%)"] = [100.0] + [float(np.nanmean(plates_data[i][valid_rows, c])) for c in s_cols_plot]
                        mtt_summary_dict[f"{p_name}_SD(%)"] = [float(ctrl_sd_pct_list[i])] + [float(np.nanstd(plates_data[i][valid_rows, c])) for c in s_cols_plot]
                    summary_df_mtt = pd.DataFrame(mtt_summary_dict)
                    summary_df_mtt.to_excel(writer, sheet_name='Summary', index=False)
                    
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

                    # ガイド
                    worksheet = writer.book['Summary']
                    sc = len(summary_df_mtt.columns) + 2
                    worksheet.cell(row=2, column=sc, value="💡 【エラーバー(SD)付き折れ線グラフの最短作成手順】")
                    worksheet.cell(row=3, column=sc, value="1. 左の表の濃度(A列)と各条件の『Mean』の列だけをCtrlキーで選択し、[挿入] ＞ [散布図(直線とマーカー)]")
                    worksheet.cell(row=4, column=sc, value="2. グラフ上の線をクリックし、[＋] ＞ [誤差範囲] ＞ [その他の誤差範囲オプション]")
                    worksheet.cell(row=5, column=sc, value="3. 『両方向』『キャップ』にし、『カスタム』にチェックを入れ『値の指定』")
                    worksheet.cell(row=6, column=sc, value="4. 正負の誤差値の両方に、該当条件の『SD』列の数値をドラッグして指定すれば完成！")

                # 結果表示
                st.success("解析が完了しました！")
                st.markdown("### 📊 統合比較グラフ")
                if fig_comb: st.pyplot(fig_comb)
                for name, f in figs:
                    buf = io.BytesIO()
                    f.savefig(buf, format='svg', bbox_inches='tight')
                    st.download_button(label=f"📥 {name} (SVG)", data=buf.getvalue(), file_name=name, mime="image/svg+xml")
                if fig_comb:
                    buf_c = io.BytesIO()
                    fig_comb.savefig(buf_c, format='svg', bbox_inches='tight')
                    st.download_button(label="📥 統合グラフ (SVG)", data=buf_c.getvalue(), file_name="MTT_Combined_Graph.svg", mime="image/svg+xml")
                
                st.download_button(label="📥 Excelデータをダウンロード", data=excel_buffer.getvalue(), file_name="MTT_Analysis_Data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

            # ==========================================
            # 🟢 WB / HPLC / qPCR / 顕微鏡の処理
            # ==========================================
            else:
                is_paired = '対応あり' in pairing_mode
                is_non_param = 'ノンパラ' in pairing_mode
                is_grouped_norm = 'グループ' in norm_mode
                is_grouped_test = 'グループ内' in test_target_mode
                
                upper_labels, lower_labels, internal_group_ids, raw_processed = [], [], [], {}
                expected_n = None
                
                for idx, item in enumerate(input_data):
                    if is_microscope:
                        up_w, down_w, val_w = item
                        if not val_w.strip(): continue
                        t_nums = parse_text(val_w)
                        raw_processed[f"Cond_{idx}"] = t_nums
                    else:
                        up_w, down_w, target_w, loading_w = item
                        if not target_w.strip() or not loading_w.strip(): continue
                        t_nums = parse_text(target_w)
                        l_nums = parse_text(loading_w)
                        if len(t_nums) != len(l_nums):
                            st.error(f"エラー: {up_w.strip() or f'Cond_{idx+1}'} のデータ数が一致しません。")
                            st.stop()
                        if is_qpcr: raw_processed[f"Cond_{idx}"] = [t - l for t, l in zip(t_nums, l_nums)]
                        else: raw_processed[f"Cond_{idx}"] = [t / l for t, l in zip(t_nums, l_nums)]
                    
                    up_text = up_w.strip() or f"Cond_{idx+1}"
                    down_text = down_w.strip() or ""
                    upper_labels.append(up_text)
                    lower_labels.append(down_text)
                    internal_group_ids.append(f"Cond_{idx}")
                    
                    if not is_microscope:
                        if is_paired:
                            if expected_n is None: expected_n = len(t_nums)
                            elif len(t_nums) != expected_n:
                                st.error("エラー: 「対応あり」モードではすべてのn数を揃える必要があります。")
                                st.stop()
                        else:
                            if expected_n is None: expected_n = len(t_nums)
                
                if len(internal_group_ids) < 2:
                    st.error("エラー: 解析するには最低2つ以上の条件にデータを入力してください。")
                    st.stop()

                final_normalized_data = {}
                if is_grouped_norm:
                    group_controls = {}
                    for uid, down_label in zip(internal_group_ids, lower_labels):
                        if down_label not in group_controls: group_controls[down_label] = uid
                    for idx, uid in enumerate(internal_group_ids):
                        c_uid = group_controls[lower_labels[idx]]
                        if is_qpcr:
                            if is_paired: final_normalized_data[uid] = [2 ** -(dc - c_dc) for dc, c_dc in zip(raw_processed[uid], raw_processed[c_uid])]
                            else: final_normalized_data[uid] = [2 ** -(dc - np.mean(raw_processed[c_uid])) for dc in raw_processed[uid]]
                        else:
                            if is_paired: final_normalized_data[uid] = [r / c_r for r, c_r in zip(raw_processed[uid], raw_processed[c_uid])]
                            else: final_normalized_data[uid] = [r / np.mean(raw_processed[c_uid]) for r in raw_processed[uid]]
                else:
                    c_uid = internal_group_ids[0]
                    for uid in internal_group_ids:
                        if is_qpcr:
                            if is_paired: final_normalized_data[uid] = [2 ** -(dc - c_dc) for dc, c_dc in zip(raw_processed[uid], raw_processed[c_uid])]
                            else: final_normalized_data[uid] = [2 ** -(dc - np.mean(raw_processed[c_uid])) for dc in raw_processed[uid]]
                        else:
                            if is_paired: final_normalized_data[uid] = [r / c_r for r, c_r in zip(raw_processed[uid], raw_processed[c_uid])]
                            else: final_normalized_data[uid] = [r / np.mean(raw_processed[c_uid]) for r in raw_processed[uid]]

                # --- 統計検定 ---
                p_values_to_show = []
                test_desc_flat = ""
                num_groups = len(internal_group_ids)
                
                if is_grouped_test:
                    groups_dict = {}
                    for idx, uid in enumerate(internal_group_ids):
                        groups_dict.setdefault(lower_labels[idx], []).append(uid)
                    
                    first_g_len = len(list(groups_dict.values())[0])
                    if first_g_len == 2: test_desc_flat = "Mann-Whitney U test" if is_non_param else "Paired t-test" if is_paired else "Welch's t-test"
                    elif first_g_len >= 3: test_desc_flat = "Kruskal-Wallis followed by Mann-Whitney U (Holm)" if is_non_param else "Paired t-test (Holm)" if is_paired else "One-way ANOVA followed by Tukey test"
                    
                    for down_label, uids in groups_dict.items():
                        if len(uids) == 2:
                            if is_non_param: _, p_val = stats.mannwhitneyu(raw_processed[uids[0]], raw_processed[uids[1]])
                            elif is_paired: _, p_val = stats.ttest_rel(raw_processed[uids[0]], raw_processed[uids[1]])
                            else: _, p_val = stats.ttest_ind(raw_processed[uids[0]], raw_processed[uids[1]], equal_var=False)
                            p_values_to_show.append((uids[0], uids[1], p_val))
                        elif len(uids) >= 3:
                            if is_non_param or is_paired:
                                pairs = list(combinations(uids, 2))
                                raw_ps = [stats.mannwhitneyu(raw_processed[u1], raw_processed[u2]).pvalue if is_non_param else stats.ttest_rel(raw_processed[u1], raw_processed[u2]).pvalue for u1, u2 in pairs]
                                _, corr_ps, _, _ = multipletests(raw_ps, method='holm')
                                for i, (u1, u2) in enumerate(pairs): p_values_to_show.append((u1, u2, corr_ps[i]))
                            else:
                                all_vals = [v for u in uids for v in raw_processed[u]]
                                all_groups = [u for u in uids for _ in raw_processed[u]]
                                tukey = pairwise_tukeyhsd(endog=all_vals, groups=all_groups, alpha=0.05)
                                gu = tukey.groupsunique
                                for i, j in combinations(range(len(gu)), 2):
                                    # scipy/statsmodelsの仕様でインデックスを取得
                                    idx_pair = list(combinations(range(len(gu)), 2)).index((i, j))
                                    p_values_to_show.append((gu[i], gu[j], tukey.pvalues[idx_pair]))
                else:
                    if num_groups == 2:
                        u1, u2 = internal_group_ids[0], internal_group_ids[1]
                        test_desc_flat = "Mann-Whitney U test" if is_non_param else "Paired t-test" if is_paired else "Welch's t-test"
                        if is_non_param: _, p_val = stats.mannwhitneyu(raw_processed[u1], raw_processed[u2])
                        elif is_paired: _, p_val = stats.ttest_rel(raw_processed[u1], raw_processed[u2])
                        else: _, p_val = stats.ttest_ind(raw_processed[u1], raw_processed[u2], equal_var=False)
                        p_values_to_show.append((u1, u2, p_val))
                    elif num_groups >= 3:
                        if is_non_param or is_paired:
                            test_desc_flat = "Kruskal-Wallis followed by Mann-Whitney U (Holm)" if is_non_param else "Paired t-test (Holm)"
                            pairs = list(combinations(internal_group_ids, 2))
                            raw_ps = [stats.mannwhitneyu(raw_processed[u1], raw_processed[u2]).pvalue if is_non_param else stats.ttest_rel(raw_processed[u1], raw_processed[u2]).pvalue for u1, u2 in pairs]
                            _, corr_ps, _, _ = multipletests(raw_ps, method='holm')
                            for i, (u1, u2) in enumerate(pairs): p_values_to_show.append((u1, u2, corr_ps[i]))
                        else:
                            test_desc_flat = "One-way ANOVA followed by Tukey test"
                            all_vals = [v for u in internal_group_ids for v in raw_processed[u]]
                            all_groups = [u for u in internal_group_ids for _ in raw_processed[u]]
                            tukey = pairwise_tukeyhsd(endog=all_vals, groups=all_groups, alpha=0.05)
                            gu = tukey.groupsunique
                            for i, j in combinations(range(len(gu)), 2):
                                idx_pair = list(combinations(range(len(gu)), 2)).index((i, j))
                                p_values_to_show.append((gu[i], gu[j], tukey.pvalues[idx_pair]))

                # --- グラフ描画 ---
                fig, ax = plt.subplots(figsize=(max(4.0, len(internal_group_ids)*1.5+1.5), 5.5))
                x_pos = np.arange(len(internal_group_ids))
                
                if is_microscope:
                    box_data = [final_normalized_data[uid] for uid in internal_group_ids]
                    ax.boxplot(box_data, positions=x_pos, widths=0.4, patch_artist=True, 
                               boxprops=dict(facecolor='white', color='black', linewidth=1.2), 
                               capprops=dict(color='black', linewidth=1.2), whiskerprops=dict(color='black', linewidth=1.2),
                               medianprops=dict(color='black', linewidth=1.5), flierprops=dict(marker='o', markerfacecolor='black', markeredgecolor='black', alpha=0.8, markersize=4))
                else:
                    means = [np.mean(final_normalized_data[uid]) for uid in internal_group_ids]
                    sds = [np.std(final_normalized_data[uid]) for uid in internal_group_ids]
                    ax.bar(x_pos, means, yerr=sds, color='black', edgecolor='black', width=0.17, capsize=3, error_kw=dict(ecolor='black', lw=1.2))
                
                for spine in ax.spines.values(): spine.set_linewidth(1.5)
                ax.tick_params(direction='in', left=True, right=False, length=5, width=1.5, labelsize=14)
                ax.tick_params(axis='x', bottom=False, top=False)
                ax.set_xlim(-0.6, len(internal_group_ids) - 0.4)
                
                max_y = max([v for vals in final_normalized_data.values() for v in vals]) if final_normalized_data else 1
                y_shift, h, base_bracket_y = max_y * 0.15, max_y * 0.025, max_y * 1.15
                levels, max_level, sig_pairs = [], 0, []
                
                for u1, u2, p_val in p_values_to_show:
                    if p_val < 0.001: stars = "***"
                    elif p_val < 0.01: stars = "**"
                    elif p_val < 0.05: stars = "*"
                    else: continue
                    idx1, idx2 = internal_group_ids.index(u1), internal_group_ids.index(u2)
                    sig_pairs.append((min(idx1, idx2), max(idx1, idx2), stars))
                
                sig_pairs.sort(key=lambda x: x[1] - x[0])
                for s_idx, e_idx, stars in sig_pairs:
                    placed_level = -1
                    for l_idx, intervals in enumerate(levels):
                        if not any(not (e_idx < s or s_idx > e) for s, e in intervals):
                            placed_level = l_idx; break
                    if placed_level == -1: placed_level = len(levels); levels.append([])
                    levels[placed_level].append((s_idx, e_idx))
                    max_level = max(max_level, placed_level)
                    by = base_bracket_y + placed_level * y_shift
                    ax.plot([s_idx, s_idx, e_idx, e_idx], [by-h, by, by, by-h], color='black', lw=1.2)
                    ax.text((s_idx+e_idx)/2, by+h*0.2, stars, ha='center', va='bottom', fontsize=14, fontweight='bold')
                    
                ax.set_ylim(0, base_bracket_y + (max_level + 1) * y_shift if sig_pairs else max_y * 1.3)
                ax.set_title(test_desc_flat if is_microscope else f"{test_desc_flat}, n={expected_n or 'varies'}", fontsize=14, pad=15, fontname='Arial')
                ax.set_ylabel(ylabel_input, fontsize=16, fontweight='bold', labelpad=10)
                ax.set_xticklabels([]) 
                
                trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
                for i, up_lab in enumerate(upper_labels): ax.text(i, -0.05, up_lab, ha='center', va='top', transform=trans, fontsize=16, fontweight='bold')
                
                for label, elements in [(k, list(g)) for k, g in itertools.groupby(enumerate(lower_labels), key=lambda x: x[1])]:
                    if not label: continue
                    indices = [x[0] for x in elements]
                    if indices[0] != indices[-1]: ax.plot([indices[0]-0.25, indices[-1]+0.25], [-0.16, -0.16], color='black', lw=1.5, transform=trans, clip_on=False)
                    ax.text((indices[0]+indices[-1])/2, -0.21, label, ha='center', va='top', transform=trans, fontsize=16, fontweight='bold')

                plt.subplots_adjust(bottom=0.25)
                
                # --- Excel作成 ---
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    summary_df = pd.DataFrame({
                        '条件名': [f"{u} ({l})" if l else u for u, l in zip(upper_labels, lower_labels)],
                        '上段ラベル': upper_labels, '下段ラベル': lower_labels,
                        '平均値 (Mean)': [float(np.mean(final_normalized_data[u])) for u in internal_group_ids], 
                        '標準偏差 (SD)': [float(np.std(final_normalized_data[u])) for u in internal_group_ids], 
                        '中央値 (Median)': [float(np.median(final_normalized_data[u])) for u in internal_group_ids], 
                        'n数': [int(len(final_normalized_data[u])) for u in internal_group_ids]
                    })
                    summary_df.to_excel(writer, sheet_name='Summary', index=False)
                    
                    long_data = [{"条件名": f"{upper_labels[i]} ({lower_labels[i]})" if lower_labels[i] else upper_labels[i], "正規化データ": float(val)} for i, u in enumerate(internal_group_ids) for val in final_normalized_data[u]]
                    pd.DataFrame(long_data).to_excel(writer, sheet_name='Normalized_Data', index=False) 
                    
                    stat_data = [{"比較ペア": f"{upper_labels[internal_group_ids.index(u1)]} vs {upper_labels[internal_group_ids.index(u2)]}", "p値": p, "有意差": "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns"} for u1, u2, p in p_values_to_show]
                    pd.DataFrame(stat_data).to_excel(writer, sheet_name='Statistical_Details', index=False)
                    
                    # ガイド
                    ws = writer.book['Summary'] if not is_microscope else writer.book['Normalized_Data']
                    sc = len(summary_df.columns) + 2 if not is_microscope else 4
                    if is_microscope:
                        ws.cell(row=2, column=sc, value="💡 【箱ひげ図の最短作成手順】")
                        ws.cell(row=3, column=sc, value="1. 左のA列とB列をすべて全選択します。")
                        ws.cell(row=4, column=sc, value="2. [挿入]タブ ＞ [統計グラフ] ＞ [箱ひげ図] をクリックします。")
                    else:
                        ws.cell(row=2, column=sc, value="💡 【エラーバー(SD)付き棒グラフの最短作成手順】")
                        ws.cell(row=3, column=sc, value="1. 左の『条件名』と『平均値(Mean)』の列を選択し、[挿入] ＞ [縦棒グラフ] を作成。")
                        ws.cell(row=4, column=sc, value="2. グラフの棒をクリックし、[＋] ＞ [誤差範囲] ＞ [その他の誤差範囲オプション]。")
                        ws.cell(row=5, column=sc, value="3. 『カスタム』にチェックを入れ、『値の指定』。")
                        ws.cell(row=6, column=sc, value="4. 正負両方に、左の『標準偏差(SD)』の数値をドラッグして指定すれば完成！")

                # 出力表示
                st.success("解析が完了しました！")
                st.pyplot(fig)
                
                buf_svg = io.BytesIO()
                fig.savefig(buf_svg, format='svg', bbox_inches='tight')
                
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1: st.download_button(label="📥 Excelデータをダウンロード", data=excel_buffer.getvalue(), file_name="Analysis_Data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
                with col_dl2: st.download_button(label="📥 グラフ(SVG)", data=buf_svg.getvalue(), file_name="Graph.svg", mime="image/svg+xml")

        except Exception as e:
            st.error(f"エラーが発生しました:\n{traceback.format_exc()}")
