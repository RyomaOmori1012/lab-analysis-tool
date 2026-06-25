import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
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

# --- フォントのグローバル設定 ---
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'MS PGothic', 'Liberation Sans', 'IPAexGothic', 'sans-serif']
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['mathtext.fontset'] = 'custom'
plt.rcParams['mathtext.rm'] = 'Arial'
plt.rcParams['mathtext.it'] = 'Arial:italic'
plt.rcParams['mathtext.bf'] = 'Arial:bold'

# ★ 文字列に日本語が含まれるか判定し、フォントを出し分ける関数
def get_font(text):
    return 'sans-serif'

def fix_svg_font(svg_bytes):
    svg_str = svg_bytes.getvalue().decode('utf-8')
    # ブラウザやパワポで開いた際も、Arialがあればそれを、なければ代用を、と順番に探させる設定です。
    svg_str = re.sub(r'font-family:[^;"]+', 'font-family: Arial, "MS PGothic", "Liberation Sans", "IPAexGothic", sans-serif', svg_str)
    return svg_str.encode('utf-8')

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

def render_mtt_bar(input_data, config):
    if config.get('svg_font_path', True):
        plt.rcParams['svg.fonttype'] = 'path'
    else:
        plt.rcParams['svg.fonttype'] = 'none'

    i_rows = parse_idx(config['mtt_ignore_row'], True)
    i_cols = parse_idx(config['mtt_ignore_col'], False)
    b_cols = parse_idx(config['mtt_blank_col'], False)
    c_cols = parse_idx(config['mtt_control_col'], False)  
    m_cols = parse_idx(config['mtt_mock_col'], False)     
    
    valid_rows = [r for r in range(8) if r not in i_rows]
    
    detailed_rows = []
    indiv_results = []
    excel_exclude_logs = []
    
    for idx, item in enumerate(input_data):
        pn = item[0]
        pd_text = item[1]
        exclude_flag = item[2] if len(item) > 2 else False
        mock_lbl = item[3] if len(item) > 3 else "Mock"
        cond_lbl = item[4] if len(item) > 4 else (pn if pn else f"Plate {idx+1}")
        
        arr = parse_plate(pd_text)
        
        # ★ 外れ値マスキング
        exclude_set = config.get('mtt_exclude_map', {}).get(idx, set())
        for r_mask, c_mask in exclude_set:
            val_before = arr[r_mask, c_mask]
            arr[r_mask, c_mask] = np.nan
            excel_exclude_logs.append(f"プレート {idx+1} ({cond_lbl}): {chr(65+r_mask)}{c_mask+1}ウェル (除外前の値: {val_before:.4f})")
        
        blank_vals = [arr[r, c] for r in valid_rows for c in b_cols if c not in i_cols and not np.isnan(arr[r, c])]
        blank_mean = np.nanmean(blank_vals) if blank_vals else 0.0
        
        mock_raw = [arr[r, c] - blank_mean for r in valid_rows for c in m_cols if c not in i_cols and not np.isnan(arr[r, c])]
        mock_mean = np.nanmean(mock_raw) if mock_raw else np.nan
        
        cond_raw = [arr[r, c] - blank_mean for r in valid_rows for c in c_cols if c not in i_cols and not np.isnan(arr[r, c])]
        
        mock_norm = []
        cond_norm = []
        
        if not np.isnan(mock_mean) and mock_mean != 0:
            mock_norm = [(v / mock_mean) * 100 for v in mock_raw]
            cond_norm = [(v / mock_mean) * 100 for v in cond_raw]
        
        for r in valid_rows:
            for col in m_cols:
                if col not in i_cols and not np.isnan(arr[r, col]):
                    raw_val = arr[r, col]
                    val_sub = raw_val - blank_mean
                    norm_val = (val_sub / mock_mean) * 100 if not np.isnan(mock_mean) and mock_mean != 0 else np.nan
                    detailed_rows.append({
                        "プレート名": pn,
                        "条件名": mock_lbl,
                        "ウェル": f"{chr(65+r)}{col+1}",
                        "生データ (吸光度)": float(raw_val),
                        "ブランク補正後": float(val_sub),
                        "プレート内Mock平均": float(mock_mean),
                        "規格化後データ (%)": float(norm_val) if not np.isnan(norm_val) else np.nan
                    })
            for col in c_cols:
                if col not in i_cols and not np.isnan(arr[r, col]):
                    raw_val = arr[r, col]
                    val_sub = raw_val - blank_mean
                    norm_val = (val_sub / mock_mean) * 100 if not np.isnan(mock_mean) and mock_mean != 0 else np.nan
                    detailed_rows.append({
                        "プレート名": pn,
                        "条件名": cond_lbl,
                        "ウェル": f"{chr(65+r)}{col+1}",
                        "生データ (吸光度)": float(raw_val),
                        "ブランク補正後": float(val_sub),
                        "プレート内Mock平均": float(mock_mean),
                        "規格化後データ (%)": float(norm_val) if not np.isnan(norm_val) else np.nan
                    })
                    
        indiv_results.append({
            "plate_name": pn,
            "mock_lbl": mock_lbl,
            "cond_lbl": cond_lbl,
            "mock_norm": mock_norm,
            "cond_norm": cond_norm,
            "exclude": exclude_flag
        })

    def get_colors(num_bars, mode):
        if mode == "すべて黒":
            return ['black'] * num_bars  
        else:
            import matplotlib.cm as cm
            return [cm.Greys(v) for v in np.linspace(1.0, 0.3, num_bars)]

    def draw_custom_bar_chart(data_lists, labels, x_coords, colors, title_prefix, test_pairs_to_run, bw):
        valid_data_for_stat = []
        for d in data_lists:
            clean = [v for v in d if not np.isnan(v)]
            valid_data_for_stat.append(clean)
            
        p_pairs = []
        test_desc = ""
        if config.get('show_stats', True):
            for idx_m, idx_c in test_pairs_to_run:
                d_m = valid_data_for_stat[idx_m]
                d_c = valid_data_for_stat[idx_c]
                if len(d_m) >= 2 and len(d_c) >= 2:
                    _, pairs, t_name = run_statistical_test([d_m, d_c], config.get('var_equal', False), is_vs_control=False, is_non_param=config.get('is_non_param', False), is_paired=config.get('is_paired', False))
                    if pairs:
                        p_pairs.append((idx_m, idx_c, pairs[0][2]))
                    test_desc = t_name

        fig_w = config.get('fig_width', 0)
        if fig_w == 0:
            fig_w = max(4.0, (max(x_coords) - min(x_coords) + bw * 2) * 1.5) if len(x_coords) > 0 else 4.0
        fig_h = config.get('fig_height', 5.0)
        
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')
        
        means = [np.nanmean(d) if len(d)>0 else 0 for d in valid_data_for_stat]
        errs = [calc_error(d, config['error_bar_type']) if len(d)>0 else 0 for d in valid_data_for_stat]
        
        for i in range(len(labels)):
            ax.bar(x_coords[i], means[i], yerr=errs[i], width=bw, color=colors[i], edgecolor='black', capsize=4, error_kw=dict(ecolor='black', lw=1.2))
            
        for spine in ax.spines.values(): spine.set_color('black'); spine.set_linewidth(1.5)
        ax.tick_params(axis='y', colors='black', direction='in', length=5, width=1.5, labelsize=config.get('tick_fontsize', 14))
        
        rot = 0
        if len(x_coords) > 1:
            x_span = max(x_coords) - min(x_coords) + bw * 2.0
            inches_per_x = fig_w / x_span if x_span > 0 else 1.0
            
            fontsize = config.get('x_label_fontsize', 14)
            char_width_inches = fontsize / 72.0
            
            def get_text_width(text):
                w = 0
                for c in str(text):
                    if unicodedata.east_asian_width(c) in 'FWA': w += 2
                    else: w += 1
                return w / 2.0
            
            overlap_detected = False
            for i in range(len(labels) - 1):
                dx_inches = (x_coords[i+1] - x_coords[i]) * inches_per_x
                len1 = get_text_width(labels[i])
                len2 = get_text_width(labels[i+1])
                avg_len = (len1 + len2) / 2.0
                
                space_needed = avg_len * char_width_inches * 1.2
                if dx_inches - space_needed < char_width_inches:
                    overlap_detected = True
                    break
                    
            if overlap_detected:
                rot = 45
        
        ax.set_xticks(x_coords)
        
        # ★ 日本語フォントを自動判定
        xtick_font = 'Arial'
        for lbl in labels:
            if get_font(lbl) == 'IPAexGothic':
                xtick_font = 'IPAexGothic'
                break
                
        if rot != 0:
            ax.set_xticklabels(labels, fontsize=config.get('x_label_fontsize', 14), fontweight='bold', color='black', rotation=rot, ha='center', fontname=xtick_font)
            ax.tick_params(axis='x', bottom=False, pad=5)
        else:
            ax.set_xticklabels(labels, fontsize=config.get('x_label_fontsize', 14), fontweight='bold', color='black', ha='center', fontname=xtick_font)
            ax.tick_params(axis='x', bottom=False)
            
        ax.set_ylabel("Cell Viability [%]", fontsize=config.get('label_fontsize', 16), fontweight='bold', labelpad=8, fontname='Arial')
        
        current_max_y = max([m + e for m, e in zip(means, errs) if not np.isnan(m) and not np.isnan(e)] + [100.0]) if means else 100.0
        y_shift = current_max_y * 0.15
        h = current_max_y * 0.025
        base_bracket_y = current_max_y * 1.10
        max_element_y = current_max_y
        
        levels, max_level = [], 0
        plotted_stars = set()
        
        sig_pairs = []
        for i_idx, j_idx, p in p_pairs:
            if p < 0.05:
                stars = "***" if p < 0.001 else "**" if p < 0.01 else "*"
                sig_pairs.append((x_coords[i_idx], x_coords[j_idx], stars))
                
        for x_start, x_end, stars in sorted(sig_pairs, key=lambda x: x[1] - x[0]):
            plotted_stars.add(stars)
            placed_level = next((l_idx for l_idx, intervals in enumerate(levels) if not any(not (x_end < s or x_start > e) for s, e in intervals)), -1)
            if placed_level == -1: placed_level = len(levels); levels.append([])
            levels[placed_level].append((x_start, x_end)); max_level = max(max_level, placed_level)
            by = base_bracket_y + placed_level * y_shift; max_element_y = max(max_element_y, by + h)
            ax.plot([x_start, x_start, x_end, x_end], [by - h, by, by, by - h], color='black', lw=1.2)
            ax.text((x_start + x_end) / 2, by + h*0.2, stars, ha='center', va='bottom', color='black', fontsize=config.get('tick_fontsize', 14), fontweight='bold', fontname='Arial')
            
        ax.set_ylim(0, max(current_max_y * 1.2, max_element_y * 1.15))
        
        max_n = max([len(d) for d in valid_data_for_stat]) if valid_data_for_stat else 0
        star_str = ", " + ", ".join([f"{s} p < {0.05 if s=='*' else 0.01 if s=='**' else 0.001}" for s in ["*", "**", "***"] if s in plotted_stars]) if plotted_stars else ""
        title_str = f"{test_desc}{star_str}, n={max_n}" if test_desc else f"n={max_n}"
        if not config.get('show_stats', True): title_str = f"n={max_n}"
        
        # ★ 日本語フォントを自動判定
        ax.set_title(title_str, fontsize=config.get('title_fontsize', 14), pad=15, loc='right', fontname=get_font(title_str))
        
        return fig, p_pairs, test_desc

    # --- 1. 統合グラフのデータ構築（横並びレイアウト） ---
    int_x_coords = []
    int_labels = []
    int_data_lists = []
    int_test_pairs = []
    current_x = 0.0
    
    bw = config.get('mtt_bar_width', 0.4)
    bg = config.get('mtt_bar_gap', 0.05)
    gg = config.get('mtt_group_gap', 0.6)
    
    for i, res in enumerate(indiv_results):
        if res['exclude']: continue
        
        idx_mock = len(int_data_lists)
        int_x_coords.append(current_x)
        int_labels.append(res['mock_lbl'])
        int_data_lists.append(res['mock_norm'])
        
        idx_cond = len(int_data_lists)
        x_cond = current_x + bw + bg
        int_x_coords.append(x_cond)
        int_labels.append(res['cond_lbl'])
        int_data_lists.append(res['cond_norm'])
        
        int_test_pairs.append((idx_mock, idx_cond))
        
        current_x = x_cond + bw + gg

    st.markdown("### 📊 トランスフェクション毒性 (統合グラフ)")
    fig_int = None
    p_pairs_int = []
    if int_data_lists:
        colors_int = []
        for _ in int_test_pairs:
            colors_int.extend(get_colors(2, config.get('mtt_bar_color', 'グラデーション (黒→灰)')))
            
        fig_int, p_pairs_int, t_name_int = draw_custom_bar_chart(int_data_lists, int_labels, int_x_coords, colors_int, "統合", int_test_pairs, bw)
        st.pyplot(fig_int)
    
    # --- 2. 個別グラフの描画 ---
    st.markdown("### 📊 トランスフェクション毒性 (個別プレート)")
    cols = st.columns(len(indiv_results) if len(indiv_results) > 0 else 1)
    
    indiv_figs = []
    stat_data = []
    
    for i_idx, j_idx, p in p_pairs_int:
        c1 = int_labels[i_idx]
        c2 = int_labels[j_idx]
        # ▼ 2箇所目：stat_data.append の中身をごっそり入れ替える
        stat_data.append({
            "グラフ": "統合グラフ", 
            "比較": f"{c1} vs {c2}", 
            "p値": p, 
            "判定": "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns",
            "検定手法": t_name_int,
            "検定の前提": "ノンパラメトリック" if config.get('is_non_param') else "パラメトリック",
            "対応の有無": "対応あり" if config.get('is_paired') else "対応なし",
            "エラーバー": config.get('error_bar_type', '設定なし')
        })
        
    for i, res in enumerate(indiv_results):
        if res['exclude']: continue
        x_indiv = [0, bw + bg]
        lbls = [res['mock_lbl'], res['cond_lbl']]
        dlists = [res['mock_norm'], res['cond_norm']]
        cols_c = get_colors(2, config.get('mtt_bar_color', 'グラデーション (黒→灰)'))
        
        f_indiv, p_pairs_indiv, t_name_indiv = draw_custom_bar_chart(dlists, lbls, x_indiv, cols_c, f"Plate {i+1}", [(0, 1)], bw)
        with cols[i % len(cols)]:
            st.pyplot(f_indiv)
            indiv_figs.append((res['plate_name'], f_indiv))
            
        for i_idx, j_idx, p in p_pairs_indiv:
            c1 = lbls[i_idx]
            c2 = lbls[j_idx]
            # ▼ 2箇所目：stat_data.append の中身をごっそり入れ替える
            stat_data.append({
                "グラフ": f"個別 ({res['plate_name']})", 
                "比較": f"{c1} vs {c2}", 
                "p値": p, 
                "判定": "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns",
                "検定手法": t_name_indiv,
                "検定の前提": "ノンパラメトリック" if config.get('is_non_param') else "パラメトリック",
                "対応の有無": "対応あり" if config.get('is_paired') else "対応なし",
                "エラーバー": config.get('error_bar_type', '設定なし')
            })

    # --- Excel 書き出し ---
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        
        err_label = "SEM" if "SEM" in config['error_bar_type'] else "SD"
        summary_int = []
        for j, d in enumerate(int_data_lists):
            clean = [v for v in d if not np.isnan(v)]
            summary_int.append({
                "条件名": int_labels[j],
                "平均 (%)": np.nanmean(clean) if clean else np.nan,
                f"{err_label} (%)": calc_error(clean, config['error_bar_type']) if clean else np.nan
            })
        df_sum = pd.DataFrame(summary_int)
        df_sum.to_excel(writer, sheet_name='Summary', index=False)
        
        # ★ Excelへ除外ログを追記
        if excel_exclude_logs:
            ws = writer.book['Summary']
            start_row_log = len(df_sum) + 5
            ws.cell(row=start_row_log, column=1, value="【外れ値除外記録】")
            for r_idx, log_text in enumerate(excel_exclude_logs):
                ws.cell(row=start_row_log + 1 + r_idx, column=1, value=f"※ 除外した外れ値: {log_text}")
        
        if stat_data:
            pd.DataFrame(stat_data).to_excel(writer, sheet_name='Statistical_Details', index=False)
            
        if detailed_rows:
            pd.DataFrame(detailed_rows).to_excel(writer, sheet_name='Detailed_Data', index=False)

    st.download_button("📥 トランスフェクション毒性のExcelデータをダウンロード", excel_buffer.getvalue(), "Transfection_Toxicity_Data.xlsx", type="primary", use_container_width=True)
    
    if fig_int is not None:
        dl_col1, dl_col2 = st.columns(2)
        buf_c = io.BytesIO()
        fig_int.savefig(buf_c, format='svg', bbox_inches='tight')
        fixed_svg_c = fix_svg_font(buf_c)
        final_svg_c = embed_state_in_svg(fixed_svg_c)
        with dl_col1: st.download_button("📥 統合棒グラフ(SVG)を保存", final_svg_c, "Transfection_Integrated_Bar.svg", "image/svg+xml", use_container_width=True)
            
    with st.expander("個別プレートの棒グラフ(SVG)をダウンロード"):
        for p_name, f in indiv_figs:
            buf_i = io.BytesIO()
            f.savefig(buf_i, format='svg', bbox_inches='tight')
            fixed_svg_i = fix_svg_font(buf_i)
            final_svg_i = embed_state_in_svg(fixed_svg_i)
            st.download_button(f"📥 {p_name} の棒グラフ", final_svg_i, f"{p_name}_Transfection_Bar.svg", "image/svg+xml")