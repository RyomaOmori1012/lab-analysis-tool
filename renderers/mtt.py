import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import japanize_matplotlib
import matplotlib.ticker as ticker
import io
import re
import warnings
import unicodedata
import json
import base64


warnings.filterwarnings('ignore')

from utils import calc_error, run_statistical_test, parse_plate, parse_idx

import platform 

# --- フォントのグローバル設定（ローカルのこだわり維持 ＋ サーバー対策） ---
plt.rcParams['font.family'] = 'sans-serif'

# 優先順位：1.Arial(英数) 2.Liberation(URL用英数) 3.MS PGothic(ローカル日) 4.IPAexGothic(URL用日)
# この順番なら、英数はArial/Liberationが、日本語はMS P/IPAが自動で選ばれます。
plt.rcParams['font.sans-serif'] = ['Arial', 'Liberation Sans', 'MS PGothic', 'IPAexGothic', 'sans-serif']

if platform.system() == 'Linux':
    # URL版(Linux)のみ：Arialがないことによる数式エラーを防ぐ最低限の設定
    plt.rcParams['mathtext.fontset'] = 'dejavusans'
else:
    # ローカル(Windows/Mac)の最高の設定をそのまま維持
    plt.rcParams['mathtext.fontset'] = 'custom'
    plt.rcParams['mathtext.rm'] = 'Arial'
    plt.rcParams['mathtext.it'] = 'Arial:italic'
    plt.rcParams['mathtext.bf'] = 'Arial:bold'

# ★ 文字列に日本語が含まれるか判定し、フォントを出し分ける関数
def get_font(text):
    return 'sans-serif'

def fix_svg_font(svg_bytes):
    svg_str = svg_bytes.getvalue().decode('utf-8')
    # 候補をすべて並べておくことで、表示環境に合わせた最適なフォントが選ばれます
    svg_str = re.sub(r'font-family:[^;"]+', 'font-family: Arial, "Liberation Sans", "MS PGothic", "IPAexGothic", sans-serif', svg_str)
    return svg_str.encode('utf-8')

# --- ★ SVGの裏側に全設定とデータを埋め込む魔法の関数 ---
def embed_state_in_svg(svg_bytes):
    try:
        svg_str = svg_bytes.decode('utf-8')
        safe_state = {}
        for k, v in st.session_state.items():
            if k == "svg_uploader": continue
            try:
                json.dumps(v)
                safe_state[k] = v
            except:
                pass
        json_str = json.dumps(safe_state)
        b64_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        metadata = f'<metadata id="app-state-data">{b64_str}</metadata>'
        svg_str = svg_str.replace('</svg>', f'\n{metadata}\n</svg>')
        return svg_str.encode('utf-8')
    except:
        return svg_bytes

def render_mtt_analysis(input_data, config):
    if config.get('svg_font_path', True):
        plt.rcParams['svg.fonttype'] = 'path'
    else:
        plt.rcParams['svg.fonttype'] = 'none'

    i_rows, i_cols = parse_idx(config['mtt_ignore_row'], True), parse_idx(config['mtt_ignore_col'], False)
    b_cols, c_cols, s_cols = parse_idx(config['mtt_blank_col'], False), parse_idx(config['mtt_control_col'], False), parse_idx(config['mtt_sample_cols'], False)
    s_cols.sort()
    valid_rows = [r for r in range(8) if r not in i_rows]
    
    safe_dilution = config['mtt_dilution'] if config['mtt_dilution'] != 0 else 1.0
    conc_vals_plot = [config['mtt_start_conc'] / (safe_dilution ** i) for i in range(len(s_cols))][::-1]
    s_cols_plot = s_cols[::-1] if "左が高濃度" in config['mtt_conc_direction'] else s_cols
    
    plates_data, plate_names, ctrl_err_pct_list = [], [], []
    exclude_flags = []
    
    raw_plates, blank_means, ctrl_means = [], [], []
    excel_exclude_logs = []
    
    for idx, item in enumerate(input_data):
        pn, pd_text = item[0], item[1]
        exclude_flag = item[2] if len(item) > 2 else False
        exclude_flags.append(exclude_flag)
        
        arr = parse_plate(pd_text); plate_names.append(pn or f"Plate {idx+1}")
        
        # ★ 外れ値マスキング
        exclude_set = config.get('mtt_exclude_map', {}).get(idx, set())
        for r_mask, c_mask in exclude_set:
            val_before = arr[r_mask, c_mask]
            arr[r_mask, c_mask] = np.nan
            excel_exclude_logs.append(f"プレート {idx+1} ({plate_names[-1]}): {chr(65+r_mask)}{c_mask+1}ウェル (除外前の値: {val_before:.4f})")
            
        raw_plates.append(arr) 
        
        blank_vals = [arr[r, c] for r in valid_rows for c in b_cols if c not in i_cols and not np.isnan(arr[r, c])]
        blank_mean = np.nanmean(blank_vals) if blank_vals else 0.0
        blank_means.append(blank_mean) 
        
        ctrl_vals = [arr[r, c] - blank_mean for r in valid_rows for c in c_cols if c not in i_cols and not np.isnan(arr[r, c])]
        ctrl_mean = np.nanmean(ctrl_vals) if len(ctrl_vals) > 0 else np.nan
        ctrl_means.append(ctrl_mean) 
        
        c_err = calc_error(ctrl_vals, config['error_bar_type'])
        ctrl_err_pct_list.append((c_err / ctrl_mean) * 100 if not np.isnan(ctrl_mean) and ctrl_mean != 0 else 0)
        
        if np.isnan(ctrl_mean) or ctrl_mean == 0: plates_data.append(np.full((8, 12), np.nan))
        else: plates_data.append((arr - blank_mean) / ctrl_mean * 100)
    
    num_p = len(plates_data)
    indiv_figs = []
    
    fw_i = config.get('fig_width', 0.0)
    fw_i = 6.0 if fw_i <= 0 else fw_i
    
    raw_colors = config.get('mtt_colors', [])
    raw_markers = config.get('mtt_markers', [])
    colors = [raw_colors[i % len(raw_colors)] if len(raw_colors) > 0 else 'black' for i in range(num_p)]
    markers = [raw_markers[i % len(raw_markers)] if len(raw_markers) > 0 else 'o' for i in range(num_p)]
    
    for i in range(num_p):
        fig_i, ax_i = plt.subplots(figsize=(fw_i, config.get('fig_height', 4.0)))
        fig_i.patch.set_facecolor('white'); ax_i.set_facecolor('white')
        
        means_i = [np.nanmean(plates_data[i][valid_rows, c]) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
        errs_i = [calc_error(plates_data[i][valid_rows, c], config['error_bar_type']) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
        
        c, m = colors[i], markers[i]
        ax_i.errorbar(conc_vals_plot, means_i, yerr=errs_i, fmt=f'-{m}', color=c, capsize=4, mfc=c, mec=c, lw=1.5)
        ax_i.set_xscale('log')
        
        mtt_max_y_i = 125.0
        for m_val, e in zip(means_i, errs_i):
            if not np.isnan(m_val) and not np.isnan(e): mtt_max_y_i = max(mtt_max_y_i, (m_val + e) * 1.15)
        ax_i.set_ylim(bottom=0, top=mtt_max_y_i)
        
        if config.get('y_tick_interval', 0) > 0:
            ax_i.yaxis.set_major_locator(ticker.MultipleLocator(config['y_tick_interval']))
        else:
            ax_i.yaxis.set_major_locator(ticker.AutoLocator())
            
        for spine in ax_i.spines.values(): spine.set_color('black'); spine.set_linewidth(1.2)
        ax_i.minorticks_off()
        
        if config['mtt_custom_xticks'].strip() and len(conc_vals_plot) > 0:
            try:
                c_ticks = [float(x.strip()) for x in config['mtt_custom_xticks'].split(',') if x.strip()]
                all_x = conc_vals_plot + c_ticks
                min_x, max_x = min(all_x), max(all_x)
                low_exp, high_exp = int(np.floor(np.log10(min_x))), int(np.ceil(np.log10(max_x)))
                combined_ticks = sorted(list(set([10**e for e in range(low_exp, high_exp + 1)] + c_ticks)))
                ax_i.set_xticks(combined_ticks)
                ax_i.get_xaxis().set_major_formatter(ticker.ScalarFormatter())
                ax_i.set_xlim(min_x * 0.8, max_x * 1.2)
            except Exception: pass
        else: ax_i.xaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: '{:g}'.format(y)))
            
        ax_i.tick_params(direction='in', length=5, width=1.2, labelsize=config.get('tick_fontsize', 12), colors='black', which='major')
        
        # ★ 日本語フォントを自動判定
        ax_i.set_ylabel(config['ylabel_input'], fontsize=config.get('label_fontsize', 14), fontweight='bold', labelpad=8, fontname=get_font(config['ylabel_input']))
        xlabel_text = f"{config['l_name']} [{config['mtt_unit']}]"
        ax_i.set_xlabel(xlabel_text, fontsize=config.get('label_fontsize', 14), fontweight='bold', labelpad=8, fontname=get_font(xlabel_text))
        
        n_indiv = max([np.count_nonzero(~np.isnan(plates_data[i][valid_rows, c])) for c in s_cols_plot]) if s_cols_plot else len(valid_rows)
        title_str = f"n={n_indiv}"
        ax_i.set_title(title_str, fontsize=config.get('title_fontsize', 14), pad=15, loc='right', fontname=get_font(title_str))
        indiv_figs.append((plate_names[i], fig_i))

    fw_c = config.get('fig_width', 0.0)
    fw_c = 7.0 if fw_c <= 0 else fw_c
    
    fig_comb, ax = plt.subplots(figsize=(fw_c, config.get('fig_height', 5.0)))
    fig_comb.patch.set_facecolor('white'); ax.set_facecolor('white')
    
    mtt_max_y_comb = 125.0
    
    for i in range(num_p):
        means = [np.nanmean(plates_data[i][valid_rows, c]) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
        errs = [calc_error(plates_data[i][valid_rows, c], config['error_bar_type']) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
        c, m = colors[i], markers[i]
        
        ax.plot(conc_vals_plot, means, f'-{m}', color=c, mfc=c, mec=c, lw=1.8, label=plate_names[i])
        ax.errorbar(conc_vals_plot, means, yerr=errs, fmt='none', color=c, capsize=4, lw=1.8)
        for m_val, e in zip(means, errs):
            if not np.isnan(m_val) and not np.isnan(e): mtt_max_y_comb = max(mtt_max_y_comb, (m_val + e) * 1.15)

    plotted_stars, mtt_test_name = set(), ""
    dropped_warnings, non_param_warnings = set(), set()
    
    for idx_c, c in enumerate(s_cols_plot):
        col_data_valid = []
        for p_idx in range(num_p):
            if exclude_flags[p_idx]: continue
            d = plates_data[p_idx][valid_rows, c]
            d_clean = d[~np.isnan(d)]
            if len(d_clean) >= 2: col_data_valid.append(d_clean)
            else: dropped_warnings.add(f"{plate_names[p_idx]} ({conc_vals_plot[idx_c]} {config['mtt_unit']})")
        
        if config['is_non_param'] and any(len(d) <= 3 for d in col_data_valid): non_param_warnings.add("MTTデータ")
        
        min_p = np.nan
        if config.get('show_stats', True) and len(col_data_valid) >= 2:
            p_anova, pairs, t_name = run_statistical_test(col_data_valid, config['var_equal'], config['is_vs_control'], config['is_non_param'], config['is_paired'])
            if t_name: mtt_test_name = t_name
            min_p = min([p_val for _, _, p_val in pairs]) if pairs else np.nan

        if not np.isnan(min_p) and min_p < 0.05:
            stars = "***" if min_p < 0.001 else "**" if min_p < 0.01 else "*"
            plotted_stars.add(stars)
            max_mean_err_c = max([np.nanmean(d) + calc_error(d, config['error_bar_type']) for d in col_data_valid if not np.isnan(np.nanmean(d)) and not np.isnan(calc_error(d, config['error_bar_type']))] + [0])
            text_y = max_mean_err_c + (mtt_max_y_comb * 0.05)
            mtt_max_y_comb = max(mtt_max_y_comb, text_y * 1.15)
            ax.text(conc_vals_plot[idx_c], text_y, stars, ha='center', va='bottom', fontsize=config.get('tick_fontsize', 14), fontweight='bold', color='black')

    if dropped_warnings: st.warning(f"⚠️ データ不足により除外: {', '.join(dropped_warnings)}")
    if non_param_warnings: st.info("💡 n≤3の場合、ノンパラメトリック検定で有意差が出ない可能性があります。")

    ax.set_xscale('log'); ax.set_ylim(bottom=0, top=mtt_max_y_comb)
    
    if config.get('y_tick_interval', 0) > 0:
        ax.yaxis.set_major_locator(ticker.MultipleLocator(config['y_tick_interval']))
    else:
        ax.yaxis.set_major_locator(ticker.AutoLocator())
        
    for spine in ax.spines.values(): spine.set_color('black'); spine.set_linewidth(1.2)
    ax.minorticks_off()
    
    if config['mtt_custom_xticks'].strip() and len(conc_vals_plot) > 0:
        try:
            c_ticks = [float(x.strip()) for x in config['mtt_custom_xticks'].split(',') if x.strip()]
            all_x = conc_vals_plot + c_ticks
            min_x, max_x = min(all_x), max(all_x)
            low_exp, high_exp = int(np.floor(np.log10(min_x))), int(np.ceil(np.log10(max_x)))
            combined_ticks = sorted(list(set([10**e for e in range(low_exp, high_exp + 1)] + c_ticks)))
            ax.set_xticks(combined_ticks)
            ax.get_xaxis().set_major_formatter(ticker.ScalarFormatter())
            ax.set_xlim(min_x * 0.8, max_x * 1.2)
        except Exception: pass
    else: ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: '{:g}'.format(y)))
        
    ax.tick_params(direction='in', length=5, width=1.2, labelsize=config.get('tick_fontsize', 12), colors='black', which='major')
    
    # ★ 日本語フォントを自動判定
    ax.set_ylabel(config['ylabel_input'], fontsize=config.get('label_fontsize', 14), fontweight='bold', labelpad=8, fontname=get_font(config['ylabel_input']))
    ax.set_xlabel(xlabel_text, fontsize=config.get('label_fontsize', 14), fontweight='bold', labelpad=8, fontname=get_font(xlabel_text))
    
    if num_p > 1: 
        leg_font = 'Arial'
        for p_name in plate_names:
            if get_font(p_name) == 'IPAexGothic':
                leg_font = 'IPAexGothic'
                break
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), frameon=False, prop={'size': config.get('legend_fontsize', 13), 'weight': 'normal', 'family': leg_font})
    
    max_n = max([np.count_nonzero(~np.isnan(plates_data[i][valid_rows, c])) for i in range(num_p) for c in s_cols_plot]) if num_p > 0 else 0
    star_str = ", " + ", ".join([f"{s} p < {0.05 if s=='*' else 0.01 if s=='**' else 0.001}" for s in ["*", "**", "***"] if s in plotted_stars]) if plotted_stars else ""
    
    if config.get('show_stats', True): title_str = f"{mtt_test_name}{star_str}, n={max_n}" if mtt_test_name and num_p > 1 else f"n={max_n}"
    else: title_str = f"n={max_n}"
    
    # ★ 日本語フォントを自動判定
    ax.set_title(title_str, fontsize=config.get('title_fontsize', 14), pad=15, loc='right', fontname=get_font(title_str))

    st.pyplot(fig_comb)
    
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        mtt_summary_dict = {"濃度 (Concentration)": [0.0] + [float(x) for x in conc_vals_plot]}
        err_label = "SEM(%)" if "SEM" in config['error_bar_type'] else "SD(%)"
        for i, p_name in enumerate(plate_names):
            mtt_summary_dict[f"{p_name}_Mean(%)"] = [100.0] + [float(np.nanmean(plates_data[i][valid_rows, c])) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
            mtt_summary_dict[f"{p_name}_{err_label}"] = [float(ctrl_err_pct_list[i])] + [float(calc_error(plates_data[i][valid_rows, c], config['error_bar_type'])) if not np.isnan(plates_data[i][valid_rows, c]).all() else np.nan for c in s_cols_plot]
        
        df_sum = pd.DataFrame(mtt_summary_dict)
        df_sum.to_excel(writer, sheet_name='Summary', index=False)
        
        ws = writer.book['Summary']
        
        # ★ Excelへ除外ログを追記
        if excel_exclude_logs:
            start_row_log = len(df_sum) + 4
            ws.cell(row=start_row_log, column=1, value="【外れ値除外記録】")
            for r_idx, log_text in enumerate(excel_exclude_logs):
                ws.cell(row=start_row_log + 1 + r_idx, column=1, value=f"※ 除外した外れ値: {log_text}")
            tips_start_row = start_row_log + len(excel_exclude_logs) + 2
        else:
            tips_start_row = 2

        ws.cell(row=tips_start_row, column=len(mtt_summary_dict) + 2, value="💡 【エラーバー付き折れ線グラフの最短作成手順】")
        ws.cell(row=tips_start_row+1, column=len(mtt_summary_dict) + 2, value="1. 『濃度』の列と、グラフにしたい『〇〇_Mean(%)』の列を同時選択し、[挿入] ＞ [散布図 (直線とマーカー)] を作成。")
        ws.cell(row=tips_start_row+2, column=len(mtt_summary_dict) + 2, value="2. 作成されたグラフの横軸をクリックして[軸の書式設定]を開き、『対数目盛を表示する』にチェック。")
        ws.cell(row=tips_start_row+3, column=len(mtt_summary_dict) + 2, value="3. グラフのプロット線をクリックし、[＋] ＞ [誤差範囲] ＞ [その他の誤差範囲オプション]。")
        ws.cell(row=tips_start_row+4, column=len(mtt_summary_dict) + 2, value="4. 『カスタム』にチェックを入れ、『値の指定』をクリック。")
        ws.cell(row=tips_start_row+5, column=len(mtt_summary_dict) + 2, value=f"5. 正負両方の選択ボックスに、対応する『〇〇_{err_label}』の数値をドラッグして指定すれば完成！")

        long_mtt_list = []
        for i, p_name in enumerate(plate_names):
            ctrl_vals = [plates_data[i][r, c] for r in valid_rows for c in c_cols if c not in i_cols]
            for val in ctrl_vals:
                if not np.isnan(val): long_mtt_list.append({"条件名": f"{p_name}_0_{config['mtt_unit']}", "正規化生存率 (%)": float(val)})
            for idx_c, c in enumerate(s_cols_plot):
                for val in plates_data[i][valid_rows, c]:
                    if not np.isnan(val): long_mtt_list.append({"条件名": f"{p_name}_{conc_vals_plot[idx_c]}_{config['mtt_unit']}", "正規化生存率 (%)": float(val)})
        pd.DataFrame(long_mtt_list).to_excel(writer, sheet_name='Normalized_Data', index=False)
        
        detailed_rows = []
        for i, p_name in enumerate(plate_names):
            arr = raw_plates[i]
            b_mean = blank_means[i]
            c_mean = ctrl_means[i]
            norm_arr = plates_data[i]
            
            for r in valid_rows:
                for c in c_cols:
                    if c not in i_cols:
                        raw_val = arr[r, c]
                        if not np.isnan(raw_val):
                            detailed_rows.append({
                                "プレート名": p_name,
                                "条件名": f"Control (0 {config['mtt_unit']})",
                                "ウェル": f"{chr(65+r)}{c+1}",
                                "生データ (吸光度等)": float(raw_val),
                                "ブランク補正値 (生データ - Blank)": float(raw_val - b_mean) if not np.isnan(raw_val) else np.nan,
                                "正規化後データ (生存率 %)": float(norm_arr[r, c])
                            })
                            
            for idx_c, c in enumerate(s_cols_plot):
                for r in valid_rows:
                    raw_val = arr[r, c]
                    if not np.isnan(raw_val):
                        detailed_rows.append({
                            "プレート名": p_name,
                            "条件名": f"{conc_vals_plot[idx_c]} {config['mtt_unit']}",
                            "ウェル": f"{chr(65+r)}{c+1}",
                            "生データ (吸光度等)": float(raw_val),
                            "ブランク補正値 (生データ - Blank)": float(raw_val - b_mean) if not np.isnan(raw_val) else np.nan,
                            "正規化後データ (生存率 %)": float(norm_arr[r, c])
                        })
        if detailed_rows:
            pd.DataFrame(detailed_rows).to_excel(writer, sheet_name='Detailed_Data', index=False)
        
        for i in range(num_p):
            df_norm = pd.DataFrame(plates_data[i])
            df_norm.index = ['A','B','C','D','E','F','G','H']
            df_norm.columns = [str(x+1) for x in range(12)]
            df_norm.to_excel(writer, sheet_name=re.sub(r'[\\/*?:\[\]]', '', f"Plate_{i+1}_{plate_names[i]}")[:31])

    st.download_button("📥 Excelデータをダウンロード (全データ・統計詳細シート同梱)", excel_buffer.getvalue(), "Analysis_Data.xlsx", type="primary", use_container_width=True)
    
    dl_col1, dl_col2 = st.columns(2)
    buf_c = io.BytesIO()
    fig_comb.savefig(buf_c, format='svg', bbox_inches='tight')
    fixed_svg_c = fix_svg_font(buf_c)
    final_svg_c = embed_state_in_svg(fixed_svg_c)
    
    with dl_col1: st.download_button("📥 統合グラフ(SVG)を保存", final_svg_c, "Combined_Graph.svg", "image/svg+xml", use_container_width=True)
        
    with st.expander("個別プレートのグラフ(SVG)をダウンロード"):
        for p_name, f in indiv_figs:
            buf_i = io.BytesIO()
            f.savefig(buf_i, format='svg', bbox_inches='tight')
            fixed_svg_i = fix_svg_font(buf_i)
            final_svg_i = embed_state_in_svg(fixed_svg_i)
            st.download_button(f"📥 {p_name} のグラフ", final_svg_i, f"{p_name}_Graph.svg", "image/svg+xml")