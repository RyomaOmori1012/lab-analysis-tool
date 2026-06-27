import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.transforms as transforms
import matplotlib.ticker as ticker
import itertools
import io
import warnings
import unicodedata

warnings.filterwarnings('ignore')

from utils import calc_error, run_statistical_test, parse_text
from plot_utils import get_font, fix_svg_font, embed_state_in_svg, draw_significance_brackets

def calc_rotation(labels, xs, font_size, fig_width, x_span):
    if len(xs) < 2 or not labels or len(xs) != len(labels): return 0
    pairs = sorted(zip(xs, labels), key=lambda item: item[0])
    
    def get_text_width(text):
        w = 0
        for c in str(text):
            w += 1.0 if unicodedata.east_asian_width(c) in 'FWA' else 0.55
        return w
        
    char_width_inch = font_size / 72.0
    axes_width_inch = fig_width * 0.8
    
    for i in range(len(pairs) - 1):
        x1, lbl1 = pairs[i]
        x2, lbl2 = pairs[i+1]
        if x2 - x1 <= 1e-5: continue
        dx_inch = ((x2 - x1) / x_span) * axes_width_inch
        w1_inch = get_text_width(lbl1) * char_width_inch
        w2_inch = get_text_width(lbl2) * char_width_inch
        occupied_inch = (w1_inch / 2.0) + (w2_inch / 2.0)
        space_inch = dx_inch - occupied_inch
        if space_inch < (char_width_inch * 0.5):
            return 45
    return 0

def render_single_target(input_data, config):
    if config.get('svg_font_path', True): plt.rcParams['svg.fonttype'] = 'path'
    else: plt.rcParams['svg.fonttype'] = 'none'

    upper_labels, lower_labels, internal_ids, raw_processed = [], [], [], {}
    dropped_warnings, non_param_warnings, exclude_flags = set(), set(), []
    raw_target_data, raw_loading_data = {}, {}
    
    for idx, item in enumerate(input_data):
        u, d, val_t_list, val_l_list = item[0], item[1], item[2], item[3] if len(item) > 3 else []
        exclude_flag = item[4] if len(item) > 4 else False
        exclude_flags.append(exclude_flag)
        
        t_nums, l_nums = parse_text(val_t_list[0]), parse_text(val_l_list[0])
        raw_target_data[f"C_{idx}"] = list(t_nums)
        raw_loading_data[f"C_{idx}"] = list(l_nums)
        
        length = max(len(t_nums), len(l_nums))
        t_nums.extend([np.nan] * (length - len(t_nums)))
        l_nums.extend([np.nan] * (length - len(l_nums)))
        
        processed = []
        for t, l in zip(t_nums, l_nums):
            if np.isnan(t) or np.isnan(l): processed.append(np.nan)
            elif config['is_qpcr']: processed.append(t - l)
            else: processed.append(np.nan if l == 0 else t / l)
        raw_processed[f"C_{idx}"] = processed
        
        upper_labels.append(u or f"U_{idx+1}")
        lower_labels.append(d or "")
        internal_ids.append(f"C_{idx}")
    
    if not any(len([v for v in raw_processed[uid] if not np.isnan(v)]) > 0 for uid in internal_ids): st.stop()
        
    final_norm = {}
    ctrl_id = internal_ids[0]
    for i, uid in enumerate(internal_ids):
        c_id = internal_ids[lower_labels.index(lower_labels[i])] if 'グループ' in config['norm_mode'] else ctrl_id
        c_mean = np.nanmean(raw_processed[c_id])
        if np.isnan(c_mean) or c_mean == 0: c_mean = 1.0 
        
        if config['is_qpcr']: final_norm[uid] = [2 ** -(v - c_mean) for v in raw_processed[uid]]
        else: final_norm[uid] = [v / c_mean for v in raw_processed[uid]]
    
    p_pairs, test_desc_flat = [], ""
    groupings = [[u for u in internal_ids if lower_labels[internal_ids.index(u)] == low] for low in sorted(list(set(lower_labels)), key=lambda x: lower_labels.index(x))] if config['is_grouped_test'] else [internal_ids]

    for grp in groupings:
        valid_uids, valid_data = [], []
        for u in grp:
            if exclude_flags[internal_ids.index(u)]: continue
            non_nan_data = [v for v in raw_processed[u] if not np.isnan(v)]
            if len(non_nan_data) >= 2:
                valid_uids.append(u); valid_data.append(non_nan_data)
            else:
                uid_idx = internal_ids.index(u)
                dropped_warnings.add(f"{upper_labels[uid_idx]} ({lower_labels[uid_idx]})" if lower_labels[uid_idx] else upper_labels[uid_idx])
        
        if len(valid_data) < 2: continue
        if config['is_non_param'] and any(len(d) <= 3 for d in valid_data): non_param_warnings.add("解析データ")
        
        if config.get('show_stats', True):
            _, pairs, t_name = run_statistical_test(valid_data, config['var_equal'], config['is_vs_control'], config['is_non_param'], config['is_paired'])
            if t_name: test_desc_flat = t_name
            for i_idx, j_idx, p_val in pairs: p_pairs.append((valid_uids[i_idx], valid_uids[j_idx], p_val))

    if dropped_warnings: st.warning(f"⚠️ データ不足により除外: {', '.join(dropped_warnings)}")
    if non_param_warnings: st.info("💡 n≤3の場合、ノンパラメトリック検定で有意差が出ない可能性があります。")

    unique_low = sorted(list(set(lower_labels)), key=lambda x: lower_labels.index(x))
    unique_up = sorted(list(set(upper_labels)), key=lambda x: upper_labels.index(x))
    
    if config['color_mode'] == "色分け":
        cmap = plt.get_cmap('Greys_r')
        if len(unique_up) == 1: colors = [cmap(0.2)]
        else: colors = [cmap(i) for i in np.linspace(0.1, 0.6, len(unique_up))]
        palette = {u: colors[i] for i, u in enumerate(unique_up)}
    else:
        palette = {u: "black" for u in unique_up}
    
    x_coords, bar_width = {}, config['bar_width']
    bar_gap, group_gap = config.get('bar_gap', 0.02), config.get('group_gap', 0.50)
    
    if config['layout_mode'] == "条件ごとにグループ化":
        current_x = 0
        for low in unique_low:
            members = [i for i, l in enumerate(lower_labels) if l == low]
            for idx_m, i in enumerate(members):
                x_coords[internal_ids[i]] = current_x
                if idx_m < len(members) - 1: current_x += bar_width + bar_gap
                else: current_x += bar_width + group_gap
    else:
        current_x = 0
        for i, uid in enumerate(internal_ids): 
            x_coords[uid] = current_x
            current_x += bar_width + bar_gap

    x_vals = list(x_coords.values())
    if x_vals:
        max_gap = bar_gap if bar_gap > 0.6 else 0.6
        x_min_val = min(x_vals) - max_gap
        x_max_val = max(x_vals) + max_gap
        x_span = x_max_val - x_min_val
    else:
        x_span = 1.0

    fw = max(4.0, len(internal_ids) * 0.8 + x_span * 1.0) if config.get('fig_width', 0.0) <= 0 else config['fig_width']
    fig_h = config.get('fig_height', 5.0)
    fig, ax = plt.subplots(figsize=(fw, fig_h))
    fig.patch.set_facecolor('white'); ax.set_facecolor('white')

    for i, uid in enumerate(internal_ids):
        mean_val, err_val = np.nanmean(final_norm[uid]), calc_error(final_norm[uid], config['error_bar_type'])
        label_name = upper_labels[i] if i == upper_labels.index(upper_labels[i]) else ""
        ax.bar(x_coords[uid], mean_val if not np.isnan(mean_val) else 0, yerr=err_val if not np.isnan(err_val) else 0, 
               width=bar_width, color=palette[upper_labels[i]], edgecolor='black', capsize=3, error_kw=dict(ecolor='black', lw=1.2), label=label_name)

    for spine in ax.spines.values(): spine.set_visible(True); spine.set_color('black'); spine.set_linewidth(1.5)
    
    base_fs = config.get('tick_fontsize', 14)
    x_lbl_fs = config.get('x_label_fontsize', 14)
    x_fs_ratio = (x_lbl_fs / 14.0) * (5.0 / fig_h)
    
    ax.tick_params(axis='y', colors='black', direction='in', left=True, right=False, length=5, width=1.5, labelsize=base_fs)
    ax.tick_params(axis='x', bottom=False, top=False); ax.set_xticklabels([]) 
    trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
    
    offset_up_user, offset_low_user = config.get('offset_up', 0.0), config.get('offset_low', 0.0)

    if config['label_style'] == "1段 ＋ 系列名（凡例）":
        xs_low, lbls_low = [], []
        for low in unique_low:
            xs_t = [x_coords[internal_ids[i]] for i, l in enumerate(lower_labels) if l == low]
            if xs_t: xs_low.append(sum(xs_t)/len(xs_t)); lbls_low.append(low)
        rot = calc_rotation(lbls_low, xs_low, x_lbl_fs, fw, x_span)
        
        y_pos_base = -0.015 * x_fs_ratio
        va_val, extra_margin = 'top', 0
        if rot > 0:
            max_len = max([len(str(l)) for l in unique_low if l]) if unique_low else 0
            extra_margin = max_len * 0.013 * x_fs_ratio
            y_pos_base = -0.015 * x_fs_ratio - extra_margin
            va_val = 'center'
            
        y_pos = y_pos_base - offset_low_user
        for low in unique_low:
            xs = [x_coords[internal_ids[i]] for i, l in enumerate(lower_labels) if l == low]
            if xs: ax.text(sum(xs) / len(xs), y_pos, low, ha='center', va=va_val, rotation=rot, transform=trans, fontsize=x_lbl_fs, fontweight='bold', color='black', fontname=get_font(low))
    else:
        xs_up = [x_coords[uid] for uid in internal_ids]
        rot_up = calc_rotation(upper_labels, xs_up, x_lbl_fs, fw, x_span)
        
        y_up_base = -0.015 * x_fs_ratio
        va_up, extra_margin_up = 'top', 0
        if rot_up > 0:
            max_up_len = max([len(str(u)) for u in upper_labels if u]) if upper_labels else 0
            extra_margin_up = max_up_len * 0.013 * x_fs_ratio
            y_up_base = -0.015 * x_fs_ratio - extra_margin_up
            va_up = 'center'
            
        y_up = y_up_base - offset_up_user
        y_line_base = y_up_base - 0.075 * x_fs_ratio if rot_up == 0 else y_up_base - extra_margin_up - 0.015 * x_fs_ratio
        
        for i, uid in enumerate(internal_ids):
            ax.text(x_coords[uid], y_up, upper_labels[i], ha='center', va=va_up, rotation=rot_up, transform=trans, fontsize=x_lbl_fs, color='black', fontweight='bold', fontname=get_font(upper_labels[i]))
            
        xs_low_center, low_labels_clean = [], []
        for label, elements in [(k, list(g)) for k, g in itertools.groupby(enumerate(lower_labels), key=lambda x: x[1])]:
            if not label: continue
            xs = [x_coords[internal_ids[x[0]]] for x in elements]
            xs_low_center.append((min(xs) + max(xs)) / 2)
            low_labels_clean.append(label)
            
        rot_low = calc_rotation(low_labels_clean, xs_low_center, x_lbl_fs, fw, x_span)
        y_low_base, va_low, extra_margin_low = y_line_base - 0.015 * x_fs_ratio, 'top', 0
        
        if rot_low > 0:
            max_low_len = max([len(str(l)) for l in lower_labels if l]) if lower_labels else 0
            extra_margin_low = max_low_len * 0.013 * x_fs_ratio
            y_low_base = y_line_base - 0.015 * x_fs_ratio - extra_margin_low
            va_low = 'center'
            
        y_line, y_low = y_line_base - offset_low_user, y_low_base - offset_low_user
        
        for label, elements in [(k, list(g)) for k, g in itertools.groupby(enumerate(lower_labels), key=lambda x: x[1])]:
            if not label: continue
            xs = [x_coords[internal_ids[x[0]]] for x in elements]
            x_start, x_end = min(xs), max(xs)
            if x_start != x_end: ax.plot([x_start - bar_width/2.5, x_end + bar_width/2.5], [y_line, y_line], color='black', lw=1.2, transform=trans, clip_on=False)
            ax.text((x_start + x_end) / 2, y_low, label, ha='center', va=va_low, rotation=rot_low, transform=trans, fontsize=x_lbl_fs, fontweight='bold', color='black', fontname=get_font(label))

    all_vals = [v for vals in final_norm.values() for v in vals if not np.isnan(v)]
    current_max_y = max(all_vals + [0]) if all_vals else 1.0
    for uid in internal_ids:
        m, e = np.nanmean(final_norm[uid]), calc_error(final_norm[uid], config['error_bar_type'])
        if not np.isnan(m) and not np.isnan(e): current_max_y = max(current_max_y, m + e)
    if current_max_y == 0: current_max_y = 1.0
    
    sig_pairs = []
    for u1, u2, p in p_pairs:
        if p >= 0.05 or np.isnan(p) or u1 not in x_coords or u2 not in x_coords: continue
        sig_pairs.append((min(x_coords[u1], x_coords[u2]), max(x_coords[u1], x_coords[u2]), "***" if p < 0.001 else "**" if p < 0.01 else "*"))
    
    max_element_y, plotted_stars = draw_significance_brackets(ax, sig_pairs, current_max_y, base_fs)

    ax.set_ylim(0, max(current_max_y * 1.2, max_element_y * 1.15))
    if config.get('y_tick_interval', 0) > 0: ax.yaxis.set_major_locator(ticker.MultipleLocator(config['y_tick_interval']))
    else: ax.yaxis.set_major_locator(ticker.AutoLocator())
    if x_vals: ax.set_xlim(x_min_val, x_max_val)
        
    ax.set_ylabel(config['ylabel_input'], fontsize=config.get('label_fontsize', 16), fontweight="bold", color='black', labelpad=10, fontname=get_font(config['ylabel_input']))
    
    if config['label_style'] == "1段 ＋ 系列名（凡例）":
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        if by_label: 
            import platform
            leg_font = 'Liberation Sans' if platform.system() == 'Linux' else 'Arial'
            for lbl in by_label.keys():
                f_name = get_font(lbl)
                if f_name in ['IPAexGothic', 'MS PGothic', 'Hiragino Sans']: leg_font = f_name; break
            ax.legend(by_label.values(), by_label.keys(), loc='upper left', bbox_to_anchor=(1.02, 1.0), frameon=False, prop={'size': config.get('legend_fontsize', 12), 'weight': 'bold', 'family': leg_font})

    n_list = [len([v for v in raw_processed[u] if not np.isnan(v)]) for u in internal_ids]
    expected_n = n_list[0] if n_list and len(set(n_list)) == 1 else "varies"
    star_str = ", " + ", ".join([f"{s} p < {0.05 if s=='*' else 0.01 if s=='**' else 0.001}" for s in ["*", "**", "***"] if s in plotted_stars]) if plotted_stars else ""
    title_str = f"{test_desc_flat}{star_str}, n={expected_n}" if test_desc_flat else f"n={expected_n}"
    
    if not config.get('show_stats', True): title_str = f"n={expected_n}"
    if title_str: ax.set_title(title_str, fontsize=config.get('title_fontsize', 14), pad=8, loc='right', fontname=get_font(title_str))

    st.pyplot(fig)
    
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        err_label = "SEM" if "SEM" in config['error_bar_type'] else "SD"
        
        summary_df = pd.DataFrame({'上段ラベル': upper_labels, '下段ラベル': lower_labels, '平均': [np.nanmean(final_norm[u]) for u in internal_ids], err_label: [calc_error(final_norm[u], config['error_bar_type']) for u in internal_ids]})
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        detailed_rows = []
        for i, uid in enumerate(internal_ids):
            c_title = f"{upper_labels[i]} ({lower_labels[i]})" if lower_labels[i] else upper_labels[i]
            t_list, l_list, proc_list, norm_list = raw_target_data.get(uid, []), raw_loading_data.get(uid, []), raw_processed.get(uid, []), final_norm.get(uid, [])
            
            for r_idx in range(max(len(t_list), len(l_list), len(proc_list), len(norm_list))):
                row_dict = {"条件名": c_title}
                row_dict["生データ (Target)"] = t_list[r_idx] if r_idx < len(t_list) else np.nan
                row_dict["生データ (Loading Control)"] = l_list[r_idx] if r_idx < len(l_list) else np.nan
                row_dict["計算過程 (Target - Loading)" if config['is_qpcr'] else "計算過程 (Target / Loading)"] = proc_list[r_idx] if r_idx < len(proc_list) else np.nan
                row_dict["正規化後データ"] = norm_list[r_idx] if r_idx < len(norm_list) else np.nan
                detailed_rows.append(row_dict)
        pd.DataFrame(detailed_rows).to_excel(writer, sheet_name='Detailed_Data', index=False)
        
        stat_data = []
        for u1, u2, p in p_pairs:
            idx1, idx2 = internal_ids.index(u1), internal_ids.index(u2)
            c1 = f"{upper_labels[idx1]} ({lower_labels[idx1]})" if lower_labels[idx1] else upper_labels[idx1]
            c2 = f"{upper_labels[idx2]} ({lower_labels[idx2]})" if lower_labels[idx2] else upper_labels[idx2]
            stat_data.append({
                "比較": f"{c1} vs {c2}", "p値": p if not np.isnan(p) else "N/A", 
                "判定": "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns" if not np.isnan(p) else "N/A",
                "検定手法": test_desc_flat, "検定の前提": "ノンパラメトリック" if config.get('is_non_param') else "パラメトリック",
                "対応の有無": "対応あり" if config.get('is_paired') else "対応なし",
                "多重比較": "Controlとの比較" if config.get('is_vs_control') else "全ペア総当たり",
                "エラーバー": config.get('error_bar_type', '設定なし'), "正規化": config.get('norm_mode', '設定なし')
            })
        if stat_data: pd.DataFrame(stat_data).to_excel(writer, sheet_name='Statistical_Details', index=False)

        try:
            ws_sum = writer.book['Summary']
            sc = len(summary_df.columns) + 2
            ws_sum.cell(row=2, column=sc, value="💡 【エラーバー付き棒グラフの最短作成手順】")
            ws_sum.cell(row=3, column=sc, value="1. 左の『上段ラベル』と『平均』の列を選択し、[挿入] ＞ [縦棒グラフ] を作成。")
            ws_sum.cell(row=4, column=sc, value="2. グラフの棒をクリックし、[＋] ＞ [誤差範囲] ＞ [その他の誤差範囲オプション]。")
            ws_sum.cell(row=5, column=sc, value="3. 『カスタム』にチェックを入れ、『値の指定』。")
            ws_sum.cell(row=6, column=sc, value=f"4. 正負両方に、左の『{err_label}』の数値をドラッグして指定すれば完成！")

            if config['layout_mode'] == "条件ごとにグループ化":
                matrix_mean = pd.DataFrame(index=unique_up, columns=unique_low)
                matrix_sd = pd.DataFrame(index=unique_up, columns=unique_low)
                for i, uid in enumerate(internal_ids):
                    matrix_mean.at[upper_labels[i], lower_labels[i]] = np.nanmean(final_norm[uid])
                    matrix_sd.at[upper_labels[i], lower_labels[i]] = calc_error(final_norm[uid], config['error_bar_type'])
                
                matrix_mean.to_excel(writer, sheet_name='Summary_Matrix', startrow=1, startcol=0)
                matrix_sd.to_excel(writer, sheet_name='Summary_Matrix', startrow=len(unique_up)+4, startcol=0)
        except Exception: pass

    col_dl1, col_dl2 = st.columns(2)
    buf_svg = io.BytesIO()
    fig.savefig(buf_svg, format='svg', bbox_inches='tight')
    final_svg = embed_state_in_svg(fix_svg_font(buf_svg))
    
    with col_dl1: st.download_button("📥 Excelデータをダウンロード", excel_buffer.getvalue(), "Analysis_Data.xlsx", type="primary", use_container_width=True)
    with col_dl2: st.download_button("📥 完成グラフ(SVG)を保存", final_svg, "Graph.svg", "image/svg+xml", use_container_width=True)